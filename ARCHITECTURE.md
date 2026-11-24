# CLM POC — Architecture v1

## 1. Project overview

This project is a Contract Lifecycle Management (CLM) proof of concept for a Legal Department. It will support contract uploads, structured contract records, review workflows, basic approvals, and AI-assisted review.

This document describes the proposed architecture, not a statement that every feature has already been implemented. The supplied architecture diagram defines the core stack; the implementation choices below provide practical defaults.

### Initial scope
- User login and logout.
- Role-based access to contract records and documents.
- Upload and download of PDF and DOCX files.
- Contract metadata, document versions, and workflow status tracking.
- AI-assisted summaries and review findings, subject to human review.
- Basic audit logging.

## 2. Selected technology stack

| Layer | Selected technology | Notes |
|---|---|---|
| Frontend | React + Vite | Browser-based application |
| Backend | Python + FastAPI | REST API, validation, workflows, authentication, authorization |
| Database | PostgreSQL | Structured records, sessions, metadata, review results, audit events |
| File storage | Local filesystem | POC document storage on a persistent backend volume |
| AI provider | Groq or Gemini | Final provider and model remain TBD |
| Authentication | Server-side sessions | Opaque session ID in an HttpOnly cookie |
| Database access | SQLAlchemy + psycopg | Proposed implementation choice |
| Database migrations | Alembic | Proposed implementation choice |

## 3. Architecture and component responsibilities

```text
Browser: React + Vite
        |
        | REST API over HTTPS
        | JSON / multipart uploads / session cookie
        v
Python + FastAPI
        |
        +-- SQLAlchemy + psycopg --> PostgreSQL
        +-- File storage service --> Local persistent document storage
        +-- AI service adapter ---> Groq or Gemini API over HTTPS
        +-- Authentication -------> Server-side sessions in PostgreSQL
```

- Frontend: displays forms, contract lists, document actions, review findings, and approval screens; calls backend endpoints and presents results.
- Backend: validates input, enforces access control, implements workflows, reads and writes records, handles documents, and invokes AI services.
- PostgreSQL: stores structured application data and links between users, contracts, document versions, reviews, and approvals.
- Local storage: holds the actual PDF and DOCX bytes, outside any publicly served directory.
- AI service: generates draft summaries, identifies possible risks, and suggests language; it does not approve or modify contracts autonomously.
- Session authentication: runs within the backend; it is not a separate deployed service in this POC.

## 4. Frontend-to-backend communication

The React frontend calls versioned REST endpoints such as `/api/v1/contracts` using Fetch or an equivalent HTTP client.

- JSON is used for metadata requests and responses.
- `multipart/form-data` is used to upload contract files.
- Authenticated downloads return file content from an authorized backend endpoint.
- Responses include appropriate HTTP status codes and consistent error messages.
- Frontend requests include `credentials: "include"` when cookies are required.

Example:

```javascript
const response = await fetch('/api/v1/contracts', {
  credentials: 'include'
});
if (!response.ok) throw new Error('Unable to load contracts');
const contracts = await response.json();
```

During development, use Vite's `/api` proxy to FastAPI, or explicitly allow the frontend origin with credentialed CORS. Do not use a wildcard origin with credentialed requests. Prefer a same-origin reverse proxy for deployment. CORS is not authentication or authorization.

## 5. Backend-to-PostgreSQL communication

FastAPI uses SQLAlchemy with the psycopg PostgreSQL driver. A database connection string is supplied through backend configuration, not browser code.

Request flow:

```text
API request -> validate input -> check access -> service logic
            -> SQLAlchemy query/transaction -> PostgreSQL -> response
```

- Use a database session per request or unit of work, with connection pooling.
- Commit successful transactions; roll back failures and always close sessions.
- Use ORM queries or parameterized SQL rather than concatenating user input into SQL.
- Use Alembic migrations to version schema changes.
- A SQLAlchemy database session is different from a user's login session.

### Proposed core tables

| Table | Purpose |
|---|---|
| users | User identity, password hash, role, active status |
| sessions | Hashed session identifier, user reference, creation, expiry, revocation |
| contracts | Title, counterparty, owner, status, dates, other metadata |
| contract_documents | Contract reference, version, storage key, original name, type, size |
| review_results | Contract/document reference, provider, model, playbook version, findings |
| approvals | Contract reference, approver, decision, comments, timestamps |
| audit_events | Actor, action, target, timestamp, relevant change details |

Primary keys identify individual records. Foreign keys link related records; for example, `contract_documents.contract_id` references `contracts.id`.

## 6. Contract file storage

For the POC, document bytes are stored on the backend's local filesystem, while metadata and storage keys are stored in PostgreSQL. Documents do not strictly require separate storage, but this separation keeps structured queries distinct from file handling and simplifies a future S3 migration.

Upload flow:
1. Authenticate the user and authorize the upload.
2. Validate allowed file types, file content where feasible, and size limits.
3. Generate a server-controlled storage key; never use a user-supplied path.
4. Store the file outside the public web directory on a persistent volume.
5. Insert its metadata and contract/version relationship into PostgreSQL.
6. Record an audit event and clean up the file if the database operation fails.

Example storage key: `contracts/<contract-id>/<document-id>.pdf`.

**Implemented (Step 8):** the flow above is live for PDF and DOCX up to 10 MB. The storage root is `DOCUMENT_STORAGE_PATH`; `contract_documents.storage_path` holds the key relative to it, so internal paths are never exposed. Validation checks extension, declared MIME type, and file signature (`%PDF-`, or a zip containing `[Content_Types].xml` and `word/document.xml` with size/entry limits). Versioning uses the existing table: one logical document per contract, one row per version, `version_number` assigned under a row lock, exactly one `is_current` row (enforced by a partial unique index), older rows and files kept. Uploads are limited to users who may edit the contract; viewing and downloading follow contract visibility. See HANDOFF.md for details and limitations (no malware scanning, one document per contract, no deletion).

Downloads must pass backend authorization before the file is returned. New document versions receive new files and records rather than silently overwriting earlier versions. Files and database backups must be coordinated. Local storage is suitable for a single-instance POC but requires redesign for multiple backend instances.

## 7. AI integration

Only FastAPI communicates with Groq or Gemini. Provider API keys remain in backend environment configuration or a secret manager, never in React code.

**Implemented (Step 9, Groq):** `app/ai/` holds a provider-independent layer (`AIProvider` interface, safe error types, factory) with Groq isolated in `app/ai/groq.py`; adding Gemini means one new adapter and a factory entry. A review is started only by an explicit authenticated, CSRF-protected `POST /api/contracts/{id}/reviews` (never on upload) and covers the contract's current document version. The backend extracts text locally (PDF via `pypdf`, DOCX via standard-library XML; no OCR), builds a prompt that treats the contract text as untrusted data and tells the model which party is "us" (the party that is not the recorded counterparty), requests one JSON object, validates it against an application schema, verifies each quotation against the real text (unmatched quotes are dropped), and stores structured results in `review_results` with the document id and version, provider/model, playbook version, and initiating user. Raw AI replies, prompts, and contract text are not stored or logged; audit events (`ai_review.completed` / `ai_review.failed`) carry only identifiers and error codes. Playbook rules come from a configurable JSON file; the shipped baseline is illustrative, not an approved company policy, and its results are shown separately from AI observations. Provider failures (missing configuration, invalid credentials, 429, timeout, unavailable model, oversized request, malformed or cut-off reply) become generic user-safe errors. Provider rate limits apply: Groq's free tier counts prompt plus requested output tokens against 8,000 per minute. See HANDOFF.md for configuration and limitations.

Review flow:
1. Verify the user can access the requested document.
2. Extract text from PDF or DOCX; scanned PDFs require OCR, which is outside the initial scope unless added.
3. Build a prompt containing the review task, necessary contract text, and applicable playbook rules.
4. Send the request to the selected provider over HTTPS through a provider adapter.
5. Validate the response against an application schema before storing or displaying it.
6. Save findings with the document version, provider/model, prompt or playbook version, and review timestamp.
7. Present findings as suggestions for a human legal reviewer.

Initial output may include a summary, missing clauses, possible risks, suggested changes, and clause references where available. Model outputs can be incorrect and must not be treated as authoritative legal advice or approval.

Configure request timeouts, bounded retries, size limits, and cost controls. Treat contract text as untrusted input, not instructions. Do not send confidential contracts to an external provider until its retention, training-use, and privacy terms are approved. A long-running review should return a job identifier once background processing is introduced.

## 8. Session authentication and authorization

Use server-side sessions with a random, opaque session ID. Store session records in PostgreSQL initially; use a mature authentication/session implementation where practical rather than designing cryptographic mechanisms.

Login flow:
1. The browser sends credentials to `POST /api/v1/auth/login` over HTTPS.
2. FastAPI verifies the account and password against a stored password hash.
3. The backend creates a fresh session and stores a hash of its random identifier with the user ID and expiry.
4. The backend sets the raw session ID in an `HttpOnly` cookie.
5. The browser sends the cookie with subsequent requests.
6. FastAPI resolves the session, rejects expired or revoked sessions, and checks current user permissions.

Production cookie example:

```http
Set-Cookie: __Host-clm_session=<opaque-id>; Path=/; HttpOnly; Secure; SameSite=Lax
```

- Use HTTPS in deployment; any HTTP-only localhost exception must stay confined to development.
- Apply CSRF protection to state-changing requests; SameSite is an additional defense, not the only one.
- Configure inactivity and absolute timeouts, rotate sessions after login or privilege elevation, and revoke them on logout or account disablement.
- On logout, revoke the server-side session and clear the cookie.
- Never store session identifiers in localStorage or expose them to application JavaScript.
- Rate-limit login attempts and store passwords using a maintained Argon2id password-hashing implementation.
- Recheck permissions server-side on every protected endpoint, including downloads and AI review requests.

### Proposed POC roles

| Role | Example permissions |
|---|---|
| Business User | Create requests, upload documents, view authorized contracts |
| Legal Reviewer | Review assigned contracts, record findings, recommend changes |
| Legal Approver | Approve or reject contracts within assigned authority |
| Administrator | Manage users, roles, and configuration |

Roles alone are insufficient: enforce contract ownership, assignment, and organizational boundaries as applicable. Administrative access must not automatically bypass all document restrictions unless explicitly required.

## 9. Future improvements

| Improvement | Purpose |
|---|---|
| S3 or compatible object storage | Durable shared document storage, versioning, controlled signed downloads |
| SSO via OpenID Connect or SAML | Enterprise identity integration; retain a browser session where appropriate |
| MFA | Additional protection for privileged actions and sensitive accounts |
| Redis-backed sessions | Shared low-latency session storage for multiple backend instances |
| Background task queue | Reliable AI review, extraction, OCR, and notification jobs |
| OCR | Text extraction from scanned contracts |
| E-signature integration | Send agreements for signature and track execution |
| Obligation and renewal tracking | Owners, deadlines, reminders, escalation |
| Enhanced audit logging | Restricted access, integrity controls, retention, export |
| Malware scanning | Safer handling of uploaded files |
| Multi-tenancy | Strong organization-level data isolation |
| Observability and recovery | Centralized logs, metrics, alerts, backups, tested restores |

## 10. Reference notes

Core stack: supplied CLM POC architecture diagram.

Implementation guidance:
- FastAPI SQL database tutorial: https://fastapi.tiangolo.com/tutorial/sql-databases/
- OWASP session management guidance: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- Groq API reference: https://console.groq.com/docs/api-reference
- Gemini API reference: https://ai.google.dev/api/generate-content
