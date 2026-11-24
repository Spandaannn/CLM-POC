# CLM POC — Handoff

**Date:** 2026-11-24
**Current phase:** Step 8 — Document Management implemented (uncommitted).
**Status:** Authentication, contract management, and versioned PDF/DOCX
document upload/list/download are implemented and verified. AI review,
approvals, and obligations remain unimplemented.

## Step 8 — Document management (2026-11-24)

### Verified results (all actually run)

| Check | Result |
|---|---|
| `python -m pytest -q` | **66 passed** (35 existing + 31 new document tests), 1 upstream warning |
| `python -m alembic check` | "No new upgrade operations detected" — **no migration needed** |
| `npm run lint` | exit 0, 0 warnings |
| `npm run build` | exit 0, 56 modules, JS 354.30 kB (109.04 kB gzip) |
| Browser (temporary business user, since deleted) | empty state; invalid type, empty file and >10 MB rejected client-side; PDF uploaded as v1; DOCX (empty browser MIME) as v2; version history and "Current" badge; download of v1 returned the exact 51-byte PDF under its original name; server rejection of a fake `.pdf` shown as a clear message; missing stored file shows a safe message; phone width has no page-level horizontal scroll |
| Data after checks | 1 user, 1 contract (`CTR-2026-574921E2`), **0 documents**, 2 audit events (unchanged); temporary test files removed from storage |

### Schema decision: no migration

The existing `contract_documents` table already has `original_filename`,
`stored_filename`, `storage_path`, `mime_type`, `file_size`, `version_number`,
`uploaded_by`, `is_current`, `uploaded_at`, a unique
`(contract_id, version_number)` and a partial unique index allowing one
`is_current` row per contract. So **each contract has one logical document and
its versions are the rows**. An upload adds version N+1, marks it current,
clears the flag on the previous row, and keeps every older row and file.
Consequence: a contract cannot hold several unrelated documents (for example
an agreement plus an annex) — that would need a `document_group_id` column and
a changed unique index (a future migration).

### API

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/contracts/{id}/documents` | Session + CSRF; creator or admin | Upload PDF/DOCX as the next version |
| GET | `/api/contracts/{id}/documents` | Session; contract viewer | All versions, newest first, plus `current` |
| GET | `/api/documents/{id}` | Session; contract viewer | Version metadata, `latest_version_number`, full history |
| GET | `/api/documents/{id}/download` | Session; contract viewer | File as `attachment`, `nosniff`, `no-store` |

Rules and security:

- **Who can do what:** anyone who may *view* the contract may list, read
  metadata, and download (business user: own contracts; reviewer/approver/admin:
  all). Only someone who may *edit* the contract (creator or admin) may upload.
  Legal reviewers therefore cannot upload yet.
- **Validation (all three must agree):** extension `.pdf`/`.docx`; declared
  MIME equal to the expected type or `application/octet-stream` (some systems
  do not know `.docx`); real content — PDF must start `%PDF-`, DOCX must be a
  zip containing `[Content_Types].xml` and `word/document.xml`, with entry-count
  and uncompressed-size limits against zip bombs. Errors: 415 unsupported,
  413 over 10 MB (read in 64 KB chunks and stopped at the limit), 422 empty,
  404 missing contract, 403 not permitted.
- **Storage:** `<DOCUMENT_STORAGE_PATH>/contracts/<contract_id>/<document_id>.<ext>`.
  Every path part is server generated; the client filename is sanitised and
  stored only as display metadata. Files are created with exclusive mode, so
  nothing is overwritten. `storage_path` in the database is relative; it and
  the stored filename are never returned by the API or written to audit logs.
- **Download:** the stored path is resolved and refused if it leaves the storage
  root; a missing file returns a generic 404 (details are logged server-side,
  never returned).
- **Concurrency:** the contract row is locked (`SELECT ... FOR UPDATE`) while
  the next version number is chosen. If the database step fails, the new file
  is deleted.
- **Audit:** `document.uploaded` (entity type `document`) with filename,
  version, size, and MIME type. Downloads are not audited.

### Frontend

Documents section on the contract detail page (`DocumentsSection.tsx`): file
picker with client-side checks mirroring the server, upload (labelled "Upload
version N"), version-history table (version, Current/Older badge, file, size,
uploaded date, uploader, Download), and loading, error-with-retry, empty,
success and error states. Upload uses `FormData` through the existing CSRF
helper; download fetches a blob with the session cookie so errors appear in the
page instead of a raw JSON tab. New files: `api/documents.ts`,
`lib/useDocuments.ts`, `lib/documentFile.ts`, `components/DocumentsSection.tsx`.

### Files changed in Step 8

Backend: `app/api/documents.py` (new), `app/services/documents.py` (new),
`app/schemas/document.py` (new), `app/api/router.py`, `app/core/config.py`
(`document_storage_path`), `app/main.py` (no-store for `/api/documents`),
`tests/test_documents.py` (new), `requirements.txt`, `.env.example`.
Frontend: the new files above plus `api/client.ts` (FormData + blob support),
`api/types.ts`, `pages/ContractDetailPage.tsx`, `styles/global.css`.
Repo: `.gitignore`, `README.md`, `ARCHITECTURE.md`, backend/frontend READMEs.

### New dependency

`python-multipart` (`>=0.0.9,<1.0`, 0.0.34 installed) — FastAPI cannot parse
file uploads without it. Run `pip install -r requirements.txt` after pulling.

### Step 8 limitations

- One logical document per contract (see above); no deletion of documents.
- The whole multipart body is received before the size check runs, so a very
  large upload still consumes bandwidth/temp space before a 413 (put a body
  limit on the reverse proxy in production).
- No virus/malware scanning; content checks confirm file *format*, not safety.
- Files are not encrypted at rest; the storage directory must be protected and
  backed up together with the database. Deleting a contract in the database
  would leave its files on disk (there is no deletion endpoint today).
- Upload is limited to the creator/admin; downloads are not audited.
- `.gitignore` also ignores every `*.pdf` and `*.docx` in the repo so sample
  contracts are never committed accidentally.
- No automated frontend tests for the documents UI (verified in the browser).

## Earlier: stabilisation fixes (2026-11-24, after Step 7)

### Backend test failure — `test_access_is_limited_by_role_and_ownership`

- **Symptom:** reviewer list expected `total == 1`, got `2`.
- **Cause:** test isolation, not access control. Tests run on the real
  database inside a rolled-back transaction, so they also see committed rows.
  A real contract (`CTR-2026-574921E2`, created manually through the app by
  the existing admin) was present. Reviewers and admins are *meant* to see all
  contracts, so the API was right; the test wrongly assumed the table was
  empty.
- **Second latent bug found in the same test:** the final "owner list" check
  ran while the admin was still the logged-in user (the client cookie belongs
  to the last login), so it never checked the owner's list.
- **Fix (`backend/tests/test_contracts.py` only):** the contract gets a unique
  title, and reviewer/admin visibility is asserted with `?q=<marker>` and an
  exact ID match. The test signs back in as the owner before the owner-list
  check. No application code, fixtures, or data were changed; the manual
  contract was left in place.

### Frontend lint warnings (4 × `react(set-state-in-effect)`)

- **Cause:** contract pages reset loading/error state synchronously at the
  start of data-fetching effects, and the list page copied URL params into
  input state in an effect.
- **Fix:**
  - New `src/lib/useContract.ts` hook shared by `ContractDetailPage` and
    `EditContractPage`. Each result is tagged with the request it answers, and
    "loading" is derived when the newest request has no result yet. Retry
    increments a reload key.
  - `ContractsPage`: same derived-loading pattern for the list. The filter
    form became a `FilterBar` component keyed by the URL query string, so
    back/forward and Clear remount it with the URL's values (no sync effect).
- Behaviour is unchanged; verified in the browser (see below).

### Verified results

| Check | Result |
|---|---|
| `python -m pytest -q` | **35 passed**, 1 upstream warning, with the manual contract still in the database |
| `npm run lint` | exit 0, **0 warnings, 0 errors** |
| `npm run build` | exit 0, 52 modules, JS 348.13 kB (107.62 kB gzip) |
| Browser (temporary business user, since deleted) | protected redirect and login; empty state; search applies and updates the URL; back/forward restore inputs and results; no-match state and Clear filters; status/type filters from the URL; detail; edit and save with success banner; 404 page; error page with Try again issuing a new request; sign out |
| Data after checks | 1 user, 1 contract (`CTR-2026-574921E2`), 2 audit events — unchanged |

Recommendation (not done): point tests at a dedicated `clm_test` database so
manual data can never affect test results.

## Verified status (Step 7, 2026-11-24)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` | **35 passed** (15 auth/health + 20 contracts), 1 upstream warning |
| Migration | `python -m alembic current` | `20261123_0001 (head)` — no new migration needed |
| Frontend lint | `npm run lint` | exit 0, 4 `set-state-in-effect` warnings at the time; **fixed since — now 0** |
| Frontend build | `npm run build` | exit 0, 51 modules, JS 348.22 kB (107.56 kB gzip) |
| Live API smoke | Vite proxy → FastAPI → PostgreSQL | **20/20 passed** (auth, CSRF, validation, search/filters, update, cross-user 403, audit events, logout) |
| Browser flow | In-app browser | protected redirect → login → empty state → create → detail → edit → filtered list → dashboard → sign out |
| Database after tests | count | **1 user** (existing admin), **0 contracts**; all temporary verification users/contracts/audit rows deleted |

Step 6 results (Lighthouse 100/100/100, 37 auth integration checks) are in
`frontend/README.md`.

## Step 7 — what was done in the final session

The contract backend, pages, and routes already existed but the frontend build
was **broken**: a half-finished refactor had moved `contractToFormValues`,
`toContractPayload`, and `ContractFormValues` into `src/lib/contractForm.ts`
without removing the copies (with missing type imports) from
`components/ContractForm.tsx`, and the pages imported from the wrong module.
Fix: removed the duplicates from the component and pointed `NewContractPage` and
`EditContractPage` at `lib/contractForm`. No backend code was changed.

## Contract management (Step 7)

Backend (`app/api/contracts.py`, `app/services/contracts.py`,
`app/schemas/contract.py`):

- `GET /api/contracts` — `q`, `status`, `contract_type`, `page`, `page_size`.
- `POST /api/contracts` — CSRF; creates a draft with a generated number.
- `GET /api/contracts/{id}` — 404 if missing, 403 if not permitted.
- `PATCH /api/contracts/{id}` — CSRF; partial update including status.
- Visibility: `business_user` → own contracts; `legal_reviewer`,
  `legal_approver`, `admin` → all. Edit: creator or `admin`.
- Audit: `contract.created` and `contract.updated` (changed fields only, no
  event for a no-op update), in the same transaction as the change.
- Validation: `extra="forbid"`, lengths, currency, decimal value ≥ 0,
  date range; DB check constraints as a backstop.

Frontend: `/contracts`, `/contracts/new`, `/contracts/:id`,
`/contracts/:id/edit`; nav link in `AppShell`; filters stored in the URL;
loading, error-with-retry, empty, no-match, 403, and 404 states.

## Project structure

```text
Demo-CLM/
├── README.md                   # Project overview and setup
├── ARCHITECTURE.md
├── HANDOFF.md
├── backend/
│   ├── app/                    # FastAPI app, auth, models, schemas, services
│   ├── alembic/                # Initial schema migration
│   ├── scripts/                # check_db.py, create_user.py
│   ├── tests/                  # 15 PostgreSQL-backed tests
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── README.md
└── frontend/
    ├── src/
    │   ├── api/                # fetch client, auth calls, types
    │   ├── auth/               # AuthProvider, useAuth, RequireAuth
    │   ├── components/         # AppShell, Button, TextField, Alert, Spinner
    │   ├── lib/                # errors, formatting, navigation helpers
    │   ├── pages/              # Login, Dashboard, NotFound
    │   ├── styles/             # tokens.css, global.css
    │   ├── App.tsx
    │   ├── main.tsx
    │   └── router.tsx
    ├── public/                 # favicon.svg, robots.txt
    ├── vite.config.ts          # /api and /health proxy
    └── README.md
```

## Backend implemented

- FastAPI app at `app.main:app`, Swagger at `/docs`.
- `/health` and `/health/db`.
- Aggregating API router for future CLM modules.
- Argon2id password hashing via `pwdlib`.
- `GET /api/auth/csrf`, `POST /api/auth/login`, `POST /api/auth/logout`,
  `GET /api/auth/me`.
- 256-bit opaque session tokens; only SHA-256 hashes stored in `user_sessions`.
- HttpOnly session cookie; `Secure`/`SameSite` configurable.
- Double-submit CSRF protection using `clm_csrf` plus `X-CSRF-Token`.
- Generic login errors, dummy-hash timing mitigation, inactive-account handling.
- Interactive first-administrator script.
- Safe validation/error handlers that do not echo passwords.
- 15 tests using the real PostgreSQL database with per-test transaction rollback.

## Frontend implemented (Step 6)

- Vite + React 19 + TypeScript application in `frontend/`.
- React Router with public `/login`, protected `/dashboard`, root redirect, and
  a 404 page.
- Vite development and preview proxy for `/api` and `/health` to
  `http://127.0.0.1:8000`; no CORS needed in development.
- Typed Fetch client with `credentials: 'include'` and normalized API errors.
- CSRF flow matching the backend exactly:
  - `GET /api/auth/csrf` bootstraps the token and cookie.
  - Login/logout send `X-CSRF-Token`.
  - Login rotates the token and the new value is kept in memory.
  - Stale-token `403` retries once with a freshly fetched token.
- `AuthProvider` restores the session with `GET /api/auth/me`, distinguishes
  signed-out from connection failures, and exposes login/logout.
- `RequireAuth` protects routes and preserves `returnTo`; unsafe external return
  URLs are rejected.
- Professional responsive login page with accessible labels, focus states,
  loading state, and generic error messaging.
- Authenticated dashboard showing the real signed-in user's name, email, role,
  active status, and member-since date.
- Clearly labelled placeholders for Contracts, Documents, AI Reviews, and
  Approvals, all marked “Not implemented yet”.
- Empty-state panel for future contract activity.
- Logout works after a page refresh by re-fetching the CSRF token.
- No session or CSRF tokens in `localStorage` or `sessionStorage`.
- No extra UI, state, or form libraries.

## Key files added or modified

### Backend (from the previous phase)

| Path | Purpose |
|---|---|
| `backend/app/main.py` | App factory, routing, exception handlers, no-store auth headers |
| `backend/app/api/auth.py` | CSRF, login, logout, `/me` endpoints |
| `backend/app/api/deps.py` | DB session, current-user, CSRF dependencies |
| `backend/app/api/health.py` | `/health`, `/health/db` |
| `backend/app/services/auth.py` | Authentication and session operations |
| `backend/app/core/security.py` | Argon2id and token helpers |
| `backend/app/core/cookies.py` | Session/CSRF cookie helpers |
| `backend/app/core/exceptions.py` | Safe error responses |
| `backend/app/schemas/` | Auth, user, health, error schemas |
| `backend/scripts/create_user.py` | First administrator creation |
| `backend/tests/` | Health and auth tests |
| `backend/README.md` | Backend setup and API documentation |

### Frontend (this phase)

| Path | Purpose |
|---|---|
| `frontend/vite.config.ts` | React plugin and `/api`/`/health` proxy |
| `frontend/src/api/client.ts` | Fetch wrapper, credentials, error handling |
| `frontend/src/api/auth.ts` | CSRF, login, logout, current-user calls |
| `frontend/src/api/types.ts` | Backend response types |
| `frontend/src/auth/AuthProvider.tsx` | Session restoration and auth actions |
| `frontend/src/auth/RequireAuth.tsx` | Protected routing |
| `frontend/src/auth/authContext.ts` | Context shape |
| `frontend/src/auth/useAuth.ts` | Typed context hook |
| `frontend/src/router.tsx` | Route table |
| `frontend/src/pages/LoginPage.tsx` | Login UI and states |
| `frontend/src/pages/DashboardPage.tsx` | User details and module placeholders |
| `frontend/src/pages/NotFoundPage.tsx` | 404 page |
| `frontend/src/components/AppShell.tsx` | Header, navigation, sign out |
| `frontend/src/components/` | Button, TextField, Alert, Spinner |
| `frontend/src/lib/` | Error, formatting, and return-path helpers |
| `frontend/src/styles/` | CSS tokens and global responsive styles |
| `frontend/.env.example` | Optional `VITE_API_BASE_URL` |
| `frontend/public/favicon.svg`, `robots.txt` | Static assets |
| `frontend/README.md` | Setup, manual tests, verification results |
| `HANDOFF.md` | This update |

No backend authentication code, models, or migrations were changed in Step 6.

## Run the application

### Terminal 1 — backend

```powershell
cd C:\Users\Spandan\Projects\OpenCode\Demo-CLM\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Fallback if activation is blocked:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Terminal 2 — frontend

```powershell
cd C:\Users\Spandan\Projects\OpenCode\Demo-CLM\frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Use `localhost` consistently; cookies are
host-specific.

### Checks

```powershell
# Backend
cd C:\Users\Spandan\Projects\OpenCode\Demo-CLM\backend
.\.venv\Scripts\python.exe -m pytest -q

# Frontend
cd C:\Users\Spandan\Projects\OpenCode\Demo-CLM\frontend
npm run lint
npm run build
```

## Manual verification summary

Detailed steps are in `frontend/README.md`. Verified flows:

1. Signed-out `/dashboard` redirects to
   `/login?returnTo=%2Fdashboard`.
2. Wrong password shows “Invalid email or password” and creates no session.
3. Correct login lands on the dashboard with the real user's name, email, role,
   active status, and member-since date.
4. Refresh restores the session.
5. Visiting `/login` while authenticated redirects to `/dashboard`.
6. Logout after a refresh works (CSRF token is re-fetched), returns to login, and
   old session tokens are rejected.
7. Return-to login lands on `/dashboard`.
8. Browser storage contains no tokens; `clm_session` is HttpOnly and only
   `clm_csrf` is visible to JavaScript.
9. Backend-unavailable state shows a retryable error instead of a false logout.
10. Lighthouse reports 100 for Accessibility, Best Practices, and SEO on both the
    login page and dashboard after fixing two contrast issues, a brand-link
    accessible-name mismatch, and adding a valid `robots.txt`.

## Environment variables

### Backend (`backend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `DATABASE_URL` | required | PostgreSQL URL with `postgresql+psycopg://` |
| `DATABASE_ECHO` | `false` | SQL logging |
| `SESSION_TTL_MINUTES` | `480` | Absolute session lifetime |
| `COOKIE_SECURE` | `false` | Must be `true` behind HTTPS |
| `COOKIE_SAMESITE` | `lax` | `none` requires Secure |
| `DOCUMENT_STORAGE_PATH` | `storage/documents` | Upload directory; relative paths resolve against `backend/`. Git-ignored; keep outside any served directory |

The real database password stays in `backend/.env`, which is Git-ignored.

### Frontend (`frontend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Empty means same-origin through the Vite proxy |

Vite variables are public; never put secrets in them.

## Known limitations

- **No AI review, approval, or obligation functionality.** The dashboard
  placeholders are informational only. Status changes are free-form (any
  status → any status) until approval workflow rules exist.
- **No contract deletion** endpoint or UI.
- **Contract audit events are written but not shown in the UI.**
- **Git:** `.gitignore` excludes `.env`, `.venv`, `node_modules`, `dist`,
  caches, key files, the document storage directory, and `*.pdf`/`*.docx`.
- **No automated frontend test suite.** Verification used TypeScript build,
  lint, HTTP integration checks, and browser/Lighthouse checks. Vitest/React
  Testing Library should be added with the first contract UI.
- **No physical mobile-device test.** Responsive breakpoints and accessible
  markup are implemented, and Lighthouse accessibility is 100, but device
  testing remains a manual follow-up.
- **Development uses the Vite proxy.** Production hosting must serve `dist/` and
  `/api` from the same origin, or configure CORS and production cookie settings.
- **No automatic idle-session polling.** Expiry is detected on the next full load
  or authenticated request.
- **No production hardening yet:** login rate limiting, account lockout, audit
  logging, signed CSRF/origin checks, session cleanup job, and HTTPS deployment.
- **Existing admin password was not used by the agent.** The real login flow was
  verified with a temporary committed test account that was deleted immediately
  afterwards.
- **Backend limitations remain:** no registration, password reset, user
  management, or email verification.

## Next steps

1. Implement review findings and approval workflows (including status
   transition rules).
2. Show contract audit history on the detail page.
3. Add frontend tests (Vitest + React Testing Library, optionally Playwright).
4. Allow reviewers to upload; consider several documents per contract
   (`document_group_id` migration) and document deletion.
5. Add production deployment: same-origin static hosting, HTTPS, secure cookies,
   rate limiting, and auth audit logging.
