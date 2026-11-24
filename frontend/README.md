# CLM Frontend — React + Vite

The frontend for the CLM proof of concept: application shell, session-based
sign-in, protected routing, a dashboard, and contract management (list with
search/filters/pagination, create, detail, edit). Document, review, and approval
features are **not implemented** yet.

## Contract screens (Step 7)

| Route | Page | Notes |
|---|---|---|
| `/contracts` | `ContractsPage` | Real API data; search, status/type filters, pagination kept in the URL; loading, error (retry), empty and no-match states |
| `/contracts/new` | `NewContractPage` | Client-side validation mirrors the API; new contracts start as drafts |
| `/contracts/:id` | `ContractDetailPage` | 404 / 403 / connection-error states; Edit shown only to creator or admin; includes the Documents section |
| `/contracts/:id/edit` | `EditContractPage` | Same form plus status; server still enforces permissions |

### Documents (Step 8)

`components/DocumentsSection.tsx` (on the detail page): upload PDF/DOCX
(client checks mirror the server: type, non-empty, 10 MB), version-history table
with Current/Older badge, size, upload date and uploader, and a Download button.
Loading, error-with-retry, empty, success, and error states. Uploads send
`FormData` through the CSRF helper (`api/documents.ts`); downloads fetch a blob
with the session cookie so errors show inside the page. Data hook:
`lib/useDocuments.ts`; validation: `lib/documentFile.ts`.

Shared pieces: `api/contracts.ts` (calls), `api/csrf.ts` (CSRF-protected
mutations with one retry), `components/ContractForm.tsx`, `lib/contractForm.ts`
(form ↔ API conversion).

## Stack

- React 19 + TypeScript
- Vite 8
- React Router 7
- Plain CSS with CSS variables
- Native Fetch API

No UI framework, state library, or form library is used.

## Project structure

```text
frontend/
├── index.html
├── vite.config.ts              # /api and /health proxy to FastAPI
├── .env.example
├── public/
│   ├── favicon.svg
│   └── robots.txt
└── src/
    ├── main.tsx                # React root
    ├── App.tsx                 # AuthProvider + RouterProvider
    ├── router.tsx              # Public/protected routes
    ├── api/
    │   ├── client.ts           # fetch wrapper, credentials, errors
    │   ├── auth.ts             # CSRF, login, logout, /me
    │   └── types.ts            # Backend response types
    ├── auth/
    │   ├── authContext.ts      # Context and types
    │   ├── AuthProvider.tsx    # Session restoration and actions
    │   ├── useAuth.ts
    │   └── RequireAuth.tsx     # Protected-route guard
    ├── components/
    │   ├── Alert.tsx
    │   ├── AppShell.tsx
    │   ├── Button.tsx
    │   ├── Spinner.tsx
    │   └── TextField.tsx
    ├── lib/
    │   ├── errors.ts
    │   ├── format.ts
    │   └── navigation.ts
    ├── pages/
    │   ├── DashboardPage.tsx
    │   ├── LoginPage.tsx
    │   └── NotFoundPage.tsx
    └── styles/
        ├── tokens.css
        └── global.css
```

## Prerequisites

- Node.js 20 or newer (verified with Node 26.7.0 and npm 11.19.0)
- The backend running at `http://127.0.0.1:8000`
- A user account created with `backend/scripts/create_user.py`

## Install

From `frontend/`:

```powershell
npm install
```

## Run the backend and frontend

Use two PowerShell terminals.

**Terminal 1 — backend:**

```powershell
cd C:\Users\Spandan\Projects\OpenCode\Demo-CLM\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

If activation is blocked, run:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend:**

```powershell
cd C:\Users\Spandan\Projects\OpenCode\Demo-CLM\frontend
npm run dev
```

Open **http://localhost:5173** in the browser.

> Use `localhost`, not a mix of `localhost` and `127.0.0.1`. Cookies are scoped to
> the host name, so mixing them can make the session cookie appear missing.

### Why there is no CORS setup

The browser only talks to Vite on port 5173. Vite proxies `/api` and `/health` to
FastAPI on port 8000, so requests are same-origin and the session cookie works.
The proxy is configured in `vite.config.ts` for both `dev` and `preview`.

For production, serve the built `dist/` folder and the API behind the same origin
(or configure CORS and `COOKIE_SECURE` deliberately). Do not use a wildcard CORS
origin with credentialed requests.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Empty means same-origin through the Vite proxy |

Copy `.env.example` to `.env` only if you need to override the API origin. Vite
variables are public and must never contain secrets.

The backend must use `COOKIE_SECURE=false` while testing over plain HTTP on
localhost. Set it to `true` when serving over HTTPS.

## Authentication flow

1. `GET /api/auth/me` runs on first load. A `401`/`403` means signed out; other
   errors show a retryable connection problem.
2. `GET /api/auth/csrf` sets the readable `clm_csrf` cookie and returns the same
   token in JSON.
3. `POST /api/auth/login` sends the token in `X-CSRF-Token` with the email and
   password. The server sets the HttpOnly `clm_session` cookie and rotates the
   CSRF token.
4. The rotated CSRF token is kept in a module-level variable in `src/api/auth.ts`,
   never in `localStorage` or `sessionStorage`.
5. Protected routes call `GET /api/auth/me`; signed-out users are redirected to
   `/login?returnTo=<path>`.
6. `POST /api/auth/logout` sends a CSRF token, deletes the server-side session,
   and clears both cookies.
7. After a page refresh the in-memory CSRF token is gone, so logout or login
   fetches a fresh one automatically. This is intentional.

The session token is never readable by JavaScript because the cookie is
HttpOnly. The CSRF cookie is readable by design, but the token is still not
persisted in browser storage.

## Scripts

```powershell
npm run dev      # Vite development server on 5173
npm run build    # TypeScript check + production build
npm run lint     # oxlint
npm run preview  # preview the production build on 4173
```

## Manual test steps

1. **Protected route while signed out**
   - Open `http://localhost:5173/dashboard`.
   - Expected: redirected to `/login?returnTo=%2Fdashboard`.

2. **Invalid login**
   - Enter a valid email with the wrong password.
   - Expected: "Invalid email or password"; no session is created.

3. **Successful login**
   - Sign in with the account created by the administrator.
   - Expected: dashboard shows the real name, email, role, active status, and
     member-since date.
   - The Contracts, Documents, AI Reviews, and Approvals cards are clearly marked
     "Not implemented yet".

4. **Refresh**
   - Press F5 on the dashboard.
   - Expected: the dashboard reloads and the same user remains signed in.

5. **Authenticated login route**
   - While signed in, open `http://localhost:5173/login`.
   - Expected: redirected back to the dashboard.

6. **Logout**
   - Click **Sign out** (also test after a refresh).
   - Expected: return to the login page, and navigating to `/dashboard` redirects
     to login again.

7. **Browser storage and cookies**
   - Open DevTools → Application.
   - Expected: `localStorage` and `sessionStorage` contain no auth tokens.
   - Cookies: `clm_session` is HttpOnly; `clm_csrf` is readable.

8. **Return-to flow**
   - Sign out, open `/dashboard`, sign in.
   - Expected: after login you land on `/dashboard`, not a generic page.

9. **Backend unavailable**
   - Stop the backend and reload a protected page.
   - Expected: "Unable to check your session" with a **Try again** button, not a
     false sign-out.

## Verification performed

### Step 8 — documents (2026-11-24)

`npm run lint` -> exit 0, 0 warnings; `npm run build` -> exit 0, 56 modules.
Browser-verified: empty state, client-side rejection of wrong type / empty /
over-10 MB files, PDF upload (v1), DOCX upload (v2), version history, download
of an older version (exact bytes, original filename), server rejection message,
missing-file message, and phone width. No automated UI tests for documents yet.

### Lint-warning fix (2026-11-24)

`npm run lint` → exit 0, 0 warnings; `npm run build` → exit 0, 52 modules.
The four `set-state-in-effect` warnings were removed by deriving loading state
from request-tagged results (`lib/useContract.ts`, `ContractsPage`) and keying
the filter form by the URL query. Browser re-check: search, URL filters,
back/forward, Clear, detail, edit, 404, and Try again all behave as before.

### Step 7 — contracts (2026-11-24)

```text
npm run lint   -> exit 0, 4 warnings (react set-state-in-effect in the
                  data-fetching effects of the three contract pages)
npm run build  -> exit 0, 51 modules, JS 348.22 kB (107.56 kB gzip)
```

- Live API smoke test through the Vite proxy: **20/20 passed** (unauth 401,
  create 201, CSRF 403, date validation 422, search, status and type filters,
  detail, update, cross-user 403 on view/edit, list isolation, audit events,
  logout).
- Browser: protected `/contracts` → login with `returnTo` → empty state →
  create contract → detail with success banner → edit title and status →
  filtered list shows the updated row → dashboard → sign out → redirect.
- Temporary verification accounts and their contracts/audit rows were deleted.

### Step 6 — shell and authentication

Actual results on 2026-11-24:

```text
npm run lint   -> exit 0, no warnings
npm run build  -> exit 0
                  42 modules transformed
                  JS  327.45 kB (103.26 kB gzip)
                  CSS  14.10 kB (3.63 kB gzip)
```

Integration checks ran through the Vite proxy against the real FastAPI backend
and PostgreSQL:

- **37 checks passed**, including:
  - `/health` and `/health/db` through the proxy.
  - Unauthenticated `/api/auth/me` → 401.
  - CSRF cookie/token matching.
  - Login without CSRF → 403.
  - Wrong password → 401 and no session cookie.
  - Successful login with the real user payload.
  - HttpOnly `clm_session`, `SameSite=Lax`.
  - Rotated CSRF token matching the new cookie.
  - `/api/auth/me` with the session cookie → 200.
  - Logout with a bad CSRF token → 403 and session stays active.
  - Proper logout → 204, cookies cleared, old token rejected.
- Browser checks:
  - Wrong-password error displayed.
  - Successful login reached `/dashboard`.
  - Dashboard showed the actual name, email, and role.
  - Refresh restored the session.
  - `/login` redirected to `/dashboard` while authenticated.
  - Logout after refresh worked (CSRF token re-fetched).
  - Protected route redirected to `/login?returnTo=%2Fdashboard`.
  - Return-to login landed on `/dashboard`.
  - No `localStorage`/`sessionStorage` keys; only `clm_csrf` visible to
    JavaScript.
- Lighthouse on both the login page and dashboard:
  - Accessibility **100**
  - Best Practices **100**
  - SEO **100**

The temporary verification account and its sessions were deleted afterwards.
The database returned to **1 user** (the existing administrator) and **0**
sessions. No fake users or contract data are shipped in the UI.

## Known limitations

- No document, review, or approval functionality yet; contracts cannot be
  deleted from the UI.
- Contract data is fetched in effects with derived loading state
  (`lib/useContract.ts`, `ContractsPage`); there is no client-side cache.
- No automated frontend unit/component tests; verification used build, lint,
  HTTP integration checks, and browser checks.
- Responsive CSS is implemented, but no physical mobile-device test was run.
- There is no CORS configuration because the Vite proxy keeps development
  same-origin.
- Production hosting (serving `dist/` and `/api` from one origin) is not set up.
- Session expiry while sitting idle on the dashboard is not polled; the next
  full load or authenticated request would detect it.
- No dark mode, internationalization, or offline support.
