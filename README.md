# CLM POC — Contract Lifecycle Management

A proof of concept for a Legal Department to manage contracts. It currently
provides secure session-based sign-in, end-to-end **contract metadata
management** (create, list, search, filter, view, edit) with role/ownership
authorization and an audit trail, **versioned PDF/DOCX documents** per
contract, optional **AI-assisted contract review** (Groq), and a two-stage
**approval workflow** (Legal Reviewer, then Legal Approver) with request-changes,
rejection, and resubmission history. Contract status is controlled by that
workflow (see [ARCHITECTURE.md](ARCHITECTURE.md)). Obligation tracking is
designed but **not implemented yet**.

## Architecture

```text
Browser (React + Vite + TypeScript, localhost:5173)
   │  same-origin /api via Vite proxy, HttpOnly session cookie + CSRF header
   ▼
FastAPI (Python, 127.0.0.1:8000)
   │  SQLAlchemy 2 + psycopg 3, Alembic migrations
   ▼
PostgreSQL 18 (clm_db)
```

| Layer | Location | Notes |
|---|---|---|
| Frontend | [`frontend/`](frontend/README.md) | React 19, React Router 7, plain CSS, native fetch |
| Backend | [`backend/`](backend/README.md) | FastAPI, Pydantic v2, Argon2id, server-side sessions |
| Database | PostgreSQL | `users`, `user_sessions`, `contracts`, `audit_events`, plus tables reserved for documents, reviews, approvals, obligations |

## Implemented features

- **Authentication:** login/logout, `/me`, opaque session tokens (hash stored),
  HttpOnly cookie, double-submit CSRF, protected routes with `returnTo`.
- **Dashboard:** signed-in user details and module overview.
- **Contracts:**
  - List with search (title, number, counterparty), status and type filters,
    pagination; loading, error, empty, and no-match states.
  - Create (server-generated `CTR-<year>-<hex>` number, starts as draft).
  - Detail page; edit page (metadata while a draft; after approval only the
    lifecycle status can change, because approval states are set by the workflow).
  - Authorization: business users see/edit only their own contracts; legal
    reviewers and approvers can view all; admins can view and edit all.
  - `contract.created` / `contract.updated` audit events with field-level diffs.
  - Input validation on client and server, plus database check constraints.
- **Documents (Step 8):** upload PDF/DOCX (max 10 MB) on the contract detail
  page, each upload saved as a new version with older versions kept, version
  history, authorised download, and `document.uploaded` audit events. Files are
  stored on the local disk under `DOCUMENT_STORAGE_PATH`; content is verified,
  not just the extension.
- **Approval workflow (Step 10):** a creator submits a draft with a document
  and picks a Legal Reviewer and Legal Approver. The reviewer recommends,
  requests changes, or rejects; the approver gives final approval, requests
  changes, or rejects. Changes sent back reopen the draft for edit and
  resubmission as a new cycle, with all earlier cycles kept. Decisions are
  validated on the server, comments are mandatory for rejections and change
  requests, the creator can never approve their own contract, and a contract
  is locked while under approval. The dashboard shows an approval queue.
- **AI review (Step 9, optional):** on a contract with a document, click
  **Run AI review** to get an executive summary, extracted metadata and
  clauses, risk findings with verified source excerpts, a comparison with a
  configurable playbook, and a history of reviews tied to document versions.
  Powered by Groq; results are suggestions for a human legal reviewer and never
  approve, reject, or change a contract.

## Setup

Prerequisites: Python 3.11+, Node.js 20+, PostgreSQL 18 with a `clm_db`
database and `clm_user` role.

### 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
Copy-Item .env.example .env      # then set the real password in DATABASE_URL
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe scripts\create_user.py   # first administrator (interactive)
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Frontend (second terminal)

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173** (use `localhost` consistently; cookies are
host-specific). API docs: http://127.0.0.1:8000/docs.

### Database configuration

`backend/.env` (Git-ignored) holds `DATABASE_URL`, e.g.
`postgresql+psycopg://clm_user:<password>@localhost:5432/clm_db`.
Percent-encode special characters in the password. See
[backend/README.md](backend/README.md) for all variables.

### Document storage

Uploaded contracts are written to `DOCUMENT_STORAGE_PATH` (default
`backend/storage/documents`, created automatically; set it in `backend/.env`).
Layout: `contracts/<contract-id>/<document-id>.pdf|docx`. The directory is
Git-ignored and is **not** served by the frontend; keep it outside any public
directory, restrict OS access, and back it up together with the database.
Never commit uploaded contracts.

- **Allowed:** `.pdf` and `.docx`, up to 10 MB; extension, MIME type and real
  content must all be valid.
- **Versioning:** every upload becomes the next version of the contract's
  document (v1, v2, ...); the latest is marked *Current* and earlier files are
  never overwritten or removed.
- **Permissions:** contract viewers can list and download; the creator or an
  administrator can upload.

### AI review (optional)

Add to `backend/.env` (the file is Git-ignored; never commit a key) and restart
the backend:

```text
AI_PROVIDER=groq
GROQ_API_KEY=<your key from the Groq console>
GROQ_MODEL=openai/gpt-oss-20b
```

Without these the app works normally and the AI section says AI is not
configured. Contract text is sent to Groq **only** when a signed-in user clicks
**Run AI review** (never on upload). Supported files: text-based PDF and
`.docx` (scanned PDFs have no text and OCR is not supported). The playbook is an
illustrative baseline, not an approved legal policy; point `AI_PLAYBOOK_PATH`
at your own JSON. On Groq's free tier only short contracts fit the
8,000-tokens-per-minute limit. See [HANDOFF.md](HANDOFF.md) for all variables
and limitations.

## Checks

```powershell
cd backend;  .\.venv\Scripts\python.exe -m pytest -q
cd frontend; npm run lint; npm run build
```

Last run (2026-11-25): backend **203 passed**; lint exit 0 (0 warnings);
build exit 0. Backend tests use the real PostgreSQL database inside a
rolled-back transaction, so they must not assume tables are empty; a dedicated
test database is recommended.

## Limitations

- No obligations yet. The approval workflow has one reviewer and one approver
  per cycle, no notifications, e-signature, or delegation. AI review output varies, can be wrong, and
  is limited by the provider's rate limits (free-tier Groq: short contracts
  only); no OCR for scanned PDFs.
- One logical document per contract (versions only); no document or contract
  deletion; no malware scanning; no user management UI (users are created by
  script).
- No frontend automated tests (verified via build, lint, live API smoke test,
  and manual browser flows).
- Development only: no HTTPS, rate limiting, or production deployment config.

See [HANDOFF.md](HANDOFF.md) for detailed status and next steps.
