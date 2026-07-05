import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Candidate, User
from app.schemas import (
    AdminScoreUpdate,
    ScoreCreate,
    ScoreResponse,
    ScoreUpdate,
    SummaryResponse,
)
from app.auth import get_current_user
from app.services.candidate_service import (
    get_candidate,
    submit_score,
    update_score,
    admin_update_score,
    get_scores_for_candidate,
    get_scores_for_reviewer,
    has_reviewer_submitted_scores,
)
from app.routers.candidates.helpers import _parse_skills

router = APIRouter()


@router.patch("/{candidate_id}/scores/{score_id}", response_model=ScoreResponse)
def update_score_endpoint(
    candidate_id: int,
    score_id: int,
    data: ScoreUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update an existing score — only the reviewer who submitted the score can edit it."""
    # Permission check: reviewers can only edit scores on candidates assigned to them
    if current_user.role == "reviewer":
        candidate = get_candidate(db, candidate_id)
        if not candidate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
        if candidate.assigned_reviewer_id is not None and candidate.assigned_reviewer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to edit scores for this candidate",
            )

    updated = update_score(db, score_id, data, current_user.id)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Score not found or you are not the owner of this score",
        )
    return ScoreResponse.model_validate(updated)


@router.patch("/{candidate_id}/admin-score/{score_id}", response_model=ScoreResponse)
def admin_update_score_endpoint(
    candidate_id: int,
    score_id: int,
    data: AdminScoreUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Admin-only score update: edits the numeric score value but preserves the reviewer's original note."""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can use this endpoint",
        )

    updated = admin_update_score(db, score_id, data.score)
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Score not found",
        )
    return ScoreResponse.model_validate(updated)


@router.post("/{candidate_id}/scores", response_model=ScoreResponse, status_code=status.HTTP_201_CREATED)
def submit_score_endpoint(
    candidate_id: int,
    data: ScoreCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit a score for a candidate."""
    # Bug 2: Permission check - reviewers can only score candidates assigned to them.
    # Allow scoring if candidate is unassigned (assigned_reviewer_id is None).
    if current_user.role == "reviewer":
        candidate = get_candidate(db, candidate_id)
        if not candidate:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
        if candidate.assigned_reviewer_id is not None and candidate.assigned_reviewer_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not authorized to score this candidate",
            )

    # Prevent duplicate scores for the same category by the same reviewer
    existing_scores = get_scores_for_reviewer(db, candidate_id, current_user.id)
    if any(s.category == data.category for s in existing_scores):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"You have already submitted a score for category '{data.category}'",
        )

    score = submit_score(db, candidate_id, data, current_user.id)
    if not score:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")
    return ScoreResponse.model_validate(score)


@router.post("/{candidate_id}/summary", response_model=SummaryResponse)
async def generate_summary(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mock AI summary generation — simulates an async LLM call with a 2-second delay.
    Respects RBAC: reviewers see only their own scores, admins see all.
    """
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidate not found")

    # Bug 2: Permission check - reviewers can only generate summaries for assigned candidates.
    # Allow if candidate is unassigned (assigned_reviewer_id is None).
    if (
        current_user.role == "reviewer"
        and candidate.assigned_reviewer_id is not None
        and candidate.assigned_reviewer_id != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not authorized to view this candidate's summary",
        )

    # Simulate async LLM call
    await asyncio.sleep(2)

    # Respect RBAC: reviewer sees only their own scores
    if current_user.role == "admin":
        scores = get_scores_for_candidate(db, candidate_id)
    else:
        scores = get_scores_for_reviewer(db, candidate_id, current_user.id)
    avg_score = sum(s.score for s in scores) / len(scores) if scores else 0

    summary = (
        f"Candidate {candidate.name} applied for {candidate.role_applied}. "
        f"Current status: {candidate.status}. "
        f"Skills: {_parse_skills(candidate)}. "
        f"Average score: {avg_score:.1f}/5 across {len(scores)} review(s). "
        f"This is an AI-generated summary based on available scores and profile data."
    )
    return SummaryResponse(summary=summary)
