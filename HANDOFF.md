# CLM POC — Handoff

**Date:** 2026-11-25
**Current phase:** Step 10 — Contract Approval Workflow implemented (uncommitted).
**Status:** Authentication, contract management, versioned PDF/DOCX documents,
Groq-powered AI review, and a two-stage approval workflow (Legal Reviewer, then
Legal Approver, with request-changes, rejection, resubmission cycles, and full
history) are implemented and verified. Obligations remain unimplemented.

## Step 10 — Contract approval workflow (2026-11-25)

### Verified results (all actually run)

| Check | Result |
|---|---|
| `python -m pytest -q` | **203 passed** (150 from Steps 5-9 + 53 new in `tests/test_approvals.py`), 1 upstream warning, on a database that also held the user's manual-test data |
| `python -m alembic check` | "No new upgrade operations detected"; `alembic current` = `20261125_0003 (head)` |
| `npm run lint` | exit 0, 0 warnings |
| `npm run build` | exit 0, 64 modules, JS 385.81 kB (116.02 kB gzip) |
| Browser (3 temporary accounts, since deleted) | invalid submit (no document) refused; submit; locked state; mandatory-comment validation; request changes; creator edit + upload v2 + resubmit (cycle 2, history kept); recommend; final-approve confirmation incl. Cancel; Approved end state; approved contract edit page (content read-only, lifecycle status saved); rejection path (danger confirm, required comment, Rejected end state); dashboard queue |
| Frontend tests | none (the project has no test runner); verified by the documented browser run above |
| Data after checks | 1 user, the `abc` contract, 0 approval cycles; test users/contracts/files removed; the user's own manual-test documents and AI reviews untouched |

### Workflow

1. The creator (or an admin) prepares a contract in **Draft** and uploads a
   document, then **submits** it choosing an active Legal Reviewer and an active
   Legal Approver. The contract becomes **Pending review** and is locked.
2. The **Legal Reviewer** (assigned user, or admin) can **recommend approval**
   (moves to the approver), **request changes** (comment required), or **reject**
   (comment required).
3. The **Legal Approver** (assigned user, or admin) can **approve** (comment
   optional), **request changes** (comment required), or **reject** (comment
   required). Approval sets the contract to **Approved**.
4. After "changes requested" the contract returns to **Draft**; the creator can
   edit and upload again, then **resubmit**, which starts a **new cycle**
   (reviewer/approver can be chosen again). Earlier cycles stay in the history.
5. Rejection is final.

State machine (one row per cycle in `approval_cycles`):

```text
(submit)   -> pending_reviewer --recommend--> pending_approver --approve--> approved
                  |  request_changes / reject      |  request_changes / reject
                  v                                v
        changes_requested (-> contract Draft, creator may RESUBMIT = new cycle)
        rejected          (-> contract Rejected, final)
```

| Cycle status | Contract status |
|---|---|
| (never submitted) / `changes_requested` | `draft` |
| `pending_reviewer`, `pending_approver` | `pending_review` |
| `approved` | `approved` |
| `rejected` | `rejected` |

### Business rules (enforced on the server)

- Only the creator or an admin can submit/resubmit (same rule as editing).
- Only the assigned Legal Reviewer or an admin acts at the reviewer stage; only
  the assigned Legal Approver or an admin acts at the approver stage. An
  assignee whose role has since changed loses the assignment.
- Reviewer and approver must be **different, active** users with roles
  `legal_reviewer` / `legal_approver` (admins are not assignable). The creator and
  the submitter can never be assigned.
- **The creator can never decide on their own contract**, even if they are an
  admin. Nobody who recommended in a cycle can also give that cycle's final
  approval (matters for admin overrides).
- Request-changes and reject need a comment of at least 10 characters; approve,
  recommend and submit comments are optional. Max 2,000 characters.
- Invalid transitions return 409 (for example approving a rejected contract,
  recommending twice, resubmitting without requested changes). Order of checks:
  authentication, CSRF, contract visibility (403/404), state (409),
  authorisation (403), input (422).
- Every action locks the contract row (`SELECT ... FOR UPDATE`) and runs in one
  transaction; a partial unique index allows only one open cycle per contract.
- Each cycle records the **document version submitted**.
- Actions are append-only rows (cycle, sequence, type, stage, actor, comment,
  timestamp); earlier cycles are never modified. Audit events:
  `approval.submitted | resubmitted | recommended | changes_requested | rejected |
  approved` (entity type `approval`) with cycle number, stage and contract
  status change. Comments are kept in the action log, not in audit details.
- **AI review is advisory only**: nothing links AI reviews to approval state
  (tested).

### Changes to existing behaviour (deliberate)

- **A plain `PATCH /api/contracts/{id}` can no longer set `draft`,
  `pending_review`, `approved` or `rejected`** (previously any status could be
  set, which bypassed any workflow). Only `active`, `expired`, `terminated` can
  be set manually, and only once the contract is approved (409 otherwise).
- **Content can only be edited, and documents uploaded, while the contract is a
  Draft** (409 otherwise): pending review, awaiting final approval, approved,
  rejected, and later lifecycle states are fixed. An approved contract may still
  change lifecycle status.
- Two existing tests (`test_contracts.py`) set `pending_review` through PATCH;
  they were updated (one now sets that state directly in the database, one no
  longer edits status).
- The contract edit form no longer offers workflow statuses; it shows a
  lifecycle status select for approved contracts with read-only content.
- Contracts whose status was set manually before this step (e.g. an `approved`
  contract with no approval history) show "Not submitted" and offer no actions.

### Database change (migration `20261125_0003`, additive)

Two new tables; the older `approvals` table is untouched and unused.

- `approval_cycles`: `contract_id`, `cycle_number` (unique per contract), `status`
  (check constraint), `reviewer_id`, `approver_id` (must differ), `submitted_by`,
  `document_id`/`document_version`, `submitted_at`, `completed_at`, timestamps;
  partial unique index `uq_approval_cycles_one_open`.
- `approval_actions`: `cycle_id`, `sequence` (unique per cycle), `action_type`,
  `stage`, `actor_id`, `comment`, `created_at`.
- Applied to the local database (`alembic upgrade head`). Downgrade drops both.

### API (all need a session; POST needs CSRF)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/contracts/{id}/approval` | Workflow status, every cycle (newest first) with actions, and `available_actions` for the caller |
| POST | `/api/contracts/{id}/approval/submit` | `{reviewer_id, approver_id, comment?}` — creator/admin; draft with a document |
| POST | `/api/contracts/{id}/approval/resubmit` | Same body — after changes were requested; new cycle |
| POST | `/api/contracts/{id}/approval/reviewer-action` | `{action: recommend\|request_changes\|reject, comment?}` |
| POST | `/api/contracts/{id}/approval/approver-action` | `{action: approve\|request_changes\|reject, comment?}` |
| GET | `/api/approvals/assignees` | Active reviewers and approvers that can be chosen |
| GET | `/api/approvals/summary` | Dashboard: awaiting my action, my contracts in the workflow, counts |

Changed: `PATCH /api/contracts/{id}` (status/content rules above) and
`POST /api/contracts/{id}/documents` (409 unless Draft).
`available_actions` is computed by the same function the endpoints use, so the UI
never offers something the server would refuse.

### Frontend

- **Approval workflow panel** on the contract detail page (above Documents and
  AI Reviews, which are unchanged): status badge, four-step progress, assigned
  reviewer/approver, cycle and submitted document version, waiting message, role
  based action buttons, submit/resubmit form (reviewer/approver pickers,
  optional note; resubmit prefilled), an inline confirmation panel for every
  decision (mandatory comment clearly marked; red warning for reject, notice for
  final approval; Cancel), and a per-cycle timeline with actor, role, time and
  comment. Loading, error (retry), empty and "no legal team" states.
- Documents section shows why uploads are paused; the Edit button hides when the
  contract is locked; the edit page explains the lock.
- **Dashboard**: new "Approval queue" panel (awaiting my action, my contracts in
  approval); stale "Not implemented yet" module cards corrected.
- New files: `api/approvals.ts`, `components/ApprovalSection.tsx`,
  `components/ApprovalSummaryPanel.tsx`; edited: `types.ts`, `format.ts`,
  `Button.tsx` (danger variant), `ContractForm.tsx`, `EditContractPage.tsx`,
  `ContractDetailPage.tsx`, `DocumentsSection.tsx`, `ContractFilesAndReviews.tsx`,
  `DashboardPage.tsx`, `global.css`.

### Backend files

New: `app/models/approval_cycle.py`, `app/schemas/approval.py`,
`app/services/approvals.py`, `app/api/approvals.py`,
`alembic/versions/20261125_0003_approval_workflow.py`,
`tests/test_approvals.py`. Edited: `app/models/enums.py`, `app/models/__init__.py`,
`app/models/contract.py`, `app/services/contracts.py` (status/content rules),
`app/api/documents.py`, `app/api/router.py`, `app/main.py`,
`tests/test_contracts.py`.

### Tests added (53)

Submission (success, comment, creator/admin only, document required, assignee
validation incl. inactive/wrong role/unknown/same person/creator, malformed
input, resubmit-vs-submit); reviewer and approver authorisation (assigned,
unassigned, admin, role changed, authentication, CSRF, visibility); creator and
admin-creator cannot decide; same person cannot recommend and approve; full
sequential workflow; request changes (reviewer and approver) and resubmission;
rejection at both stages (final); mandatory comments (none/blank/short/boundary);
duplicate and out-of-order transitions; one open cycle; three-cycle history kept
intact; audit events (order, actors, no comment text); failed actions leave no
trace; edit/upload locks, status bypass closed, lifecycle rules, unchanged fields
tolerated; document versioning across cycles; AI review leaves approval state
unchanged; assignees; dashboard summary. Queries are scoped to each test's own
contract.

### Step 10 limitations

- One reviewer and one approver per cycle (no multi-step matrices, delegation,
  reassignment, or due dates); an assignee cannot be changed mid-cycle (the
  workflow must be sent back and resubmitted).
- No notifications of any kind (email, in-app); users find work on the
  dashboard queue. No e-signature, SSO, or external integrations.
- After approval the content is fixed; there is no "amend an approved contract"
  flow (an admin cannot edit it either). Rejected contracts cannot be reopened.
- The contract page reloads after each action, so unsaved text in other panels
  (for example a chosen file) is lost.
- `GET /api/approvals/assignees` lists the legal team's names and emails to any
  signed-in user (needed for the submit form).
- Legal reviewers still cannot upload documents (creator/admin only).
- Admin override exists at both stages (with the creator/recommender exclusions).
- Contracts left in `pending_review` by the old free-form status edit have no
  cycle and cannot be progressed; the clause-level `approvals` table is unused.
- No automated frontend tests.

## Step 9 — AI contract review (2026-11-24)

### Verified results (all actually run)

| Check | Result |
|---|---|
| `python -m pytest -q` | **150 passed** (66 from Steps 5-8 + 84 new), 1 upstream warning, on the baseline database. The review and document tests (67) were also run while manual-test rows existed in the database and passed, after their queries were scoped to their own contract |
| `python -m alembic check` | "No new upgrade operations detected"; `alembic current` = `20261124_0002 (head)` |
| `npm run lint` | exit 0, 0 warnings |
| `npm run build` | exit 0, 61 modules, JS 368.64 kB (112.20 kB gzip) |
| Browser (temporary user, since deleted) | no-document state; upload does **not** start a review; loading state during analysis; full result view; history of 2 reviews with switching; upload of v2 flips earlier reviews to "Earlier version" with a notice; simulated rate-limit message; simulated "not configured" state (button disabled, rest of app works) |
| **Real Groq** | **Yes — see "Real Groq testing" below** (mocked tests never use the network) |
| Secrets | Real key found only in `backend/.env` (Git-ignored, untracked); scan of all 144 project files |
| Data after checks | 1 user, 1 contract (`CTR-2026-574921E2`), 0 documents, 0 reviews, 2 audit events (unchanged); test files removed |

### Real Groq testing (manual, distinct from the mocked suite)

A **fictional** services agreement (made-up parties, `.docx`) was uploaded to a
temporary contract and reviewed through the real UI with
`openai/gpt-oss-20b`.

- Review 1 succeeded in about 9 s. All sections were produced and every quoted
  excerpt was matched to the document. Two problems were found and fixed:
  the AI judged risks from the wrong party's perspective (it did not know which
  party is "us"), and the UI showed "INR INR 1,200,000".
- Review 2 failed with Groq **413** ("Request too large ... TPM limit 8000").
  Diagnosis with direct calls: Groq's free `on_demand` tier allows 8,000
  tokens per minute and counts *prompt tokens + the requested output cap*;
  the original 8,000-token cap alone consumed that budget. With a 4,500 cap the
  answer was cut off (reasoning tokens); with `reasoning_effort: low` it
  completed in about 1,900 tokens. Fixes: configurable `AI_MAX_OUTPUT_TOKENS`
  (default 4000), `GROQ_REASONING_EFFORT` (default `low`), and a cut-off answer
  (`finish_reason: length`) is now rejected instead of saved.
- Final review (final settings) succeeded in about 5 s with the correct
  "our organisation" perspective, 8 clauses, 5 risk findings and 10 playbook
  results. Two reviews were stored and shown in history before being deleted.
- In total about eight real requests were made (three completed reviews, the
  rest diagnostics of the free-tier limit), all with fictional text. Results
  vary between runs: the first review flagged the missing data-protection
  clause as a risk, the final one did not (the playbook comparison still marked
  it "Not met" in the first; always verify).

### What was built

Backend packages/modules:

- `app/ai/` — provider-independent layer: `base.py` (interface), `errors.py`,
  `groq.py` (the only Groq-specific code), `factory.py`, `playbook.py` +
  `baseline_playbook.json`, `prompts.py`.
- `app/services/text_extraction.py` — PDF (`pypdf`) and DOCX (standard-library
  XML) text extraction.
- `app/services/reviews.py`, `app/api/reviews.py`, `app/schemas/review.py`.

Endpoints (all need a session; POST also needs CSRF):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/ai/status` | `configured`, provider, model, message, `max_input_chars` — never a key |
| POST | `/api/contracts/{id}/reviews` | Run an AI review of the **current** document version (the only call that sends text to the AI) |
| GET | `/api/contracts/{id}/reviews` | History, newest first (counts, version, reviewer) |
| GET | `/api/reviews/{id}` | Full review |

Error mapping (generic, safe messages; provider bodies/keys never returned):
409 no document; 422 no extractable text or unreadable file; 429 provider
rate limit/quota; 413 document too large for provider limits; 503 AI not
configured; 504 timeout; 502 provider/auth/model/malformed or cut-off reply.
Statuses are checked in order: auth, CSRF, contract access, document exists,
configuration, extraction, provider call.

How a review works: current document version located (read-only) -> provider
configured? -> text extracted locally -> text cut to `AI_MAX_INPUT_CHARS` ->
Groq asked for one JSON object -> JSON validated (rejected, not stored, if
malformed or cut off) -> every quotation checked against the real text (a
quote that cannot be found is dropped and labelled "not verified") -> stored
with the exact document id **and version**, plus a `ai_review.completed` audit
event. Failed attempts that reached the provider write `ai_review.failed` with
only an error code. Contract text, prompts, raw AI replies and keys are never
stored or logged.

Content of a review: executive summary (overview, parties, commercial terms,
key dates/obligations); metadata (parties, effective/expiry date, value and
currency, governing law, renewal terms; unknown = `null`, shown as "Not found
in the document"); clauses (payment, termination, confidentiality, indemnity,
limitation of liability, IP, data protection, dispute resolution, governing
law, renewal); risk findings (title, description, severity low/medium/high/
critical, category, concern, suggested action, verified excerpt — labelled
"AI observations"); playbook comparison (one row per configured rule: met /
partially met / not met / not assessed — labelled "Configured rules").
Page and clause numbers are deliberately not produced.

Playbook: none existed, so `app/ai/baseline_playbook.json` (10 rules) ships as
an **illustrative baseline, not an approved company legal policy**; this is
stated in the data, the API and the UI. Replace it with `AI_PLAYBOOK_PATH`
(same JSON shape). Rule titles/requirements are copied into each stored review,
so history stays accurate if the playbook is edited later (restart the backend
after editing — playbooks are cached).

Perspective: the model is told "our organisation" is the party that is **not**
the contract's recorded counterparty. If the counterparty field is wrong or
missing from the text, risk direction can be wrong — keep it accurate.

Permissions: anyone who can **view** a contract can start and read its reviews
(business users: their own contracts; reviewers/approvers/admins: all). Nothing
is sent to the AI for anyone else. A review never changes a contract, its
status, or its document.

### Database change (migration `20261124_0002`)

`review_results` could not hold the requested data (it had only `contract_id`,
`document_id`, `provider`, `model`, `review_type`, `summary`, `findings`), so
an additive migration was required. Applied to the local database
(`alembic upgrade head`); existing rows (none) get safe defaults. Reused:
`findings` (risk findings), `summary` (overview), `provider`, `model`,
`review_type` (`full_review`), `document_id`, `created_at`.

Added columns: `document_version` (int), `status` (`completed`|`failed`,
check constraint; only completed reviews are stored today, failures are in the
audit log), `initiated_by` (FK users, SET NULL, indexed), `summary_details`,
`extracted_metadata`, `clauses`, `playbook_results`, `source_info` (all JSONB
with defaults), `playbook_version`. The metadata column is named
`extracted_metadata` because `metadata` is reserved by SQLAlchemy. Downgrade
drops them.

### Configuration (`backend/.env`; never commit it)

| Variable | Default | Notes |
|---|---|---|
| `AI_PROVIDER` | none | `groq` is the only provider; empty = AI disabled, app unaffected |
| `GROQ_API_KEY` | none | Secret. Held as `SecretStr`, never returned or logged |
| `GROQ_MODEL` | `openai/gpt-oss-20b` | |
| `GROQ_REASONING_EFFORT` | `low` | `low`/`medium`/`high`; set empty for models without it |
| `AI_MAX_OUTPUT_TOKENS` | `4000` | Counts toward provider rate limits |
| `AI_MAX_INPUT_CHARS` | `30000` | Contract text sent; longer files are cut off and flagged |
| `AI_TIMEOUT_SECONDS` | `90` | |
| `AI_PLAYBOOK_PATH` | built-in | Optional JSON playbook |

Setup: add the variables to `backend/.env`, restart the backend, open a
contract with an uploaded document, and click **Run AI review of version N**.
`.env.example` documents the variables with an empty key.

### Supported documents and limits

PDF with a text layer and `.docx` (body text and tables; headers, footers,
comments and text boxes are not read). 10 MB file limit, 300 PDF pages, text
capped at 500,000 characters, then `AI_MAX_INPUT_CHARS` for the AI. Scanned or
image-only PDFs are reported as having no extractable text — **OCR is not
supported**. Encrypted PDFs and corrupted files are rejected with a clear
message. The stored file is only ever read.

### Files changed in Step 9

Backend (new): `app/ai/*` (7 files), `app/services/text_extraction.py`,
`app/services/reviews.py`, `app/api/reviews.py`, `app/schemas/review.py`,
`alembic/versions/20261124_0002_ai_review_fields.py`, `tests/helpers.py`,
`tests/test_text_extraction.py`, `tests/test_ai_provider.py`,
`tests/test_reviews.py`. Backend (edited): `app/models/review_result.py`,
`app/models/enums.py`, `app/core/config.py`, `app/api/router.py`,
`app/main.py`, `requirements.txt` (adds `pypdf`; `httpx` moved from dev to
runtime), `requirements-dev.txt`, `.env.example`, `tests/conftest.py`
(autouse fixture so no test can reach the real provider),
`tests/test_documents.py` (queries now scoped to the test's contract).
Frontend (new): `api/reviews.ts`, `lib/useApiResource.ts`,
`components/AiReviewsSection.tsx`, `components/ReviewView.tsx`,
`components/ContractFilesAndReviews.tsx`. Frontend (edited): `api/types.ts`,
`components/DocumentsSection.tsx` (takes shared document state),
`pages/ContractDetailPage.tsx`, `styles/global.css`. Docs: this file,
`README.md`, `ARCHITECTURE.md`, backend/frontend READMEs.

### Tests added (84)

Extraction (PDF, DOCX incl. tables, scanned/empty/tiny/corrupt/mismatched
files, DOCTYPE/entity DOCX, size cap, original file untouched); Groq adapter
via `httpx.MockTransport` (success, 401/403/404/413/429/5xx/timeouts, malformed
payloads, cut-off replies, key never in errors/repr/payload); factory and
playbook; and the review API with a **fake provider** (success for PDF and
DOCX, persistence, version association and history, excerpt verification,
value normalisation, truncation, no-document, scanned PDF, missing file, not
configured, all provider failures, malformed AI replies, audit events, no
content in logs/audit, no AI call on upload, authentication, CSRF, 404s,
stranger blocked with no provider call, reviewer allowed, contract unchanged,
`/api/ai/status` without secrets). No normal test uses the network or quota.

### Step 9 limitations

- **Provider limits:** on Groq's free tier a single request (prompt + output
  cap) must fit 8,000 tokens per minute, so only short contracts (roughly
  8,000 characters or less) can be reviewed; larger ones return the "too large
  for the provider's limits" message. A paid tier or a smaller
  `AI_MAX_INPUT_CHARS` changes this. Long documents are cut off at
  `AI_MAX_INPUT_CHARS` and the review is flagged as partial.
- **AI quality:** results vary between runs, can miss issues or misjudge them,
  and are never legal advice. Excerpts are verified verbatim; summaries,
  severities and suggestions are not.
- No OCR; DOCX headers/footers/comments not read; no page or clause numbers.
- Synchronous request (up to `AI_TIMEOUT_SECONDS`); no background queue,
  progress, or cancel. No per-user rate limit or cost control beyond the
  provider's. Business users can spend quota on their own contracts.
- Reviews are never run automatically and cannot be deleted. Failed attempts
  are audited but not shown in the UI. The review history is not exported.
- The baseline playbook is illustrative only.
- Contract text is sent to Groq on each review: confirm Groq's retention and
  data-use terms before using real contracts.
- The tests share the real database; this step's new tests (and the Step 8
  document tests) are scoped to their own contract so manual data cannot
  affect them. A dedicated test database is still recommended.

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
| `AI_PROVIDER`, `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_REASONING_EFFORT`, `AI_MAX_OUTPUT_TOKENS`, `AI_MAX_INPUT_CHARS`, `AI_TIMEOUT_SECONDS`, `AI_PLAYBOOK_PATH` | see Step 9 | AI review (optional). The key is a secret |

The real database password stays in `backend/.env`, which is Git-ignored.

### Frontend (`frontend/.env`)

| Variable | Default | Notes |
|---|---|---|
| `VITE_API_BASE_URL` | empty | Empty means same-origin through the Vite proxy |

Vite variables are public; never put secrets in them.

## Known limitations

- **No obligations functionality.** Approvals exist (Step 10); see its
  limitations above.
- **Contract status changes are server-enforced, not free-form.** `draft`,
  `pending_review`, `approved` and `rejected` are set only by the approval
  workflow (submit, recommend, request changes, reject, approve, resubmit). A
  plain edit may only move an already approved contract to `active`, `expired`
  or `terminated`. Contract content and document uploads are allowed only while
  the contract is a draft. See "Step 10 — Contract approval workflow".
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

1. Obligations and renewal tracking for approved/active contracts.
2. Show contract audit history on the detail page; in-app notifications for
   approvers.
3. Add frontend tests (Vitest + React Testing Library, optionally Playwright).
4. Allow reviewers to upload; consider several documents per contract
   (`document_group_id` migration) and document deletion.
5. Add production deployment: same-origin static hosting, HTTPS, secure cookies,
   rate limiting, and auth audit logging.
