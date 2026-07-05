import asyncio
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db, SessionLocal
from app.models import Notification, User
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


@router.get("/stream")
async def stream_notifications(
    current_user: User = Depends(get_current_user),
):
    """
    SSE endpoint that streams new notifications in real time.
    Polls the DB every 5 seconds for new unread notifications
    and pushes them to the connected client.
    """
    async def event_generator():
        last_max_id = 0
        while True:
            try:
                db = SessionLocal()
                try:
                    # Query for unread notifications newer than the last seen ID
                    notifs = (
                        db.query(Notification)
                        .filter(
                            Notification.user_id == current_user.id,
                            Notification.is_read == 0,
                            Notification.id > last_max_id,
                        )
                        .order_by(Notification.id.asc())
                        .all()
                    )
                    if notifs:
                        for n in notifs:
                            data = {
                                "id": n.id,
                                "user_id": n.user_id,
                                "type": n.type,
                                "title": n.title,
                                "message": n.message,
                                "candidate_id": n.candidate_id,
                                "is_read": bool(n.is_read),
                                "created_at": n.created_at.isoformat() if n.created_at else None,
                            }
                            yield {"event": "notification", "data": json.dumps(data)}
                            last_max_id = max(last_max_id, n.id)
                finally:
                    db.close()
            except Exception:
                pass
            await asyncio.sleep(5)

    return EventSourceResponse(event_generator())


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
