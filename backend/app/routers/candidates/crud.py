from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Candidate, User
from app.schemas import (
    CandidateCreate,
    CandidateDetail,
    CandidateListResponse,
    PaginationInfo,
    ReviewCandidateListItem,
    CandidateUpdate,
    ScoreResponse,
)
from app.auth import get_current_user
from app.services.candidate_service import (
    list_candidates,
    get_candidate,
    create_candidate,
    update_candidate,
    soft_delete_candidate,
    restore_candidate,
    list_archived_candidates,
    list_candidates_for_reviewer,
    get_scores_for_candidate,
    get_scores_for_reviewer,
    has_reviewer_submitted_scores,
    candidate_has_any_scores,
    get_candidates_average_scores,
)
from app.services.notification_service import notify_reviewer_assigned
from app.routers.candidates.helpers import _parse_skills, _candidate_to_list_item, VALID_STATUSES

router = APIRouter()


@router.get("", response_model=CandidateListResponse)
def list_candidates_endpoint(
    status: Optional[str] = Query(None),
    role_applied: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List candidates with SQL-level filtering and pagination."""
    # Validate status
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{status}'. Allowed: {', '.join(sorted(VALID_STATUSES))}",
        )

    # Clamp page_size to [1, 50]
    actual_page_size = max(1, min(page_size, 50))

    candidates, total = list_candidates(
        db=db,
        status=status,
        role_applied=role_applied,
        skill=skill,
        keyword=keyword,
        page=page,
        page_size=actual_page_size,
    )

    # Compute average scores across all reviewers for this batch of candidates
    candidate_ids = [c.id for c in candidates]
    avg_scores = get_candidates_average_scores(db, candidate_ids)

    items = []
    for c in candidates:
        item = _candidate_to_list_item(c)
        score_data = avg_scores.get(c.id)
        if score_data:
            item.average_score = score_data[0]
            item.score_count = score_data[1]
        items.append(item)

    total_pages = max(1, (total + actual_page_size - 1) // actual_page_size) if total > 0 else 0

    return CandidateListResponse(
        data=items,
        pagination=PaginationInfo(
            page=page,
            page_size=actual_page_size,
            total_count=total,
            total_pages=total_pages,
        ),
    )


@router.get("/review", response_model=list[ReviewCandidateListItem])
def list_review_candidates(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List candidates assigned to the current reviewer.
    Reviewer-only endpoint.
    """
    if current_user.role != "reviewer":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only reviewers can access this endpoint",
        )

    candidates, total = list_candidates_for_reviewer(
        db=db,
        reviewer_id=current_user.id,
        page=page,
        page_size=page_size,
    )

    result = []
    for c in candidates:
        is_reviewed_by_any = candidate_has_any_scores(db, c.id)
        # Get the current reviewer's scores to compute both the flag and average in one query
        my_scores = get_scores_for_reviewer(db, c.id, current_user.id)
        is_reviewed_by_current = len(my_scores) > 0
        avg_score = round(sum(s.score for s in my_scores) / len(my_scores), 2) if my_scores else None
        result.append(ReviewCandidateListItem(
            id=c.id,
            name=c.name,
            email=c.email,
            role_applied=c.role_applied,
            status=c.status,
            skills=_parse_skills(c),
            created_at=c.created_at,
            assigned_date=c.assigned_date,
            assigned_reviewer_id=c.assigned_reviewer_id,
            cv_file_url=c.cv_file_url,
            is_reviewed_by_current_user=is_reviewed_by_current,
            is_reviewed_by_anyone=is_reviewed_by_any,
            average_score=avg_score,
        ))

    return result


@router.get("/archived", response_model=CandidateListResponse)
def list_archived_candidates_endpoint(
    status: Optional[str] = Query(None),
    role_applied: Optional[str] = Query(None),
    skill: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List archived (soft-deleted) candidates. Admin-only.
    NOTE: This route MUST be defined BEFORE /{candidate_id} to avoid FastAPI
    matching "archived" as a candidate_id parameter.
    """
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can view archived candidates",
        )

    # Validate status
    if status and status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status '{status}'. Allowed: {', '.join(sorted(VALID_STATUSES))}",
        )

    actual_page_size = max(1, min(page_size, 50))
    candidates, total = list_archived_candidates(
        db=db,
        status=status,
        role_applied=role_applied,
        skill=skill,
        keyword=keyword,
        page=page,
        page_size=actual_page_size,
    )
    total_pages = max(1, (total + actual_page_size - 1) // actual_page_size) if total > 0 else 0
    return CandidateListResponse(
        data=[_candidate_to_list_item(c) for c in candidates],
        pagination=PaginationInfo(
            page=page,
            page_size=actual_page_size,
            total_count=total,
            total_pages=total_pages,
        ),
    )


# ── Routes with path parameters ──


@router.get("/{candidate_id}", response_model=CandidateDetail, response_model_exclude_none=True)
def get_candidate_endpoint(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get candidate detail with scores, respecting RBAC."""
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # Bug 2: Permission check - reviewers can only access candidates assigned to them.
    # Allow access if candidate is unassigned (assigned_reviewer_id is None) to
    # support creation flow where a reviewer creates an unassigned candidate.
    if (
        current_user.role == "reviewer"
        and candidate.assigned_reviewer_id is not None
        and candidate.assigned_reviewer_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this candidate",
        )

    # RBAC: reviewer can only see their own scores, admin sees all
    if current_user.role == "admin":
        scores = get_scores_for_candidate(db, candidate_id)
        internal_notes = candidate.internal_notes
    else:
        scores = get_scores_for_reviewer(db, candidate_id, current_user.id)
        internal_notes = None  # Reviewers cannot see internal notes

    # Determine if current reviewer has submitted any scores
    is_reviewed = False
    if current_user.role == "reviewer":
        is_reviewed = has_reviewer_submitted_scores(db, candidate_id, current_user.id)

    return CandidateDetail(
        id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        role_applied=candidate.role_applied,
        status=candidate.status,
        skills=_parse_skills(candidate),
        internal_notes=internal_notes,
        cv_file_url=candidate.cv_file_url,
        is_reviewed_by_current_user=is_reviewed,
        created_at=candidate.created_at,
        scores=[ScoreResponse.model_validate(s) for s in scores],
    )


@router.post("", response_model=CandidateDetail, status_code=status.HTTP_201_CREATED, response_model_exclude_none=True)
def create_candidate_endpoint(
    data: CandidateCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new candidate."""
    candidate = create_candidate(db, data)

    # Notify reviewer if assigned during creation
    if data.assigned_reviewer_id is not None and current_user.role == "admin":
        notify_reviewer_assigned(db, candidate, current_user)

    return get_candidate_endpoint(candidate.id, db, current_user)


@router.patch("/{candidate_id}", response_model=CandidateDetail, response_model_exclude_none=True)
def update_candidate_endpoint(
    candidate_id: int,
    data: CandidateUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update a candidate (status, internal_notes)."""
    # Only admins can update internal_notes
    if data.internal_notes is not None and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can update internal notes",
        )

    # Check if reviewer is being assigned (to trigger notification)
    old_candidate = get_candidate(db, candidate_id)
    was_already_assigned = old_candidate and old_candidate.assigned_reviewer_id is not None

    # Bug 2: Permission check - reviewers can only edit candidates assigned to them.
    # Allow editing if candidate is unassigned (assigned_reviewer_id is None).
    # Uses the already-fetched old_candidate to avoid a redundant DB query.
    if (
        current_user.role == "reviewer"
        and old_candidate
        and old_candidate.assigned_reviewer_id is not None
        and old_candidate.assigned_reviewer_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to edit this candidate",
        )

    candidate = update_candidate(db, candidate_id, data)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # Notify reviewer if newly assigned
    if (
        candidate.assigned_reviewer_id is not None
        and not was_already_assigned
        and current_user.role == "admin"
    ):
        notify_reviewer_assigned(db, candidate, current_user)

    return get_candidate_endpoint(candidate_id, db, current_user)


@router.delete("/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_candidate_endpoint(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft delete a candidate (sets status to archived). Admin-only."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can delete candidates",
        )
    if not soft_delete_candidate(db, candidate_id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")


@router.patch("/{candidate_id}/restore", response_model=CandidateDetail, response_model_exclude_none=True)
def restore_candidate_endpoint(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore an archived candidate. Admin-only."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can restore candidates",
        )
    if not restore_candidate(db, candidate_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Candidate not found or not archived",
        )
    return get_candidate_endpoint(candidate_id, db, current_user)
