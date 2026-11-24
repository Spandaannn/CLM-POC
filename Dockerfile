# syntax=docker/dockerfile:1
#
# Single-container build for Render: FastAPI serves the API AND the built React
# app from the same origin. Build context is the repository root.
#
#   docker build -t clm-poc .
#
# Nothing secret is baked in: no .env, no keys, no uploads (see .dockerignore).
# All configuration arrives as environment variables at run time.

# ---- Stage 1: build the React frontend -------------------------------------
FROM node:22-bookworm-slim AS frontend-build

WORKDIR /build/frontend

# Install from the lock file first so this layer is cached between builds.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Empty = same-origin requests (/api/...), which is what FastAPI serves.
ENV VITE_API_BASE_URL=
RUN npm run build


# ---- Stage 2: Python runtime ------------------------------------------------
# Python 3.12 is pinned deliberately: every dependency in requirements.txt
# publishes Linux wheels for it. (Local development may use a newer Python.)
FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 clm

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install -r requirements.txt

COPY backend/alembic.ini ./alembic.ini
COPY backend/alembic ./alembic
COPY backend/app ./app
COPY backend/scripts ./scripts
COPY --from=frontend-build /build/frontend/dist ./frontend_dist

# Uploaded documents. On Render's free plan this folder is EPHEMERAL: files are
# lost whenever the service restarts, redeploys or spins down.
RUN mkdir -p /app/storage/documents && chown -R clm:clm /app/storage

USER clm

ENV FRONTEND_DIST_DIR=/app/frontend_dist \
    DOCUMENT_STORAGE_PATH=/app/storage/documents

# Render sets PORT (10000 by default). 10000 is the fallback for local runs.
EXPOSE 10000

# Migrations run when the container STARTS (never during the image build). If
# `alembic upgrade head` fails, the container exits and the deploy fails
# instead of serving an app with a mismatched schema.
# --proxy-headers lets uvicorn trust Render's load balancer for the real
# client scheme (https) and address.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000} --proxy-headers --forwarded-allow-ips='*'"]
