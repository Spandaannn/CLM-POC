# CLM Backend — FastAPI and Session Authentication

FastAPI application with session-based authentication and contract metadata
management (Step 7) on top of the existing PostgreSQL schema. Document storage,
approval workflows, and AI integration are not implemented yet.

## What is implemented

### Contracts (Step 7)

- `POST/GET /api/contracts`, `GET/PATCH /api/contracts/{id}`.
- Search (`q` across title, contract number, counterparty; LIKE wildcards
  escaped), `status` and `contract_type` filters, pagination.
- Server-generated contract number (`CTR-<year>-<8 hex>`), creator, and
  timestamps; clients cannot set them (`extra="forbid"`).
- Authorization: business users see and edit only contracts they created;
  legal reviewers/approvers can view all; admins can view and edit all.
- `contract.created` and `contract.updated` rows in `audit_events`, written in
  the same transaction; updates record only changed fields (`from`/`to`).
- Validation: required fields, lengths, non-negative value with 2 decimals,
  3-letter currency, `end_date >= start_date` (also enforced by DB checks).
- CSRF required on create and update.

### AI review (Step 9)

- Provider-independent AI layer (`app/ai/`) with Groq as the first adapter;
  `GET /api/ai/status`, `POST/GET /api/contracts/{id}/reviews`,
  `GET /api/reviews/{id}`.
- Text extraction from stored PDF (`pypdf`) and DOCX (stdlib XML); no OCR.
- Structured results stored in `review_results` (migration `20261124_0002`):
  summary, metadata, clauses, risk findings, playbook results, document id and
  **version**, provider/model, status, initiating user. Quotations are verified
  against the document text; unverifiable ones are dropped.
- Configure with `AI_PROVIDER`, `GROQ_API_KEY`, `GROQ_MODEL` (and optional
  `GROQ_REASONING_EFFORT`, `AI_MAX_OUTPUT_TOKENS`, `AI_MAX_INPUT_CHARS`,
  `AI_TIMEOUT_SECONDS`, `AI_PLAYBOOK_PATH`). The key never appears in any
  response, log, or test output. Without configuration the rest of the API is
  unaffected. All tests mock the provider.

### Documents (Step 8)

- Versioned PDF/DOCX files per contract: each upload is the next version, the
  latest is `is_current`, and older rows/files are kept. Uses the existing
  `contract_documents` table, so **no migration** was needed.
- Validation of extension, MIME type and file signature (PDF `%PDF-`; DOCX zip
  with `[Content_Types].xml` and `word/document.xml`), 10 MB limit (413).
- Stored at `DOCUMENT_STORAGE_PATH/contracts/<contract_id>/<document_id>.<ext>`
  with server-generated names; the database holds a relative path and the API
  never returns it. Download refuses paths outside the storage root and returns
  a generic 404 if the file is missing.
- Viewers of a contract can list/download; the creator or an admin can upload.
  `document.uploaded` audit events. Needs `python-multipart`.

### Authentication

- FastAPI app with `/health` and `/health/db`.
- API router structure ready for future CLM modules.
- Argon2id password hashing via `pwdlib`.
- Login, logout, and current-user endpoints.
- Opaque 256-bit session tokens; only SHA-256 hashes are stored in
  `user_sessions`.
- HttpOnly session cookie with configurable `Secure` and `SameSite` attributes.
- Double-submit-cookie CSRF protection for state-changing auth requests.
- Interactive script for creating the first administrator account.
- PostgreSQL-backed pytest suite using transaction rollback (no SQLite).

## Project layout

```text
backend/
├── app/
│   ├── main.py                 # FastAPI app factory and global handlers
│   ├── api/
│   │   ├── router.py           # Aggregates future module routers
│   │   ├── deps.py             # DB, current-user, and CSRF dependencies
│   │   ├── health.py           # /health and /health/db
│   │   ├── auth.py             # /api/auth/* endpoints
│   │   └── contracts.py        # /api/contracts endpoints
│   ├── core/
│   │   ├── config.py           # Environment settings
│   │   ├── cookies.py          # Cookie names and attributes
│   │   ├── security.py         # Argon2id and token helpers
│   │   └── exceptions.py       # Validation and database error handlers
│   ├── db/                     # Engine, sessions, health helpers
│   ├── models/                 # Existing SQLAlchemy models
│   ├── schemas/                # Pydantic request/response schemas
│   └── services/               # auth.py (sessions), contracts.py (queries, access, audit)
├── alembic/                    # Existing initial migration
├── scripts/
│   ├── check_db.py             # Connection/schema check
│   └── create_user.py          # First administrator account
├── tests/                      # PostgreSQL-backed API tests
├── .env.example
├── requirements.txt
└── requirements-dev.txt
```

## 1. Prerequisites

- Python 3.11 or newer
- PostgreSQL 13 or newer (this project uses PostgreSQL 18 locally)
- The `clm_db` database and `clm_user` role created during database setup

## 2. Install dependencies

From `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

If activation is blocked, use `.\.venv\Scripts\python.exe` directly for every
command.

## 3. Environment variables

Copy `.env.example` to `.env` if it does not exist, then set the password:

```powershell
Copy-Item .env.example .env
```

| Variable | Required | Default | Purpose |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | PostgreSQL URL using `postgresql+psycopg://` |
| `DATABASE_ECHO` | No | `false` | Log SQL statements |
| `SESSION_TTL_MINUTES` | No | `480` | Absolute session lifetime |
| `COOKIE_SECURE` | No | `false` | Send cookies only over HTTPS; set `true` in production |
| `COOKIE_SAMESITE` | No | `lax` | `lax`, `strict`, or `none` |
| `DOCUMENT_STORAGE_PATH` | No | `storage/documents` | Upload directory (relative to `backend/`); Git-ignored, never served publicly |
| `AI_PROVIDER` | No | none | `groq`; empty disables AI review |
| `GROQ_API_KEY` | No | none | Secret; keep only in `backend/.env` |
| `GROQ_MODEL` | No | `openai/gpt-oss-20b` | |
| `GROQ_REASONING_EFFORT` | No | `low` | `low`/`medium`/`high`, or empty to omit |
| `AI_MAX_OUTPUT_TOKENS` | No | `4000` | Counts toward provider rate limits |
| `AI_MAX_INPUT_CHARS` | No | `30000` | Contract characters sent to the AI |
| `AI_TIMEOUT_SECONDS` | No | `90` | |
| `AI_PLAYBOOK_PATH` | No | built-in | Optional JSON playbook |

`COOKIE_SAMESITE=none` requires `COOKIE_SECURE=true`. `.env` is ignored by Git;
never commit real credentials. Percent-encode special characters in the
password (`@` → `%40`, `:` → `%3A`, `/` → `%2F`, `#` → `%23`, `%` → `%25`).

## 4. Database migration

The initial migration has already been applied to the local database. For a
fresh database, run:

```powershell
alembic upgrade head
python scripts\check_db.py
```

No new migration is required for authentication or contracts: they use the
existing `users`, `user_sessions`, `contracts`, and `audit_events` tables.

## 5. Create the first user

```powershell
python scripts\create_user.py
```

The script prompts for full name, email, password, and password confirmation.
Passwords are entered with `getpass` and are never echoed. The first account is
assigned the `admin` role, which is allowed by the existing `ck_users_role`
constraint. Duplicate emails are rejected. No credentials are hardcoded.

There is intentionally no public registration endpoint.

## 6. Start the API

From `backend/`:

```powershell
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Swagger UI: `http://127.0.0.1:8000/docs`
- API health: `http://127.0.0.1:8000/health`
- Database health: `http://127.0.0.1:8000/health/db`

## 7. Endpoints

| Method | Path | Auth | Purpose |
|---|---|---|---|
| GET | `/health` | None | API process is running |
| GET | `/health/db` | None | PostgreSQL is reachable |
| GET | `/api/auth/csrf` | None | Set CSRF cookie and return its token |
| POST | `/api/auth/login` | CSRF | Validate credentials, create session cookie |
| POST | `/api/auth/logout` | CSRF | Delete session and clear cookies |
| GET | `/api/auth/me` | Session | Return the authenticated user |
| GET | `/api/contracts` | Session | List visible contracts (`q`, `status`, `contract_type`, `page`, `page_size`) |
| POST | `/api/contracts` | Session + CSRF | Create a draft contract |
| GET | `/api/contracts/{id}` | Session | Contract detail (404 missing, 403 not permitted) |
| PATCH | `/api/contracts/{id}` | Session + CSRF | Partial update, including status |
| POST | `/api/contracts/{id}/documents` | Session + CSRF (creator/admin) | Upload PDF/DOCX (max 10 MB) as the next version |
| GET | `/api/contracts/{id}/documents` | Session | List all versions, newest first |
| GET | `/api/documents/{id}` | Session | Version metadata and version history |
| GET | `/api/documents/{id}/download` | Session | Download a version (attachment) |
| GET | `/api/ai/status` | Session | Is AI review configured? (no secrets) |
| POST | `/api/contracts/{id}/reviews` | Session + CSRF | Run an AI review of the current document version |
| GET | `/api/contracts/{id}/reviews` | Session | Review history, newest first |
| GET | `/api/reviews/{id}` | Session | One review in full |

Login is JSON:

```json
{ "email": "admin@example.com", "password": "your-password" }
```

### Authentication flow

1. Call `GET /api/auth/csrf`; it sets the readable `clm_csrf` cookie and
   returns the same token.
2. Send the token in the `X-CSRF-Token` header to login or logout.
3. Login sets `clm_session` as an HttpOnly cookie containing the raw token.
   Only its hash is stored in PostgreSQL.
4. `/api/auth/me` validates the cookie, database session, expiry, and active
   account.
5. Login rotates the CSRF token and returns the new one; use it for logout.

The CSRF check is a double-submit cookie: the random cookie value must match the
request header. A cross-site attacker can cause a request but cannot read the
cookie and therefore cannot produce the matching header.

## 8. Test with PowerShell

Start the server first, then open another PowerShell window.

Health checks:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -UseBasicParsing
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health/db" -UseBasicParsing
```

Full login, `/me`, and logout flow (replace the placeholder email/password):

```powershell
$base = "http://127.0.0.1:8000"

$csrf = (
  Invoke-RestMethod -Uri "$base/api/auth/csrf" -SessionVariable web -UseBasicParsing
).csrf_token

$body = @{
  email = "admin@example.com"
  password = "YOUR_PASSWORD"
} | ConvertTo-Json

$login = Invoke-RestMethod `
  -Uri "$base/api/auth/login" `
  -Method Post `
  -Body $body `
  -ContentType "application/json" `
  -WebSession $web `
  -Headers @{ "X-CSRF-Token" = $csrf } `
  -UseBasicParsing

$login.user

$me = Invoke-RestMethod `
  -Uri "$base/api/auth/me" `
  -WebSession $web `
  -UseBasicParsing

$me | ConvertTo-Json

Invoke-RestMethod `
  -Uri "$base/api/auth/logout" `
  -Method Post `
  -WebSession $web `
  -Headers @{ "X-CSRF-Token" = $login.csrf_token } `
  -UseBasicParsing
```

After logout, `/me` should return `401 Unauthorized`. To inspect error bodies in
PowerShell 7, add `-SkipHttpErrorCheck`.

## 9. Tests

```powershell
python -m pytest -v
```

Tests use the real PostgreSQL database from `.env`. Each test runs inside an
outer transaction that is rolled back, so test users and sessions are not
persisted. SQLite is not used.

Coverage:

- API health and database health, including a simulated database failure.
- Successful login and hashed-session storage.
- Invalid password and unknown email.
- CSRF enforcement.
- Logout and cookie clearing.
- `/me` with a valid session, no session, and invalid session.
- Expired sessions and inactive users.
- Validation errors do not echo submitted passwords.
- AI review (84 tests, provider always mocked): text extraction (PDF, DOCX,
  scanned/empty/corrupt/mismatched files), Groq adapter via
  `httpx.MockTransport` (all error classes, no key leakage), factory and
  playbook, and the review API (persistence, version history, excerpt
  verification, failures, malformed replies, authentication, CSRF, permissions).
- Documents (31 tests): valid PDF/DOCX, invalid extension/MIME/content, empty
  and oversized files (10 MB boundary), nonexistent contract, CSRF and
  authentication, role/ownership access, version creation with old files kept,
  audit events, download headers and bytes, filename path traversal, tampered
  stored path, and a missing stored file. Files go to a temp directory.
- Contracts: creation with server fields and audit event, unique numbers,
  rejected client-supplied system fields, validation, auth and CSRF
  enforcement, search/filter/pagination, role and ownership access, detail and
  404, update audit diffs, no-op updates, invalid updates, and audit history
  surviving contract deletion.

Actual result (2026-11-24):

```text
150 passed, 1 warning in 25.81s
```

The one warning is an upstream Starlette `TestClient`/`httpx` deprecation; it
does not affect the API. A live Uvicorn smoke test also returned:

```text
GET /health: 200 {'status': 'ok'}
GET /health/db: 200 {'status': 'ok', 'database': 'ok'}
GET /api/auth/csrf: 200
GET /api/auth/me (no session): 401
POST /api/auth/login (unknown user): 401
```

No test users or session rows remained after the run.

## 10. Security notes

- Passwords use Argon2id through `pwdlib`; plaintext passwords are never stored.
- Session tokens use `secrets.token_urlsafe(32)` (256 bits) and only SHA-256
  hashes are stored.
- The session cookie is always HttpOnly. `Secure` and `SameSite` are
  environment-controlled.
- Login errors are generic, and a dummy Argon2 verification reduces email
  enumeration through timing.
- Inactive accounts cannot log in; existing sessions are deleted when a
  disabled user is encountered.
- Auth responses send `Cache-Control: no-store`.
- No registration endpoint or client-selected roles exist.
- Not yet implemented: login rate limiting, account lockout, auth audit
  logging (contract changes are audited), session cleanup for rows that are never presented, email verification, and
  password reset. These should be addressed before production use.
- For deployment, serve over HTTPS, set `COOKIE_SECURE=true`, and use an
  appropriate `COOKIE_SAMESITE` policy. CORS is not configured because there is
  no frontend yet.

## 11. Troubleshooting

- `no pq wrapper available` or `DLL load failed while importing pq`: install
  the PostgreSQL client tools and ensure `C:\Program Files\PostgreSQL\18\bin`
  is on `PATH`, or allow the psycopg binary wheel.
- `DLL load failed while importing _collections_cy`: keep the pinned
  SQLAlchemy 2.0 line so it uses the pure-Python fallback.
- `401 Not authenticated`: log in again; sessions expire after
  `SESSION_TTL_MINUTES` and logout deletes the database row.
- `403 CSRF validation failed`: call `GET /api/auth/csrf` again and send its
  token in `X-CSRF-Token`. Login and logout both require it.
- `uvicorn` not found: activate `.venv` or run
  `.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload`.
