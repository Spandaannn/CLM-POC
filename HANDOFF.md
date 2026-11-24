# CLM POC — Handoff

**Date:** 2026-11-24
**Current phase:** Step 7 — Contract Management complete.
**Status:** Authentication, frontend shell, and contract metadata management
(create, list, search/filter, detail, edit, authorization, audit events) are
implemented and verified end to end. Document, review, and approval features
remain unimplemented.

## Verified status (Step 7, 2026-11-24)

| Check | Command | Result |
|---|---|---|
| Backend tests | `python -m pytest -q` | **35 passed** (15 auth/health + 20 contracts), 1 upstream warning |
| Migration | `python -m alembic current` | `20261123_0001 (head)` — no new migration needed |
| Frontend lint | `npm run lint` | exit 0, 4 `set-state-in-effect` warnings (data-fetching effects) |
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

The real database password stays in `backend/.env`, which is Git-ignored.

### Frontend (`frontend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Empty means same-origin through the Vite proxy |

Vite variables are public; never put secrets in them.

## Known limitations

- **No document, review, or approval functionality.** The dashboard
  placeholders are informational only. Status changes are free-form (any
  status → any status) until approval workflow rules exist.
- **No contract deletion** endpoint or UI.
- **Contract audit events are written but not shown in the UI.**
- **Git:** a local repository was initialised on 2026-11-24 with no commits
  and no remote. `.gitignore` excludes `.env`, `.venv`, `node_modules`,
  `dist`, caches, and key files.
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

1. Add PDF/DOCX upload, versioning, and authorized downloads.
2. Implement review findings and approval workflows (including status
   transition rules).
3. Show contract audit history on the detail page.
4. Add frontend tests (Vitest + React Testing Library, optionally Playwright).
5. Add production deployment: same-origin static hosting, HTTPS, secure cookies,
   rate limiting, and auth audit logging.
