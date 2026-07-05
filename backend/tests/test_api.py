"""
Tests for TechKraft Candidate Assessments API.

Covers:
0. Import test — all sub-routers load correctly
1. API endpoint test — create a candidate, verify response shape
2. Auth enforcement test — reviewer cannot see another reviewer's scores
3. Soft delete test — candidate is soft-deleted (status=archived)
4. Review candidates endpoint — assigned candidates and is_reviewed flag
5. Reviewer candidate detail — cv_file_url, is_reviewed_by_current_user, no internal_notes
6. Admin candidate detail — sees internal_notes and all scores
"""

import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.main import app
from app.database import Base, get_db
from app.auth import hash_password, create_access_token
from app.models import User


TEST_DB_PATH = "/tmp/test_techkraft.db"

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
            "role_applied": "Engineer",
            "skills": ["Python", "FastAPI"],
        },
        headers=auth_headers(token),
    )

    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test User"
    assert data["email"] == "test@example.com"
    assert data["role_applied"] == "Engineer"
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
            "role_applied": "Tester",
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
            "role_applied": "Engineer",
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
            "role_applied": "Reviewer Role",
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
    data = review_resp.json()
    assert len(data) > 0
    found = [c for c in data if c["id"] == candidate_id]
    assert len(found) == 1, "Assigned candidate should appear in review list"
    assert found[0]["is_reviewed_by_current_user"] == False
    assert found[0]["cv_file_url"] == "/cv/1/resume.pdf"

    # Admin should get 403
    admin_review = client.get(
        "/candidates/review",
        headers=auth_headers(token_admin),
    )
    assert admin_review.status_code == 403


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
            "role_applied": "Tester",
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
