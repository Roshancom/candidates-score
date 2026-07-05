from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import NotificationListResponse, NotificationResponse, NotificationUpdate
from app.auth import get_current_user
from app.services.notification_service import (
    get_notifications,
    get_unread_count,
    mark_notifications_read,
)

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationListResponse)
def list_notifications(
    limit: int = Query(20, ge=1, le=50),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get notifications for the current user, ordered by most recent first."""
    notifications, total = get_notifications(
        db=db,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )
    unread_count = get_unread_count(db, current_user.id)

    return NotificationListResponse(
        items=[NotificationResponse.model_validate(n) for n in notifications],
        unread_count=unread_count,
    )


@router.get("/unread-count", response_model=dict)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get the count of unread notifications."""
    count = get_unread_count(db, current_user.id)
    return {"unread_count": count}


@router.patch("/read", response_model=dict)
def mark_read(
    data: NotificationUpdate,
    notification_ids: Optional[list[int]] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Mark notifications as read.
    If notification_ids is provided, only those are marked.
    Otherwise, all unread notifications are marked.
    """
    updated = mark_notifications_read(
        db=db,
        user_id=current_user.id,
        notification_ids=notification_ids,
    )
    return {"updated": updated}
