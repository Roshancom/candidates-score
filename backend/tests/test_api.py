"""
Tests for TechKraft Candidate Assessments API.

Covers:
0. Import test — all sub-routers load correctly
1. API endpoint test — create a candidate, verify response shape
2. Auth enforcement test — reviewer cannot see another reviewer's scores
3. Soft delete test — candidate is soft-deleted (status=archived)
4. Review candidates endpoint — assigned candidates, is_reviewed flag, pagination metadata
5. AI Summary persistence test — generated summary appears in subsequent GET response
6. Reviewer candidate detail — cv_file_url, is_reviewed_by_current_user, no internal_notes
7. Status auto-transition — scoring a new candidate transitions to reviewed
8. No status downgrade — scoring hired/rejected/archived doesn't revert to reviewed
9. Archived candidate retains scores — scores appear in /candidates/archived response
10. CV upload validation — rejects wrong types, oversized files, content mismatch, empty files
11. Candidate creation validation — name, email, skills, reviewer, duplicate detection
"""

import os
import tempfile
import shutil

# JWT_SECRET_KEY must be set before importing `app.main` which imports `app.auth`.
# If not set in the environment, provide a test key so tests can run standalone.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-testing-only")
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.auth import hash_password, create_access_token
from app.models import User
from app.routers.candidates import cv_files as cv_files_mod


TEST_DB_PATH = "/tmp/test_techkraft.db"
TEST_UPLOAD_DIR = tempfile.mkdtemp(prefix="test_uploads_")

# Override UPLOAD_DIR to a writable temp directory for tests
# Must patch cv_files_mod.UPLOAD_DIR (not helpers.UPLOAD_DIR) because cv_files.py
# imports UPLOAD_DIR by value at module import time.
cv_files_mod.UPLOAD_DIR = TEST_UPLOAD_DIR

# Clean up any previous test database
if os.path.exists(TEST_DB_PATH):
    os.remove(TEST_DB_PATH)

test_engine = create_engine(f"sqlite:///{TEST_DB_PATH}", connect_args={"check_same_thread": False})
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    """Create tables before each test, drop after."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(autouse=True)
def clean_uploads():
    """Clean up any uploaded files between tests."""
    yield
    for fname in os.listdir(TEST_UPLOAD_DIR):
        fpath = os.path.join(TEST_UPLOAD_DIR, fname)
        try:
            if os.path.isfile(fpath):
                os.unlink(fpath)
            elif os.path.isdir(fpath):
                shutil.rmtree(fpath)
        except OSError:
            pass


def create_test_user(email="reviewer@test.com", password="testpass", role="reviewer"):
    """Helper to create a user and return a JWT token."""
    db = TestSessionLocal()
    try:
        user = User(
            email=email,
            hashed_password=hash_password(password),
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return create_access_token(data={"sub": user.id})
    finally:
        db.close()


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# -------- Test 0: Import / Router Loading Test --------

def test_candidates_sub_routers_import():
    """
    Verify all split router modules import correctly and the combined
    router has all expected routes registered.
    This catches import-order or circular-dependency bugs introduced
    during refactoring.
    """
    from app.routers.candidates import crud, scores, cv_files, seed, streaming, helpers

    # Each sub-module must expose a 'router' attribute
    assert hasattr(crud, "router")
    assert hasattr(scores, "router")
    assert hasattr(cv_files, "router")
    assert hasattr(seed, "router")
    assert hasattr(streaming, "router")

    # Helpers must expose shared constants and functions
    assert hasattr(helpers, "VALID_STATUSES")
    assert hasattr(helpers, "UPLOAD_DIR")
    assert callable(getattr(helpers, "_parse_skills"))
    assert callable(getattr(helpers, "_candidate_to_list_item"))

    # The combined router from __init__.py must have all routes registered
    from app.routers.candidates import router as combined_router
    route_paths = [(r.path, list(r.methods)[0] if r.methods else "") for r in combined_router.routes]
    route_set = set(p for p, _ in route_paths)

    # Check that key fixed paths exist (not exhaustive, just representative)
    assert "/candidates" in route_set, "GET /candidates (list) not registered"
    assert "/candidates/review" in route_set, "/candidates/review not registered"
    assert "/candidates/archived" in route_set, "/candidates/archived not registered"
    assert "/candidates/seed/count" in route_set, "/candidates/seed/count not registered"
    assert "/candidates/admin/seed" in route_set, "/candidates/admin/seed not registered"
    assert "/candidates/{candidate_id}" in route_set, "/candidates/{{candidate_id}} not registered"
    assert "/candidates/{candidate_id}/scores" in route_set, "POST score not registered"
    assert "/candidates/{candidate_id}/cv" in route_set, "/candidates/{{candidate_id}}/cv not registered"
    assert "/candidates/{candidate_id}/stream" in route_set, "/candidates/{{candidate_id}}/stream not registered"
    assert "/candidates/{candidate_id}/summary" in route_set, "POST summary not registered"


# -------- Test 1: API Endpoint Test --------

def test_create_candidate_response_shape():
    """Test creating a candidate returns the correct response shape."""
    token = create_test_user()

    response = client.post(
        "/candidates",
        json={
            "name": "Test User",
            "email": "test@example.com",
            "role_applied": "Software Engineer",
            "skills": ["Python", "FastAPI"],
        },
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"
    assert data["role_applied"] == "Software Engineer"
    assert data["skills"] == ["Python", "FastAPI"]
    assert data["status"] == "new"
    assert "id" in data
    assert "created_at" in data
    assert "scores" in data


# -------- Test 2: Auth Enforcement (RBAC) --------

def test_reviewer_cannot_see_other_reviewer_scores():
    """
    Test that a reviewer cannot see another reviewer's scores.
    Reviewer 1 submits score. Reviewer 2 requests candidate detail
    and should see zero scores.
    """
    token_r1 = create_test_user(email="r1@test.com", password="testpass", role="reviewer")
    token_r2 = create_test_user(email="r2@test.com", password="testpass", role="reviewer")

    # Reviewer 1 creates a candidate
    create_resp = client.post(
        "/candidates",
        json={
            "name": "RBAC Test",
            "email": "rbac@example.com",
            "role_applied": "QA Engineer",
        },
        headers=auth_headers(token_r1),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Reviewer 1 submits a score
    score_resp = client.post(
        f"/candidates/{candidate_id}/scores",
        json={"category": "Coding", "score": 4.5, "note": "Great"},
        headers=auth_headers(token_r1),
    )
    assert score_resp.status_code == 201

    # Reviewer 2 requests candidate detail — should see 0 scores
    detail_resp = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_r2),
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert len(data["scores"]) == 0, "Reviewer should not see another reviewer's scores"
    # Reviewer should also not see internal_notes (key should be absent entirely)
    assert "internal_notes" not in data, "internal_notes must be omitted from response for reviewers"


# -------- Test 3: Soft Delete & RBAC internal_notes --------

def test_soft_delete_and_admin_internal_notes():
    """
    Test soft delete sets status to archived.
    Also test that admin can view internal_notes but reviewer cannot.
    """
    token_admin = create_test_user(email="admin@test.com", password="testpass", role="admin")
    token_reviewer = create_test_user(email="rev@test.com", password="testpass", role="reviewer")

    # Create candidate as reviewer
    create_resp = client.post(
        "/candidates",
        json={
            "name": "Soft Delete Test",
            "email": "softdelete@example.com",
            "role_applied": "Software Engineer",
        },
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Admin adds internal notes
    notes_resp = client.patch(
        f"/candidates/{candidate_id}",
        json={"internal_notes": "This is an admin note"},
        headers=auth_headers(token_admin),
    )
    assert notes_resp.status_code == 200

    # Reviewer should NOT see internal_notes (key should be absent)
    reviewer_detail = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_reviewer),
    )
    assert reviewer_detail.status_code == 200
    assert "internal_notes" not in reviewer_detail.json(), "internal_notes must be omitted for reviewers"

    # Admin SHOULD see internal_notes
    admin_detail = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_admin),
    )
    assert admin_detail.status_code == 200
    assert admin_detail.json()["internal_notes"] == "This is an admin note"

    # Soft delete the candidate
    delete_resp = client.delete(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_admin),
    )
    assert delete_resp.status_code == 204

    # Verify candidate is gone from list
    list_resp = client.get(
        "/candidates",
        headers=auth_headers(token_admin),
    )
    assert list_resp.status_code == 200
    ids = [item["id"] for item in list_resp.json()["data"]]
    assert candidate_id not in ids, "Soft-deleted candidate should not appear in list"

    # Verify direct access returns 404
    get_resp = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_admin),
    )
    assert get_resp.status_code == 404


# -------- Test 4: Review Candidates Endpoint --------

def test_review_candidates_endpoint():
    """
    Test the /candidates/review endpoint:
    - Returns only candidates assigned to the reviewer
    - Has is_reviewed_by_current_user flag
    - cv_file_url is present
    - Admins cannot access this endpoint
    """
    token_admin = create_test_user(email="admin2@test.com", role="admin")
    token_reviewer = create_test_user(email="rev3@test.com", role="reviewer")

    # Create a candidate and assign it to the reviewer
    create_resp = client.post(
        "/candidates",
        json={
            "name": "Review Assign Test",
            "email": "reviewassign@example.com",
            "role_applied": "Software Engineer",
        },
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Manually assign the candidate to the reviewer (simulating admin assignment)
    db = TestSessionLocal()
    from app.models import Candidate as C
    try:
        c = db.query(C).filter(C.id == candidate_id).first()
        c.assigned_reviewer_id = 2  # reviewer is second user
        c.cv_file_url = "/cv/1/resume.pdf"
        db.commit()
    finally:
        db.close()

    # Reviewer requests their review candidates
    review_resp = client.get(
        "/candidates/review",
        headers=auth_headers(token_reviewer),
    )
    assert review_resp.status_code == 200
    body = review_resp.json()
    assert "data" in body, "Response must have 'data' key"
    assert "pagination" in body, "Response must have 'pagination' key"
    data = body["data"]
    assert len(data) > 0
    found = [c for c in data if c["id"] == candidate_id]
    assert len(found) == 1, "Assigned candidate should appear in review list"
    assert found[0]["is_reviewed_by_current_user"] == False
    assert found[0]["cv_file_url"] == "/cv/1/resume.pdf"
    # Verify pagination metadata
    pagination = body["pagination"]
    assert "page" in pagination
    assert "total_count" in pagination
    assert "total_pages" in pagination
    assert pagination["total_count"] >= 1

    # Admin should get 403
    admin_review = client.get(
        "/candidates/review",
        headers=auth_headers(token_admin),
    )
    assert admin_review.status_code == 403


# -------- Test 6: AI Summary Persistence --------

def test_ai_summary_persistence():
    """
    Test that a generated AI summary persists in the DB and appears in
    a subsequent GET /candidates/{id} response.
    """
    token = create_test_user(email="admin@persist.test", role="admin")

    # Create a candidate
    create_resp = client.post(
        "/candidates",
        json={
            "name": "Summary Persist",
            "email": "summarypersist@example.com",
            "role_applied": "Software Engineer",
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Before generating, GET should not have ai_summary (excluded via response_model_exclude_none)
    detail_before = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token),
    )
    assert detail_before.status_code == 200
    before = detail_before.json()
    assert before.get("ai_summary") is None, \
        "No summary should exist before generation"

    # Generate summary
    summary_resp = client.post(
        f"/candidates/{candidate_id}/summary",
        headers=auth_headers(token),
    )
    assert summary_resp.status_code == 200
    summary_data = summary_resp.json()
    assert "summary" in summary_data
    assert len(summary_data["summary"]) > 0

    # After generating, GET should include the cached summary
    detail_after = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token),
    )
    assert detail_after.status_code == 200
    detail = detail_after.json()
    assert detail["ai_summary"] == summary_data["summary"], \
        "Cached summary should match generated summary"
    assert detail["ai_summary_generated_at"] is not None, \
        "ai_summary_generated_at should be set"


# -------- Test 7: Status Auto-Transition on Score --------

def test_candidate_status_transitions_to_reviewed_on_score():
    """
    Test that submitting a score for a 'new' candidate auto-transitions
    their status to 'reviewed'.
    """
    token = create_test_user(email="rev@status.test", role="reviewer")

    # Create a new candidate
    create_resp = client.post(
        "/candidates",
        json={
            "name": "Status Test",
            "email": "statustest@example.com",
            "role_applied": "Software Engineer",
        },
        headers=auth_headers(token),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]
    assert create_resp.json()["status"] == "new"

    # Submit a score
    score_resp = client.post(
        f"/candidates/{candidate_id}/scores",
        json={"category": "Coding", "score": 4.0, "note": "Good"},
        headers=auth_headers(token),
    )
    assert score_resp.status_code == 201

    # Verify status transitioned to 'reviewed'
    detail_resp = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "reviewed"


def test_scoring_does_not_downgrade_hired_or_rejected_status():
    """
    Test that scoring a hired, rejected, or archived candidate:
    - Does NOT revert their status to 'reviewed'
    - Scoring archived candidates is rejected outright
    """
    token_admin = create_test_user(email="admin@nodowngrade.test", role="admin")
    token_reviewer = create_test_user(email="rev@nodowngrade.test", role="reviewer")

    # Create a candidate
    create_resp = client.post(
        "/candidates",
        json={
            "name": "No Downgrade",
            "email": "nodowngrade@example.com",
            "role_applied": "Software Engineer",
        },
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Manually set status to 'hired' as admin
    patch_resp = client.patch(
        f"/candidates/{candidate_id}",
        json={"status": "hired"},
        headers=auth_headers(token_admin),
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "hired"

    # Submit a score for the hired candidate — should succeed but NOT downgrade status
    score_resp = client.post(
        f"/candidates/{candidate_id}/scores",
        json={"category": "Coding", "score": 4.0, "note": "Good"},
        headers=auth_headers(token_reviewer),
    )
    assert score_resp.status_code == 201

    # Verify status is still 'hired'
    detail_resp = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_admin),
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "hired", \
        "Scoring a hired candidate must NOT revert status to reviewed"

    # Now test scoring an archived candidate is rejected
    delete_resp = client.delete(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_admin),
    )
    assert delete_resp.status_code == 204

    # Attempt to score archived candidate — should be rejected
    score_archived = client.post(
        f"/candidates/{candidate_id}/scores",
        json={"category": "Leadership", "score": 3.0, "note": "Test"},
        headers=auth_headers(token_reviewer),
    )
    assert score_archived.status_code == 409, \
        "Scoring an archived candidate should return 409 Conflict"


# -------- Test 5: Reviewer Candidate Detail --------

def test_reviewer_candidate_detail_has_reviewed_flag():
    """
    Test that:
    - Reviewer sees cv_file_url and is_reviewed_by_current_user in detail
    - Reviewer does NOT see internal_notes
    - After submitting a score, is_reviewed_by_current_user flips to True
    """
    token_reviewer = create_test_user(email="rev4@test.com", role="reviewer")

    # Create a candidate and assign
    create_resp = client.post(
        "/candidates",
        json={
            "name": "Review Flag Test",
            "email": "flagtest@example.com",
            "role_applied": "QA Engineer",
            "skills": ["Python"],
        },
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Manually assign and set cv
    db = TestSessionLocal()
    from app.models import Candidate as C
    try:
        c = db.query(C).filter(C.id == candidate_id).first()
        c.assigned_reviewer_id = 1
        c.cv_file_url = "/cv/test/resume.pdf"
        c.internal_notes = "Secret admin note"
        db.commit()
    finally:
        db.close()

    # Get detail — should show cv_file_url and NOT internal_notes
    detail_resp = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_reviewer),
    )
    assert detail_resp.status_code == 200
    data = detail_resp.json()
    assert data["cv_file_url"] == "/cv/test/resume.pdf"
    assert data["is_reviewed_by_current_user"] == False
    assert "internal_notes" not in data, "Reviewer should NOT see internal_notes"

    # Submit a score
    score_resp = client.post(
        f"/candidates/{candidate_id}/scores",
        json={"category": "Coding", "score": 4.0, "note": "Good"},
        headers=auth_headers(token_reviewer),
    )
    assert score_resp.status_code == 201

    # Get detail again — is_reviewed_by_current_user should be True
    detail_resp2 = client.get(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_reviewer),
    )
    assert detail_resp2.status_code == 200
    data2 = detail_resp2.json()
    assert data2["is_reviewed_by_current_user"] == True
    assert len(data2["scores"]) == 1


# -------- Test 9: Archived Candidate Retains Scores --------

def test_archived_candidate_retains_scores():
    """
    Test that soft-deleted (archived) candidates still include their
    average_score and score_count in the /candidates/archived response.
    """
    token_admin = create_test_user(email="admin@archived-score.test", role="admin")
    token_reviewer = create_test_user(email="rev@archived-score.test", role="reviewer")

    # Create a candidate as reviewer
    create_resp = client.post(
        "/candidates",
        json={
            "name": "Archived Score Test",
            "email": "archivedscore@example.com",
            "role_applied": "Software Engineer",
        },
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Submit a score
    score_resp = client.post(
        f"/candidates/{candidate_id}/scores",
        json={"category": "Coding", "score": 4.0, "note": "Good work"},
        headers=auth_headers(token_reviewer),
    )
    assert score_resp.status_code == 201

    # Admin soft-deletes the candidate
    delete_resp = client.delete(
        f"/candidates/{candidate_id}",
        headers=auth_headers(token_admin),
    )
    assert delete_resp.status_code == 204

    # Fetch archived list — must include scores
    archived_resp = client.get(
        "/candidates/archived",
        headers=auth_headers(token_admin),
    )
    assert archived_resp.status_code == 200
    body = archived_resp.json()
    assert "data" in body
    assert "pagination" in body

    # Find our candidate in the archived list
    archived_items = [c for c in body["data"] if c["id"] == candidate_id]
    assert len(archived_items) == 1, "Archived candidate should appear in /candidates/archived"
    item = archived_items[0]
    assert item["average_score"] == 4.0, f"Expected average_score=4.0, got {item['average_score']}"
    assert item["score_count"] == 1, f"Expected score_count=1, got {item['score_count']}"


# -------- Test 10: CV Upload Validation --------

def _make_pdf_bytes() -> bytes:
    """Return minimal valid PDF bytes with the %PDF- magic number."""
    return b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [] /Count 0 >>\nendobj\nxref\n0 3\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \ntrailer\n<< /Size 3 /Root 1 0 R >>\nstartxref\n111\n%%EOF"


def test_upload_valid_pdf():
    """Upload a valid PDF under 5 MB → success."""
    token_admin = create_test_user(email="admin@cv.test", role="admin")
    token_reviewer = create_test_user(email="rev@cv.test", role="reviewer")

    # Create a candidate first
    create_resp = client.post(
        "/candidates",
        json={"name": "CV Test", "email": "cvtest@example.com","role_applied": "Software Engineer"
},
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Upload a valid PDF
    pdf_content = _make_pdf_bytes()
    upload_resp = client.post(
        f"/candidates/{candidate_id}/cv",
        files={"file": ("resume.pdf", pdf_content, "application/pdf")},
        headers=auth_headers(token_admin),
    )
    assert upload_resp.status_code == 200
    data = upload_resp.json()
    assert data["cv_file_url"] == f"cv_{candidate_id}.pdf"
    assert data["cv_content_type"] == "application/pdf"
    assert "message" in data

    # Verify it can be streamed back
    stream_resp = client.get(
        f"/candidates/{candidate_id}/cv",
        headers=auth_headers(token_admin),
    )
    assert stream_resp.status_code == 200
    assert stream_resp.headers["content-type"] == "application/pdf"


def test_upload_file_too_large():
    """Upload a file over 5 MB → 400 with size error."""
    token_admin = create_test_user(email="admin@cvsize.test", role="admin")
    token_reviewer = create_test_user(email="rev@cvsize.test", role="reviewer")

    create_resp = client.post(
        "/candidates",
        json={"name": "Size Test", "email": "sizetest@example.com","role_applied": "Software Engineer"
},
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Create content starting with PDF magic but over 5 MB
    oversized = b"%PDF-1.4\n" + b"x" * (5 * 1024 * 1024 + 1)
    upload_resp = client.post(
        f"/candidates/{candidate_id}/cv",
        files={"file": ("resume.pdf", oversized, "application/pdf")},
        headers=auth_headers(token_admin),
    )
    assert upload_resp.status_code == 400
    assert "5 MB" in upload_resp.json()["detail"]


def test_upload_wrong_type_png():
    """Upload a .png file → 400 with type error."""
    token_admin = create_test_user(email="admin@type.test", role="admin")
    token_reviewer = create_test_user(email="rev@type.test", role="reviewer")

    create_resp = client.post(
        "/candidates",
        json={"name": "Type Test", "email": "typetest@example.com","role_applied": "Software Engineer"
},
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Upload a PNG file (correct magic but wrong content-type)
    png_header = b"\x89PNG\r\n\x1a\n"
    upload_resp = client.post(
        f"/candidates/{candidate_id}/cv",
        files={"file": ("photo.png", png_header, "image/png")},
        headers=auth_headers(token_admin),
    )
    assert upload_resp.status_code == 400
    detail = upload_resp.json()["detail"]
    assert "Only PDF files" in detail or "Invalid file type" in detail


def test_upload_wrong_extension_png():
    """Upload a file with .png extension but valid PDF content-type/content → 400 with extension error."""
    token_admin = create_test_user(email="admin@ext.test", role="admin")
    token_reviewer = create_test_user(email="rev@ext.test", role="reviewer")

    create_resp = client.post(
        "/candidates",
        json={"name": "Ext Test", "email": "exttest@example.com","role_applied": "Software Engineer"
},
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Upload PDF content with .png extension but correct content-type
    # This passes the content-type check but should fail at extension check
    upload_resp = client.post(
        f"/candidates/{candidate_id}/cv",
        files={"file": ("photo.png", _make_pdf_bytes(), "application/pdf")},
        headers=auth_headers(token_admin),
    )
    assert upload_resp.status_code == 400
    detail = upload_resp.json()["detail"]
    assert ".pdf" in detail or "file extension" in detail.lower()


def test_upload_content_mismatch():
    """
    Upload a .txt file renamed to .pdf (correct extension & content-type,
    but wrong magic number) → 400 with content-mismatch error.
    """
    token_admin = create_test_user(email="admin@magic.test", role="admin")
    token_reviewer = create_test_user(email="rev@magic.test", role="reviewer")

    create_resp = client.post(
        "/candidates",
        json={"name": "Magic Test", "email": "magictest@example.com","role_applied": "Software Engineer"
},
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    # Upload a text file with .pdf extension and PDF content-type
    upload_resp = client.post(
        f"/candidates/{candidate_id}/cv",
        files={"file": ("malicious.exe.pdf", b"This is not a PDF", "application/pdf")},
        headers=auth_headers(token_admin),
    )
    assert upload_resp.status_code == 400
    detail = upload_resp.json()["detail"]
    assert "content does not match PDF format" in detail or "valid PDF" in detail


def test_upload_empty_file():
    """Upload an empty file → 400 with empty-file error."""
    token_admin = create_test_user(email="admin@empty.test", role="admin")
    token_reviewer = create_test_user(email="rev@empty.test", role="reviewer")

    create_resp = client.post(
        "/candidates",
        json={"name": "Empty Test", "email": "emptytest@example.com","role_applied": "Software Engineer"
},
        headers=auth_headers(token_reviewer),
    )
    assert create_resp.status_code == 201
    candidate_id = create_resp.json()["id"]

    upload_resp = client.post(
        f"/candidates/{candidate_id}/cv",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers=auth_headers(token_admin),
    )
    assert upload_resp.status_code == 400
    detail = upload_resp.json()["detail"]
    assert "Empty file" in detail or "empty" in detail.lower()


# -------- Test 11: Candidate Creation Validation --------

def test_create_candidate_rejects_empty_name():
    """Reject a candidate with an empty/whitespace-only name."""
    token = create_test_user()
    resp = client.post(
        "/candidates",
        json={
            "name": "   ",
            "email": "valid@example.com",
            "role_applied": "Software Engineer",
            "skills": ["Python"],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    errors = {e["loc"][-1]: e["msg"] for e in resp.json()["detail"]}
    assert "name" in errors


def test_create_candidate_rejects_invalid_email():
    """Reject a candidate with an invalid email format."""
    token = create_test_user()
    resp = client.post(
        "/candidates",
        json={
            "name": "Valid Name",
            "email": "not-an-email",
            "role_applied": "Software Engineer",
            "skills": ["Python"],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    errors = {e["loc"][-1]: e["msg"] for e in resp.json()["detail"]}
    assert "email" in errors


def test_create_candidate_rejects_duplicate_email():
    """Reject a candidate with a duplicate email (case-insensitive)."""
    token = create_test_user()
    # Create first candidate
    resp1 = client.post(
        "/candidates",
        json={
            "name": "First User",
            "email": "dupe@example.com",
            "role_applied": "Software Engineer",
            "skills": ["Python"],
        },
        headers=auth_headers(token),
    )
    assert resp1.status_code == 201

    # Try creating second candidate with same email (different case)
    resp2 = client.post(
        "/candidates",
        json={
            "name": "Second User",
            "email": "Dupe@example.com",
            "role_applied": "Software Engineer",
            "skills": ["Go"],
        },
        headers=auth_headers(token),
    )
    assert resp2.status_code == 400
    detail = resp2.json()["detail"]
    assert "already exists" in detail.lower()


def test_create_candidate_rejects_empty_skills():
    """Reject a candidate with empty skills list or all-whitespace entries."""
    token = create_test_user()
    resp = client.post(
        "/candidates",
        json={
            "name": "No Skills",
            "email": "noskills@example.com",
            "role_applied": "Software Engineer",
            "skills": [],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 422
    errors = {e["loc"][-1]: e["msg"] for e in resp.json()["detail"]}
    assert "skills" in errors


def test_create_candidate_rejects_invalid_reviewer():
    """Reject assigning a non-existent or non-reviewer user ID."""
    token_admin = create_test_user(email="admin@reviewertest", role="admin")
    # Try assigning to non-existent reviewer ID 999
    resp = client.post(
        "/candidates",
        json={
            "name": "Bad Reviewer",
            "email": "badrv@example.com",
            "role_applied": "Software Engineer",
            "skills": ["Python"],
            "assigned_reviewer_id": 999,
        },
        headers=auth_headers(token_admin),
    )
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "not found" in detail.lower()

    # Create a reviewer first so user 2 is a reviewer
    create_test_user(email="real_reviewer@test.com", role="reviewer")
    # Now create the admin (user 3) to test assigning an admin as reviewer
    token_admin2 = create_test_user(email="admin2@reviewertest", role="admin")
    # Try assigning an admin as reviewer
    resp2 = client.post(
        "/candidates",
        json={
            "name": "Admin As Reviewer",
            "email": "adminrv@example.com",
            "role_applied": "Software Engineer",
            "skills": ["Python"],
            "assigned_reviewer_id": 3,  # user 3 is admin
        },
        headers=auth_headers(token_admin2),
    )
    assert resp2.status_code == 400
    detail2 = resp2.json()["detail"]
    assert "not a reviewer" in detail2.lower()


def test_create_candidate_valid_payload():
    """Accept a fully valid payload successfully."""
    token = create_test_user()
    resp = client.post(
        "/candidates",
        json={
            "name": "  Valid User  ",  # trailing/leading whitespace should be trimmed
            "email": "  VALID@Example.com  ",  # should normalize to lowercase
            "role_applied": "Senior Frontend Engineer",
            "skills": ["React", "TypeScript", "CSS"],
        },
        headers=auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Valid User"
    assert data["email"] == "valid@example.com"
    assert data["role_applied"] == "Senior Frontend Engineer"
    assert data["skills"] == ["React", "TypeScript", "CSS"]
    assert data["status"] == "new"
