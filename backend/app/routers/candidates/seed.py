from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.auth import require_admin
from app.services.candidate_service import (
    seed_candidates,
    delete_seed_candidates,
    count_seed_candidates,
)

router = APIRouter()


@router.get("/seed/count", response_model=dict)
def count_seed_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """Return count of existing seed data candidates. Admin-only."""
    count = count_seed_candidates(db)
    return {"count": count}


@router.post("/admin/seed", response_model=dict, status_code=status.HTTP_201_CREATED)
def seed_candidates_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Inject 80 realistic fake candidates tagged as seed data.
    Admin-only. Uses a DB transaction.
    """
    try:
        candidates, batch_id = seed_candidates(db, count=80)
        return {
            "inserted": len(candidates),
            "seed_batch_id": batch_id,
            "message": f"Successfully inserted {len(candidates)} test candidates",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed candidates: {str(e)}",
        )


@router.delete("/admin/seed", response_model=dict)
def delete_seed_candidates_endpoint(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Delete all candidates where is_seed_data=True.
    Admin-only. Uses a strict DB filter to never touch real candidates.
    """
    try:
        deleted = delete_seed_candidates(db)
        return {
            "deleted": deleted,
            "message": f"Successfully removed {deleted} test candidate(s)" if deleted > 0 else "No test candidates to remove",
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove seed candidates: {str(e)}",
        )
