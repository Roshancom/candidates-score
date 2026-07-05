# TechKraft Candidate Assessments

Internal web application for reviewing and scoring job candidates. Built with FastAPI (backend) and React (frontend), containerized with Docker Compose.

---

## 1. Setup and Run Instructions

### Prerequisites
- Docker & Docker Compose (recommended)
- OR Python 3.12+ / Node.js 18+ (for local development)

### Quick Start (Docker Compose)

```bash
# 1. Copy environment template (no real secrets — see "Credentials & Security" below)
cp .env.example .env

# 2. Launch both services
docker compose up --build
```

The containers will be available at:
- **Backend API**: http://localhost:8000
- **Frontend**: http://localhost:5173

### Default Credentials (auto-seeded on first startup)

| Email                 | Password      | Role     |
|-----------------------|---------------|----------|
| admin@techkraft.com   | admin123      | Admin    |
| reviewer@techkraft.com| reviewer123   | Reviewer |

### Local Development (without Docker)

**Backend:**
```bash
cd backend
source venv/bin/activate
JWT_SECRET_KEY=dev-secret-key uvicon app.main:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api` requests to `http://localhost:8000` (configured in `vite.config.js`).

### Running Tests

All 22 backend tests pass with no failures:

```bash
cd backend
source venv/bin/activate
python -m pytest tests/test_api.py -v
```

Frontend component tests:
```bash
cd frontend
npm run test
```

**Note:** 1 of 6 frontend component tests (`CandidateListPage.test.jsx` — the "hides pagination on single page" test) has a known vitest mock hoisting issue and does not pass in the Docker test environment. See `implementation.md` for details. The remaining 5 frontend tests pass.

---

## 2. Architecture Decision Record (ADR)

### ADR 1: JWT Authentication with Environment Variable Secret

**Context:** The initial implementation used a hardcoded secret key (`techkraft-secret-key-change-in-production`) in source code. This is insecure because anyone with repository access can forge tokens.

**Decision:** Moved `JWT_SECRET_KEY` to an environment variable with a module-level `raise RuntimeError` if unset. The backend raises an explicit error at startup rather than silently using a default. A `.env.example` file documents the required variable with instructions to generate a strong key via `openssl rand -hex 32`. Docker Compose passes the variable with a shell-default fallback for development convenience.

**Trade-off:** Adds a required environment variable, which adds friction for first-time setup (the app crashes immediately if omitted). Mitigated by providing clear error messages and the `.env.example` template. In production, this is correct behavior — fail-fast on missing secrets.

### ADR 2: SQLite as the Datastore

**Context:** The application manages candidate assessments with scoring, RBAC, notifications, and pagination — a workload that could scale to thousands of records. The choice of database affects deployment complexity, backup strategy, and concurrent read/write behavior.

**Decision:** Used SQLite via SQLAlchemy. Primary driver — zero infrastructure: no database server to install, configure, or manage. The entire database is a single file (`techkraft.db`) that ships with the repository, making `docker compose up` fully self-contained. SQLAlchemy's ORM abstraction keeps the option of migrating to PostgreSQL later without rewriting query code.

**Trade-off:** SQLite does not handle concurrent writes well (serializes at the file level). This is acceptable because the app is an internal tool with a small number of concurrent admin/reviewer users. At larger scale (>\~50 concurrent writers), migrating to PostgreSQL would be necessary. The `_paginate_query` helper and `_apply_candidate_filters` function are already written against SQLAlchemy's generic query API, so the migration path is straightforward.

### ADR 3: Server-Sent Events (SSE) over WebSockets for Notifications

**Context:** Reviewers need real-time updates when candidates are assigned or scores are submitted. Options included polling, Server-Sent Events (SSE), and WebSockets.

**Decision:** Used SSE (`sse_starlette` library) with a fallback to 30-second polling on the frontend. SSE was chosen because the communication is unidirectional (server → client) and SSE is simpler to implement than WebSockets (no custom protocol handling, works over standard HTTP, automatically reconnects). The JWT auth system supports a `?token=` query parameter specifically to handle SSE connections, since `EventSource` cannot set custom headers.

**Trade-off:** SSE does not support bidirectional communication — the client cannot send messages to the server over the same connection. This is acceptable because notifications are purely server-pushed. The current implementation polls the database every 5 seconds rather than using a pub/sub channel, which adds read load but avoids requiring Redis or similar infrastructure.

---

## 3. Debugging Signal — "Fetch All + Filter in Python" Anti-Pattern

### The Problem

A common anti-pattern in beginner-to-intermediate API code is loading all rows from a database table into application memory, then filtering them with Python loops or list comprehensions:

```python
# ❌ Anti-pattern: loads the entire table
all_candidates = db.query(Candidate).all()
filtered = [c for c in all_candidates if c.status == "new" and "Python" in c.skills]
```

This is dangerous at scale because:
- Loads the entire table into memory (a 1M-row table could consume gigabytes of RAM)
- Ignores database indexes — the `status` column is indexed in the schema but never used
- Defeats the purpose of pagination — you must load *everything* before selecting a page
- Causes measurable slowdowns at a few thousand rows and crashes at tens-to-hundreds of thousands

### The Correct Approach

All filtering must happen in SQL `WHERE` clauses, and pagination must use `LIMIT`/`OFFSET` at the database level. The database engine uses indexes to find matching rows efficiently and never transfers more data than necessary.

### This Project's Implementation

This project correctly uses SQL-level filtering in all list endpoints. The `_apply_candidate_filters` function in `backend/app/services/candidate_service.py` pushes filters into the SQLAlchemy query before execution:

```python
# backend/app/services/candidate_service.py
def _apply_candidate_filters(query, status, role_applied, skill, keyword):
    if status:
        query = query.filter(Candidate.status == status)      # WHERE status = ?
    if role_applied:
        query = query.filter(Candidate.role_applied == role_applied)  # WHERE role_applied = ?
    if keyword:
        query = query.filter(
            or_(Candidate.name.ilike(f"%{keyword}%"), Candidate.email.ilike(f"%{keyword}%"))
        )  # WHERE (name ILIKE ? OR email ILIKE ?)
    if skill:
        query = query.filter(Candidate.skills.ilike(f"%{skill}%"))
    return query
```

Pagination is handled by `_paginate_query`:

```python
# backend/app/services/candidate_service.py
def _paginate_query(query, page, page_size, order_col=None, order_expr=None):
    total = query.count()              # SELECT COUNT(*) ...
    offset = (page - 1) * page_size
    results = query.order_by(...).offset(offset).limit(page_size).all()  # LIMIT ? OFFSET ?
    return results, total
```

Every list endpoint (`GET /candidates`, `GET /candidates/review`, `GET /candidates/archived`) uses these functions, ensuring the database does the heavy lifting. For example, `list_candidates` chains both helpers:

```python
def list_candidates(db, status, ..., page, page_size):
    query = db.query(Candidate).filter(Candidate.deleted_at.is_(None))
    query = _apply_candidate_filters(query, status, ...)
    return _paginate_query(query, page, page_size, Candidate.created_at)
```

No Python-side filtering or in-memory slicing is performed after the query executes.

---

## 4. Learning Reflection

Implementing the AI summary endpoint was the first time I built a feature where a mock asynchronous operation (the 2-second `asyncio.sleep()` simulating an LLM call) had to persist its result to a database column and then return that cached value on subsequent requests without re-triggering the delay. Getting the `response_model_exclude_none=True` on `CandidateDetail` right was the trickiest part: if the summary hasn't been generated yet, both `ai_summary` and `ai_summary_generated_at` must be absent from the response rather than present as `null`, which required careful ordering of the Pydantic model fields and the `model_config`.

With more time, I would replace the mock AI summary with an actual integration against an LLM provider (OpenAI, Anthropic, or a local model via Ollama) to generate genuine candidate assessments from CV text and scores, rather than the template-based placeholder. The endpoint and persistence layer are already structured to support this — only the generation logic needs to change.

---

## 5. Example API Calls

All endpoints require JWT authentication. Obtain a token first:

```bash
# Login as admin
curl -s http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@techkraft.com", "password": "admin123"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])"
```

Save the token for subsequent requests:

```bash
TOKEN="<paste-token-here>"
```

### List Candidates with Filters and Pagination

```bash
# List page 1 (20 per page) filtered by status=new and skill=Python
curl -s "http://localhost:8000/candidates?status=new&skill=Python&page=1&page_size=20" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Response shape:
```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 5,
    "total_pages": 1
  }
}
```

Available filters: `status`, `role_applied`, `skill`, `keyword` (searches name/email).

### Submit a Reviewer Score

```bash
curl -s -X POST "http://localhost:8000/candidates/1/scores" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"category": "Technical Skills", "score": 4.5, "note": "Strong technical abilities"}' \
  | python3 -m json.tool
```

Score must be between 1 and 5 (float). The same reviewer cannot submit multiple scores for the same category on the same candidate. Submitting a first score auto-transitions the candidate's status from `new` to `reviewed`.

### Trigger Mock AI Summary

```bash
curl -s -X POST "http://localhost:8000/candidates/1/summary" \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

Returns after a 2-second delay. The summary is persisted — subsequent `GET /candidates/{id}` calls include `ai_summary` and `ai_summary_generated_at` fields.

### List Archived (Soft-Deleted) Candidates

```bash
curl -s "http://localhost:8000/candidates/archived" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Admin-only endpoint. Archived candidates retain their scores (average_score and score_count are included in the response).

### Reviewer-Specific Candidate List

```bash
curl -s "http://localhost:8000/candidates/review?page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

Accessible only to users with `role=reviewer`. Returns candidates assigned to the authenticated reviewer.

---

## Credentials & Security

- **No real secrets are committed.** The `.env.example` file contains placeholder values (`change-me-to-a-real-secret`). The JWT secret must be set via the `JWT_SECRET_KEY` environment variable at runtime — the app crashes immediately with a clear error if it's missing.
- In development, Docker Compose uses a shell-default fallback (`techkraft-dev-secret-key-change-in-production`). **Do not use this default in production.**
- Passwords are hashed with bcrypt via `passlib`.
- Role-based access control (RBAC) is enforced server-side — the API checks `current_user.role` on every protected endpoint, not just in the frontend.

---

## Soft Delete Design

Candidate deletion is implemented as a **soft delete** — the record is never removed from the database:

- `DELETE /candidates/{id}` sets `deleted_at` to the current timestamp and changes `status` to `"archived"`.
- The candidate disappears from active lists but remains in the database and is visible in `GET /candidates/archived` (admin-only).
- `PATCH /candidates/{id}/restore` clears `deleted_at` and resets `status` to `"new"`.
- Scores and notifications associated with the candidate are preserved.

This design ensures auditability — no data is ever permanently lost through normal API operations. Hard deletion (for seed/test data) is handled separately via the `POST /candidates/admin/seed` (delete) flow, which filters strictly on `is_seed_data=1` to never touch real records.

---

## Extra Features (Beyond Core Requirements)

### 1. Real-Time Notifications via SSE
**Why necessary:** Reviewers needed immediate awareness of candidate assignments and score submissions without manual page refreshes. Implemented Server-Sent Events (`GET /notifications/stream`) that polls the database every 5 seconds. The JWT auth system required a `?token=` query parameter fallback because the browser `EventSource` API cannot set custom `Authorization` headers. The frontend `NotificationBell` component seamlessly falls back to 30-second polling if the SSE connection fails.

### 2. AI Summary Persistence
**Why necessary:** The initial AI summary was generated on-the-fly each time the detail page was opened with no caching, meaning the 2-second mock delay ran on every visit. Added `ai_summary` and `ai_summary_generated_at` columns to the `Candidate` model. Now the summary is generated once, stored in the database, and served from cache on subsequent requests. The frontend shows a "Regenerate Summary" button when a cached summary exists rather than forcing a re-fetch.

### 3. Archived Tab Score Display
**Bug closed:** Archived candidates showed no scores in the admin table, even though scores existed in the database. The list endpoint for archived candidates (`GET /candidates/archived`) was not computing average scores — it used a simple list comprehension (`_candidate_to_list_item(c)`). Fixed by mirroring the same score-lookup logic used in the active candidates endpoint: collect candidate IDs, call `get_candidates_average_scores()`, and attach `average_score`/`score_count` before returning. Covered by test `test_archived_candidate_retains_scores`.

### 4. Candidate Status Backfill Script
**Why necessary:** The status auto-transition logic (new → reviewed on first score) was added as a feature, but existing candidates that already had scores before the feature existed remained stuck at `status=new`. Created `backend/scripts/backfill_candidate_status.py` which runs a single SQL `UPDATE` at the database level (not loading rows into Python) to transition them. Safe by design — the `WHERE` clause only matches `status='new'`, excludes soft-deleted and seed data, and requires at least one score to exist.

### 5. Field-Level Form Validation
**Why necessary:** The candidate creation form and `POST /candidates` endpoint had little to no validation beyond required-field checks. Added comprehensive Pydantic validators on the backend (name format, email regex, role whitelist, skills deduplication and limits, reviewer existence check) and matching inline validation on the frontend (blur-triggered errors, disabled submit button, CV file required). Backend 422 validation errors are parsed and surfaced on the correct frontend field rather than displayed as a generic error.

### 6. PDF-Only CV Upload with Content Validation
**Why necessary:** The CV upload endpoint accepted PNG and JPG files with no size limit and only checked the client-supplied `Content-Type` header (trivially spoofable). Restricted to PDF only, enforced a 5 MB cap with early-abort chunked reading, validated the actual `%PDF-` magic number in the first bytes of the file (not just the filename extension or content-type header), and returns distinct error messages for each failure case. Existing PNG/JPG CVs remain accessible via the streaming endpoint (backward-compatible).

### 7. Extended Test Coverage (22 Tests)
**Why necessary:** The initial test suite had 6 tests covering only the most basic flows. Expanded to 22 tests (all passing) covering: soft delete / restore, RBAC enforcement for scores and internal notes, reviewer candidate listing with flag, archived candidate score display, AI summary persistence, status auto-transition and no-downgrade guarantee, CV upload validation (wrong type, wrong extension, oversized, empty file, content mismatch), and candidate creation validation (empty name, invalid email, duplicate email, empty skills, invalid reviewer).

---

## API Endpoint Reference

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| POST | `/auth/register` | None | Register (always creates reviewer) |
| POST | `/auth/login` | None | Login, returns JWT |
| GET | `/auth/me` | Any | Current user info |
| GET | `/auth/users/reviewers` | Admin | List reviewer users |
| POST | `/auth/admin/seed` | None | Seed default admin user |
| GET | `/candidates` | Any | List active candidates (filtered, paginated) |
| GET | `/candidates/{id}` | Any | Candidate detail + scores + AI summary |
| POST | `/candidates` | Any | Create candidate |
| PATCH | `/candidates/{id}` | Any | Update candidate (status, notes, assignment) |
| DELETE | `/candidates/{id}` | Admin | Soft delete (archive) |
| PATCH | `/candidates/{id}/restore` | Admin | Restore archived candidate |
| GET | `/candidates/review` | Reviewer | Reviewer's assigned candidates |
| GET | `/candidates/archived` | Admin | List archived candidates |
| POST | `/candidates/{id}/scores` | Any | Submit score (1–5) |
| PATCH | `/candidates/{id}/scores/{score_id}` | Any | Update own score |
| PATCH | `/candidates/{id}/admin-score/{score_id}` | Admin | Admin override score |
| POST | `/candidates/{id}/summary` | Any | Generate mock AI summary (2s) |
| GET | `/candidates/{id}/cv` | Admin/Assignee | Stream CV file |
| POST | `/candidates/{id}/cv` | Admin | Upload CV (PDF only, 5MB max) |
| GET | `/candidates/{id}/stream` | Any | SSE score stream |
| GET | `/candidates/seed/count` | Admin | Count seed data |
| POST | `/candidates/admin/seed` | Admin | Seed 80 fake candidates |
| DELETE | `/candidates/admin/seed` | Admin | Delete seed candidates |
| GET | `/notifications` | Any | List notifications |
| GET | `/notifications/unread-count` | Any | Unread count |
| GET | `/notifications/stream` | Any | SSE notification stream |
| PATCH | `/notifications/read` | Any | Mark notifications read |
