from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import Notification, User, Candidate


def create_notification(
    db: Session,
    user_id: int,
    type: str,
    title: str,
    message: str,
    candidate_id: Optional[int] = None,
) -> Notification:
    """Create a new notification for a user."""
    notification = Notification(
        user_id=user_id,
        type=type,
        title=title,
        message=message,
        candidate_id=candidate_id,
        is_read=0,
        created_at=datetime.now(timezone.utc),
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification


def get_notifications(
    db: Session,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> tuple[List[Notification], int]:
    """Get notifications for a user, ordered by most recent first."""
    query = db.query(Notification).filter(Notification.user_id == user_id)
    total = query.count()
    notifications = (
        query.order_by(Notification.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return notifications, total


def get_unread_count(db: Session, user_id: int) -> int:
    """Get the count of unread notifications for a user."""
    return (
        db.query(Notification)
        .filter(Notification.user_id == user_id, Notification.is_read == 0)
        .count()
    )


def mark_notifications_read(
    db: Session,
    user_id: int,
    notification_ids: Optional[list[int]] = None,
) -> int:
    """
    Mark notifications as read. If notification_ids is provided and non-empty, only
    those are marked. Otherwise, all unread notifications are marked.
    Returns the number of notifications updated.
    """
    query = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.is_read == 0,
    )

    if notification_ids is not None and len(notification_ids) > 0:
        query = query.filter(Notification.id.in_(notification_ids))

    count = query.update({"is_read": 1})
    db.commit()
    return count


def notify_reviewer_assigned(
    db: Session,
    candidate: Candidate,
    assigned_by: User,
) -> Optional[Notification]:
    """Notify a reviewer that a candidate has been assigned to them."""
    if not candidate.assigned_reviewer_id:
        return None

    # Dedup check: don't create a duplicate assignment notification if one already exists
    existing = (
        db.query(Notification)
        .filter(
            Notification.user_id == candidate.assigned_reviewer_id,
            Notification.type == "assignment",
            Notification.candidate_id == candidate.id,
        )
        .first()
    )
    if existing:
        return existing

    notification = create_notification(
        db=db,
        user_id=candidate.assigned_reviewer_id,
        type="assignment",
        title="New Candidate Assigned",
        message=(
            f"Admin {assigned_by.email} has assigned "
            f"\"{candidate.name}\" ({candidate.role_applied}) to you for review."
        ),
        candidate_id=candidate.id,
    )
    return notification


def notify_score_submitted(
    db: Session,
    candidate: Candidate,
    reviewer: User,
    is_first_score: bool,
) -> list[Notification]:
    """Notify all admins that a reviewer submitted a score."""
    admins = db.query(User).filter(User.role == "admin").all()

    if is_first_score:
        title = f"Review Started: {candidate.name}"
        message = (
            f"Reviewer {reviewer.email} has submitted their first score "
            f"for \"{candidate.name}\" ({candidate.role_applied})."
        )
    else:
        title = f"Score Updated: {candidate.name}"
        message = (
            f"Reviewer {reviewer.email} has submitted an additional score "
            f"for \"{candidate.name}\" ({candidate.role_applied})."
        )

    notifications = []
    for admin in admins:
        # Dedup check: don't create a duplicate notification with same type + candidate + title
        existing = (
            db.query(Notification)
            .filter(
                Notification.user_id == admin.id,
                Notification.type == "score_submitted",
                Notification.candidate_id == candidate.id,
                Notification.title == title,
                Notification.message == message,
            )
            .first()
        )
        if existing:
            notifications.append(existing)
            continue

        n = create_notification(
            db=db,
            user_id=admin.id,
            type="score_submitted",
            title=title,
            message=message,
            candidate_id=candidate.id,
        )
        notifications.append(n)

    return notifications
