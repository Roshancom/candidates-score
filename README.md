# TechKraft Candidate Assessments

A full-stack internal tool for TechKraft's recruitment team to review and score candidates. Features role-based access control (reviewer vs admin), mock AI-powered candidate summaries, and a consistent design system.

## Tech Stack

- **Backend:** Python + FastAPI (SQLite + SQLAlchemy)
- **Frontend:** React + Vite
- **Auth:** JWT (email + password)
- **Containerization:** Docker Compose
- **Testing:** pytest

## Setup & Run

### Prerequisites

- Docker and Docker Compose installed

### Running with Docker Compose

```bash
# Clone the repository and navigate to the root
cd techkraft

# Build and start all services
docker-compose up -d
docker compose up
```

This starts two services:

| Service  | Port | URL                   |
| -------- | ---- | --------------------- |
| Backend  | 8000 | http://localhost:8000 |
| Frontend | 5173 | http://localhost:5173 |

### Running locally (without Docker)

**Backend:**

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

### Demo Accounts

On first startup, the app seeds demo data including two users:

| Role     | Email                  | Password    |
| -------- | ---------------------- | ----------- |
| Admin    | admin@techkraft.com    | admin123    |
| Reviewer | reviewer@techkraft.com | reviewer123 |

## API Endpoints

### Authentication

```bash
# Login
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@techkraft.com", "password": "admin123"}'

# Register (role is always hardcoded to "reviewer" server-side)
curl -X POST http://localhost:8000/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "newuser@example.com", "password": "mypassword"}'

# Get current user
curl http://localhost:8000/auth/me \
  -H "Authorization: Bearer <token>"
```

### Candidates

```bash
# List candidates (with filters and pagination)
curl "http://localhost:8000/candidates?status=new&page=1&page_size=20" \
  -H "Authorization: Bearer <token>"

# Get candidate detail (with scores)
curl http://localhost:8000/candidates/1 \
  -H "Authorization: Bearer <token>"

# Create a candidate
curl -X POST http://localhost:8000/candidates \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"name": "John Doe", "email": "john@example.com", "role_applied": "Engineer", "skills": ["Python", "React"]}'

# Update candidate (status, internal_notes — admin only for notes)
curl -X PATCH http://localhost:8000/candidates/1 \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"status": "hired"}'

# Soft delete candidate
curl -X DELETE http://localhost:8000/candidates/1 \
  -H "Authorization: Bearer <token>"

# Submit a score
curl -X POST http://localhost:8000/candidates/1/scores \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"category": "Technical Skills", "score": 4.5, "note": "Excellent coding skills"}'

# Generate AI summary (2-second mock delay)
curl -X POST http://localhost:8000/candidates/1/summary \
  -H "Authorization: Bearer <token>"
```

### Running Tests

```bash
cd backend
source venv/bin/activate  # if running locally
pytest tests/ -v
```

## Reviewer Feature — Design Decisions

### CV Link Placement

The CV file section is placed at the **bottom of the profile card** with a `border-top` separator. This keeps the candidate's identity info (name, email, role, skills, created date) grouped together, with the CV file as an actionable attachment at the bottom. Consistent for both admin and reviewer views.

### "Not Reviewed" Badge Location

The "⚠ Not Reviewed Yet" badge lives in the **Scores card header**, alongside the Scores heading. This gives immediate visual feedback when a reviewer opens a candidate's detail page — they see the status right above the scores area without having to scan elsewhere. Once the reviewer submits their first score, the badge disappears and the candidate is considered "Reviewed" (driven by the `is_reviewed_by_current_user` flag from the backend).

### Notification Triggers (Placeholder)

Notifications are not yet fully implemented. The data model and API now support the prerequisite state:

- When the `assigned_reviewer_id` is set (admin assignment), the candidate appears in the reviewer's "Review Candidates" tab as "Not Reviewed".
- When a reviewer submits their first score, `is_reviewed_by_current_user` flips to `True`, and the candidate moves to the "Reviewed" section on the list page.
- A full notification system (email, in-app, etc.) would hook into these state transitions.

---

## Architecture Decision Records (ADR)

### ADR-1: FastAPI over Django REST Framework

- **Context:** We needed a lightweight, async-capable backend for a focused internal tool. The scope is narrow — candidate CRUD, scoring, and mock AI summaries.
- **Decision:** Use FastAPI instead of Django REST Framework.
- **Trade-off:** FastAPI gives us native async support, automatic OpenAPI docs, and Pydantic validation out of the box. The trade-off is that we lose Django's ORM migrations, admin panel, and ecosystem. For a focused internal tool, the simplicity of FastAPI is the right call.

### ADR-2: Single-Table SQLite with JSON Skills Field

- **Context:** Candidates have a list of skills, and we could normalize this into a separate `skills` table. However, the skills field is read-heavy (displayed on every list view) and rarely queried independently.
- **Decision:** Store skills as a JSON string column on the candidates table rather than a normalized join table.
- **Trade-off:** This simplifies queries and avoids joins for the most common read path. The downside is that filtering by skill requires a `LIKE` query on the JSON text, which is less efficient than an indexed join. For the expected data volume (<10k candidates), this is acceptable.

### ADR-3: JWT Auth with Role-Based Query Filtering

- **Context:** The app has two roles (reviewer and admin) with different data access rules. Reviewers should only see their own scores and never view internal notes. Admin sees all scores and can edit notes.
- **Decision:** Enforce RBAC at the query/service layer, not just the UI. The `get_candidate` service checks the current user's role and returns different data accordingly.
- **Trade-off:** This adds conditional logic to the service layer, making it slightly harder to reason about than a simple "everyone sees everything" approach. However, it's necessary for data confidentiality — UI-only enforcement can be trivially bypassed by calling the API directly.

## Pagination Architecture

### The Bug: In-Memory Pagination

The original implementation did pagination the wrong way — it fetched ALL rows from the database, filtered in Python, and sliced the list:

```python
all_candidates = db.query(Candidate).all()
filtered = [c for c in all_candidates if c.status == status]
page_slice = filtered[(page-1)*page_size : page*page_size]
```

**Why this is a problem:**
1. **Loads the entire table into memory** — Every request fetches every row from the database, regardless of how many rows are actually needed. With 100,000 candidates, you'd transfer and process all 100,000 rows just to show the first page of 20.
2. **Filters in Python instead of SQL** — WHERE clause filtering happens in Python list comprehensions, so the database cannot use indexes (`idx_candidates_role_applied`, etc.) and must transfer all rows over the network.
3. **COUNT is O(n) instead of O(1)** — `len(filtered)` requires loading and filtering all rows in Python. A proper SQL `COUNT(*)` with the same WHERE clause runs at the DB level, using indexes where available.
4. **No deterministic ordering** — Without `ORDER BY`, offset pagination can return duplicate or skipped rows across pages, a classic pagination bug.

### The Fix: DB-Level LIMIT/OFFSET

The fix builds a single filtered query object, applies all filters via SQL WHERE clauses, then reuses the same query object for both COUNT and LIMIT/OFFSET:

```python
def list_candidates(db, status=None, role_applied=None, skill=None, keyword=None, page=1, page_size=20):
    query = db.query(Candidate).filter(Candidate.deleted_at.is_(None))

    # All filters applied at SQL level, not in Python
    if status:
        query = query.filter(Candidate.status == status)
    if role_applied:
        query = query.filter(Candidate.role_applied == role_applied)
    if keyword:
        query = query.filter(or_(Candidate.name.ilike(f"%{keyword}%"), ...))
    if skill:
        query = query.filter(Candidate.skills.ilike(f"%{skill}%"))

    # COUNT at DB level with same WHERE clause
    total = query.count()

    # Pagination at DB level with deterministic ordering
    candidates = query.order_by(Candidate.created_at.desc())
        .offset((page-1) * page_size)
        .limit(page_size)
        .all()

    return candidates, total
```

Key design decisions:
- **Single query object reused** — filters are applied once to a `Query` object, then reused for both `.count()` and `.offset()/.limit()`. This guarantees the filter conditions stay in sync.
- **Deterministic `ORDER BY created_at DESC`** — Without this, the same row could appear on multiple pages or be skipped entirely.
- **Archived candidates excluded by default** — `deleted_at.is_(None)` is the base filter, applied before pagination math so counts/totals are accurate.
- **Skill filter uses `ILIKE` on JSON text** — Since skills are stored as a JSON string column (not normalized), we use `ILIKE '%skill%'`. For the expected data volume this is acceptable — a normalized join table would be needed for larger datasets.
- **Response shape** — The API returns `{ "data": [...], "pagination": { "page", "page_size", "total_count", "total_pages" } }`. This lets the frontend render page controls directly from the response metadata without additional math.

See `backend/app/services/candidate_service.py` for the full implementation.

## Learning Reflection

Building the SSE (Server-Sent Events) streaming endpoint for real-time score updates was something I'd like to explore further. While the core SSE infrastructure using `sse_starlette` works, a production-grade implementation would need a pub/sub system (like Redis Pub/Sub or a message queue) to broadcast score updates across multiple server instances. The current implementation opens a persistent connection and sends periodic keepalive pings but doesn't actually push new score events because there's no event bus. With more time, I'd wire up an async event system using Redis or an in-process asyncio Queue to make the streaming truly real-time.
