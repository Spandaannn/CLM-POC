# Deploying the CLM POC on Render (free plan)

This guide deploys the whole application as **one Render Web Service (Docker)**
plus **one free Render PostgreSQL database**. Nothing here needs a paid plan.

## How it works (plain English)

- The `Dockerfile` builds the React app, copies the finished files into a Python
  image, and starts FastAPI.
- FastAPI answers two kinds of requests from the **same web address**:
  - `/api/...`, `/health`, `/docs`, `/openapi.json` are the backend API.
  - Everything else (`/`, `/contracts/123`, ...) gets the React app. A page
    refresh on `/contracts/123` therefore works.
- Because the browser only ever talks to one address, the login cookie is a
  normal first-party cookie. There is no CORS and no cross-site cookie problem.
- When the container starts it first runs `alembic upgrade head` (database
  migrations) and then starts the server. Migrations never run while the image
  is being built. If a migration fails, the deploy fails and the old version
  keeps running.
- Local development is unchanged: `FRONTEND_DIST_DIR` is not set locally, so the
  backend serves only the API and Vite keeps proxying `/api`.

## Free-plan limitations (read before demoing)

| Limitation | What it means |
|---|---|
| **Uploaded documents are NOT persistent** | Files are stored on the container's temporary disk. They are **lost on every restart, redeploy and spin-down**. The database rows stay, so a contract may list a document whose file no longer exists (downloads and AI reviews of it then fail). Upload a fresh document shortly before demonstrating. Do not rely on stored documents. |
| Web service sleeps | After about 15 minutes without traffic the service spins down. The next request can take up to about a minute. Open the site a few minutes before the demo. Every spin-down also clears uploaded files (above). |
| Free database expires | A free Render Postgres database expires **30 days after creation** (a short grace period follows, then it is deleted). It has 1 GB of storage and no backups. |
| Limited resources | Free instances have small CPU/RAM; large files or many parallel users are not expected to work well. |
| Groq free tier | The AI provider has its own token-per-minute limits. Contract text is sent to Groq only when someone clicks "Run AI review". Use fictional contracts. |

Logins survive restarts, because sessions are stored in the database.

## Configuration summary

| Variable | Value on Render | Notes |
|---|---|---|
| `DATABASE_URL` | Internal Database URL of the free database | Set automatically by the Blueprint. A plain `postgresql://` URL is accepted. |
| `COOKIE_SECURE` | `true` | Render serves HTTPS. |
| `COOKIE_SAMESITE` | `lax` | Frontend and API share one origin. |
| `AI_PROVIDER` | `groq` | Optional; without it the app works and AI review says "not configured". |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | Optional. |
| `GROQ_API_KEY` | your key | **Secret.** Enter it only in the Render dashboard. Never commit it or put it in frontend code. The backend reads it from the environment; the frontend never sees it. |
| `DOCUMENT_STORAGE_PATH` | default `/app/storage/documents` (set in the Dockerfile) | Ephemeral on the free plan. Override only if you change storage later. |
| `FRONTEND_DIST_DIR` | default `/app/frontend_dist` (set in the Dockerfile) | Turns on serving of the React app. Leave empty locally. |
| `VITE_API_BASE_URL` | empty | Same-origin requests. The Dockerfile builds with it empty. |
| `PORT` | set by Render | The container listens on `0.0.0.0:$PORT`. |
| `SESSION_TTL_MINUTES`, `AI_*`, `GROQ_REASONING_EFFORT` | optional | Defaults are fine. |

## Option A: Blueprint (`render.yaml`) - recommended

`render.yaml` creates the free database and the free web service together and
contains no secrets.

1. Push the repository to GitHub (after you have reviewed and committed it).
2. In the Render dashboard choose **New > Blueprint**, connect the GitHub
   repository, and select the `main` branch. Render finds `render.yaml`.
3. When prompted, paste your **Groq API key** into `GROQ_API_KEY` (this value is
   stored by Render, not in Git). Leave the other values as shown.
4. Click **Apply**. Render creates `clm-db` (free) and `clm-poc` (free), builds
   the Docker image (several minutes the first time) and starts it. The start
   command applies the migrations.
5. Open the service URL (`https://clm-poc-xxxx.onrender.com`) and check:
   - `/health` returns `{"status":"ok"}` and `/health/db` returns
     `{"status":"ok","database":"ok"}`.
   - `/docs` shows Swagger.
   - `/` shows the login page, and refreshing `/contracts` keeps working.
6. Create the demo accounts (below).

Deploys do not happen automatically (`autoDeploy: false`). After pushing new
code use **Manual Deploy > Deploy latest commit** on the service.

## Option B: manual setup in the dashboard

1. **New > PostgreSQL**: Name `clm-db`, Database `clm_db`, User `clm_user`,
   Region = the region you will use for the service, **Instance Type: Free**.
   Create it, then copy its **Internal Database URL**.
2. **New > Web Service** > connect the GitHub repo and use:

   | Setting | Value |
   |---|---|
   | Branch | `main` |
   | Language / Runtime | `Docker` |
   | Root Directory | (leave empty) |
   | Dockerfile Path | `./Dockerfile` |
   | Docker Build Context Directory | `.` |
   | Docker Command | (leave empty; the Dockerfile `CMD` runs migrations then uvicorn) |
   | Region | same as the database |
   | Instance Type | **Free** |
   | Health Check Path | `/health` |
   | Auto-Deploy | No |

3. Add the environment variables from the table above (`DATABASE_URL` = the
   Internal Database URL, `COOKIE_SECURE=true`, `COOKIE_SAMESITE=lax`,
   `AI_PROVIDER=groq`, `GROQ_MODEL`, and `GROQ_API_KEY` as a secret).
4. **Create Web Service** and verify as in Option A step 5.

## Creating the demo accounts

There is deliberately **no public registration endpoint**, and no passwords are
stored in the repository. Accounts are created with
[`backend/scripts/create_user.py`](backend/scripts/create_user.py), which asks
for the name, email and password interactively (password hidden, minimum 12
characters). It now accepts `--role` (default `admin`). Render's free plan has no
shell, so run the script **from your own computer against the hosted database**:

1. In the Render dashboard open the database `clm-db` > **Connections** and copy
   the **External Database URL**. Under **Access Control** temporarily add your
   public IP address (for example `203.0.113.7/32`).
2. In PowerShell, from the repository root (use the real URL from the
   dashboard; do not commit it or paste it into chat):

   ```powershell
   cd backend
   $env:DATABASE_URL = "<paste the External Database URL here>"
   # Sanity check: prints host and database only, not the password.
   ($env:DATABASE_URL -split '@')[1]
   ```

   A process environment variable takes precedence over `backend/.env`, so your
   local `.env` is not used and not modified.
3. Run the script once per account (the migrations must already have run, which
   happens on the first successful deploy):

   ```powershell
   .\.venv\Scripts\python.exe scripts\create_user.py                       # admin
   .\.venv\Scripts\python.exe scripts\create_user.py --role business_user
   .\.venv\Scripts\python.exe scripts\create_user.py --role legal_reviewer
   .\.venv\Scripts\python.exe scripts\create_user.py --role legal_approver
   ```

   Use a different email for each (for example `admin@yourdomain`,
   `creator@...`, `reviewer@...`, `approver@...`) and choose strong passwords.
4. Clean up: remove the variable and your IP from the allow list.

   ```powershell
   Remove-Item Env:DATABASE_URL
   ```

5. Give the mentor the credentials privately (not in Git or chat history).

Suggested demo walk-through: sign in as the business user, create a contract and
upload a fictional PDF, optionally run the AI review, submit for approval
choosing the reviewer and approver, then sign in as each to recommend and
approve. Roles are documented in `HANDOFF.md`.

## Testing the image locally (optional)

If Docker is installed:

```powershell
docker build -t clm-poc .
docker run --rm -p 10000:10000 -e DATABASE_URL="<a local or test PostgreSQL URL reachable from the container>" -e COOKIE_SECURE=false clm-poc
```

then open `http://localhost:10000`. (`COOKIE_SECURE=false` is only for plain-HTTP
local testing; always `true` on Render.) The image contains no secrets; pass
them with `-e`.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Deploy fails right after the build | `alembic upgrade head` could not reach the database. Check `DATABASE_URL` is the **Internal** URL of a database in the **same region**. Read the deploy logs. |
| First page takes ~1 minute | Free service waking from sleep. |
| Login works then immediately logs out | `COOKIE_SECURE=true` over plain HTTP (local only) or a wrong `COOKIE_SAMESITE`. Use HTTPS on Render and `lax`. |
| "AI review is not configured" | `GROQ_API_KEY` / `AI_PROVIDER` missing or invalid in the dashboard. |
| Document download fails or "file not found" after a while | Expected on the free plan: the ephemeral disk was cleared. Upload the file again. |
| Everything is gone after about a month | The free database expired. Create a new one and re-create the accounts. |

## Moving to a durable setup later

Paid Render adds a persistent disk (set `DOCUMENT_STORAGE_PATH` to the disk's
mount path) and a non-expiring database. No code changes are required; only
configuration.
