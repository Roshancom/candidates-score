import json
import uuid
import re
from typing import Optional, List
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.models import Candidate, Score, User, VALID_STATUSES
from app.schemas import (
    CandidateCreate,
    CandidateListItem,
    CandidateDetail,
    CandidateUpdate,
    ScoreCreate,
    ScoreResponse,
)
from app.schemas import ScoreUpdate as ScoreUpdateSchema


from sqlalchemy.orm import Session, Query


def _apply_candidate_filters(
    query: Query,
    status: Optional[str] = None,
    role_applied: Optional[str] = None,
    skill: Optional[str] = None,
    keyword: Optional[str] = None,
) -> Query:
    """Apply common candidate filters (status, role_applied, skill, keyword) to a query."""
    if status:
        query = query.filter(Candidate.status == status)
    if role_applied:
        query = query.filter(Candidate.role_applied == role_applied)
    if keyword:
        query = query.filter(
            or_(
                Candidate.name.ilike(f"%{keyword}%"),
                Candidate.email.ilike(f"%{keyword}%"),
            )
        )
    if skill:
        query = query.filter(Candidate.skills.ilike(f"%{skill}%"))
    return query


def _paginate_query(
    query: Query,
    page: int,
    page_size: int,
    order_col = None,
    order_expr = None,
) -> tuple:
    """Apply pagination (count, offset, limit) to a query and return (results, total).
    Provide either order_col (for simple descending sort) or order_expr (for custom ordering).
    """
    total = query.count()
    page_size = min(max(page_size, 1), 50)
    offset = (page - 1) * page_size
    if order_expr is not None:
        results = query.order_by(*order_expr).offset(offset).limit(page_size).all()
    elif order_col is not None:
        results = query.order_by(order_col.desc()).offset(offset).limit(page_size).all()
    else:
        results = query.offset(offset).limit(page_size).all()
    return results, total


def list_candidates(
    db: Session,
    status: Optional[str] = None,
    role_applied: Optional[str] = None,
    skill: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[Candidate], int]:
    """
    List candidates with SQL-level filtering and pagination.
    Never loads the full table into memory.
    """
    query = db.query(Candidate).filter(Candidate.deleted_at.is_(None))
    query = _apply_candidate_filters(query, status, role_applied, skill, keyword)
    return _paginate_query(query, page, page_size, Candidate.created_at)


def get_candidate(db: Session, candidate_id: int) -> Optional[Candidate]:
    return (
        db.query(Candidate)
        .filter(Candidate.id == candidate_id, Candidate.deleted_at.is_(None))
        .first()
    )



def create_candidate(db: Session, data: CandidateCreate) -> Candidate:
    # Normalize email to lowercase
    email = data.email.strip().lower()

    # Check email uniqueness (including soft-deleted candidates)
    existing = db.query(Candidate).filter(
        func.lower(Candidate.email) == email
    ).first()
    if existing:
        raise ValueError(f"A candidate with email '{email}' already exists")

    # If reviewer is assigned, validate they exist and have role=reviewer
    if data.assigned_reviewer_id is not None:
        reviewer = db.query(User).filter(User.id == data.assigned_reviewer_id).first()
        if not reviewer:
            raise ValueError("Assigned reviewer not found")
        if reviewer.role != "reviewer":
            raise ValueError("Assigned user is not a reviewer")

    candidate = Candidate(
        name=data.name.strip(),
        email=email,
        role_applied=data.role_applied,
        skills=json.dumps(data.skills),
        status="new",
    )
    if data.assigned_reviewer_id is not None:
        candidate.assigned_reviewer_id = data.assigned_reviewer_id
        candidate.assigned_date = datetime.now(timezone.utc)
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def update_candidate(db: Session, candidate_id: int, data: CandidateUpdate) -> Optional[Candidate]:
    candidate = get_candidate(db, candidate_id)
    if not candidate:
        return None

    if data.status is not None:
        if data.status not in VALID_STATUSES:
            raise ValueError(f"Invalid status '{data.status}'. Allowed: {', '.join(sorted(VALID_STATUSES))}")
        candidate.status = data.status
    if data.internal_notes is not None:
        candidate.internal_notes = data.internal_notes
    if data.cv_file_url is not None:
        candidate.cv_file_url = data.cv_file_url
    if data.assigned_reviewer_id is not None and data.assigned_reviewer_id != candidate.assigned_reviewer_id:
        candidate.assigned_reviewer_id = data.assigned_reviewer_id
        candidate.assigned_date = datetime.now(timezone.utc)

    db.commit()
    db.refresh(candidate)
    return candidate


def soft_delete_candidate(db: Session, candidate_id: int) -> bool:
    """Soft delete by setting deleted_at timestamp."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        return False
    candidate.deleted_at = datetime.now(timezone.utc)
    candidate.status = "archived"
    db.commit()
    return True


def restore_candidate(db: Session, candidate_id: int) -> bool:
    """Restore a soft-deleted candidate by clearing deleted_at and resetting status."""
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate or candidate.deleted_at is None:
        return False
    candidate.deleted_at = None
    if candidate.status == "archived":
        candidate.status = "new"
    db.commit()
    return True


def list_archived_candidates(
    db: Session,
    status: Optional[str] = None,
    role_applied: Optional[str] = None,
    skill: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[Candidate], int]:
    """
    List archived (soft-deleted) candidates with SQL-level filtering and pagination.
    Mirrors list_candidates but filters for deleted_at is not None.
    """
    query = db.query(Candidate).filter(
        Candidate.deleted_at.isnot(None),
        Candidate.is_seed_data == 0,  # Exclude seed data from archived list
    )
    query = _apply_candidate_filters(query, status, role_applied, skill, keyword)
    return _paginate_query(query, page, page_size, Candidate.deleted_at)


def update_score(
    db: Session,
    score_id: int,
    data: ScoreUpdateSchema,
    reviewer_id: int,
) -> Optional[Score]:
    """Update an existing score (score value and note) — only the owning reviewer can update."""
    score = db.query(Score).filter(Score.id == score_id, Score.reviewer_id == reviewer_id).first()
    if not score:
        return None
    score.score = data.score
    score.note = data.note
    db.commit()
    db.refresh(score)
    return score


def admin_update_score(
    db: Session,
    score_id: int,
    score_value: float,
) -> Optional[Score]:
    """Admin-only score update: can change the numeric score value but preserves the reviewer's original note."""
    score = db.query(Score).filter(Score.id == score_id).first()
    if not score:
        return None
    score.score = score_value
    # Preserve reviewer's original note — only update the numeric score
    db.commit()
    db.refresh(score)
    return score


def submit_score(
    db: Session,
    candidate_id: int,
    data: ScoreCreate,
    reviewer_id: int,
) -> Optional[Score]:
    # Also include soft-deleted candidates in the check so we can reject archived ones
    candidate = db.query(Candidate).filter(Candidate.id == candidate_id).first()
    if not candidate:
        return None

    # Reject scoring archived candidates
    if candidate.status == "archived" or candidate.deleted_at is not None:
        return None

    # Check if this is the reviewer's first score (to trigger notification)
    existing_scores = get_scores_for_reviewer(db, candidate_id, reviewer_id)
    is_first_score = len(existing_scores) == 0
    is_first_score_overall = candidate_has_any_scores(db, candidate_id) is False

    score = Score(
        candidate_id=candidate_id,
        category=data.category,
        score=data.score,
        note=data.note,
        reviewer_id=reviewer_id,
    )
    db.add(score)

    # Auto-transition: new -> reviewed on first overall score submission
    if is_first_score_overall and candidate.status == "new":
        candidate.status = "reviewed"

    db.commit()
    db.refresh(score)

    # Trigger notification to admins
    from app.models import User as UserModel
    from app.services.notification_service import notify_score_submitted
    reviewer = db.query(UserModel).filter(UserModel.id == reviewer_id).first()
    if reviewer:
        notify_score_submitted(db, candidate, reviewer, is_first_score)

    return score


def get_scores_for_candidate(db: Session, candidate_id: int) -> List[Score]:
    return db.query(Score).filter(Score.candidate_id == candidate_id).all()


def get_scores_for_reviewer(db: Session, candidate_id: int, reviewer_id: int) -> List[Score]:
    """Reviewer can only see their own scores."""
    return (
        db.query(Score)
        .filter(Score.candidate_id == candidate_id, Score.reviewer_id == reviewer_id)
        .all()
    )


def list_candidates_for_reviewer(
    db: Session,
    reviewer_id: int,
    page: int = 1,
    page_size: int = 20,
) -> tuple[List[Candidate], int]:
    """
    List candidates assigned to a specific reviewer, with pagination.
    Includes a flag for whether the reviewer has submitted any scores.
    """
    query = (
        db.query(Candidate)
        .filter(
            Candidate.deleted_at.is_(None),
            Candidate.is_seed_data == 0,  # Exclude seed data from review list
            or_(
                Candidate.assigned_reviewer_id == reviewer_id,
                Candidate.scores.any(),
            ),
        )
    )

    order = Candidate.assigned_date.desc().nullslast(), Candidate.created_at.desc()
    return _paginate_query(query, page, page_size, order_expr=order)


def candidate_has_any_scores(db: Session, candidate_id: int) -> bool:
    """Check if a candidate has any scores from any reviewer."""
    return (
        db.query(Score.id)
        .filter(Score.candidate_id == candidate_id)
        .first()
        is not None
    )


def has_reviewer_submitted_scores(db: Session, candidate_id: int, reviewer_id: int) -> bool:
    """Check if a reviewer has submitted at least one score for a candidate."""
    return (
        db.query(Score)
        .filter(
            Score.candidate_id == candidate_id,
            Score.reviewer_id == reviewer_id,
        )
        .first()
        is not None
    )


def seed_candidates(db: Session, count: int = 80, batch_id: Optional[str] = None) -> tuple[list[Candidate], str]:
    """
    Generate and insert `count` fake candidate records, all tagged with is_seed_data=True
    and a shared seed_batch_id. Returns (candidates, batch_id).

    Uses batch-prefixed emails to guarantee uniqueness across multiple seed runs.
    """
    from faker import Faker

    fake = Faker()
    if batch_id is None:
        batch_id = str(uuid.uuid4())

    # Short unique prefix for emails to avoid collisions across seed batches
    email_prefix = batch_id[:8]

    roles = [
        "Senior Frontend Engineer",
        "Backend Engineer",
        "Full Stack Developer",
        "DevOps Engineer",
        "Data Engineer",
        "Software Engineer",
        "Machine Learning Engineer",
        "Product Manager",
        "QA Engineer",
        "Mobile Developer",
        "Security Engineer",
        "Solutions Architect",
    ]
    # Only use 'new' for seed data to accurately reflect the lifecycle:
    # seeded candidates have no scores, so they should all start as 'new'.
    # Reviewed/hired/rejected statuses imply review activity which isn't
    # present for seed data unless we also generate matching scores.
    statuses = ["new"]
    skill_pool = [
        "Python", "JavaScript", "TypeScript", "React", "Vue.js", "Angular",
        "Node.js", "FastAPI", "Django", "Flask", "PostgreSQL", "MongoDB",
        "Redis", "Docker", "Kubernetes", "AWS", "GCP", "Azure",
        "Terraform", "CI/CD", "GraphQL", "REST APIs", "Go", "Rust",
        "Java", "Spring Boot", "SQL", "NoSQL", "Kafka", "RabbitMQ",
    ]

    candidates = []
    for i in range(count):
        # Use batch-prefixed emails to guarantee uniqueness across runs
        safe_name = re.sub(r'[^a-z0-9]', '', fake.last_name().lower())
        safe_email = f"seed.{email_prefix}.{i}.{safe_name}@example.com"
        candidate = Candidate(
            name=fake.name(),
            email=safe_email,
            role_applied=fake.random_element(roles),
            status=fake.random_element(statuses),
            skills=json.dumps(fake.random_elements(skill_pool, length=fake.random_int(min=2, max=6), unique=True)),
            is_seed_data=1,
            seed_batch_id=batch_id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(candidate)
        candidates.append(candidate)

    db.commit()
    for c in candidates:
        db.refresh(c)

    return candidates, batch_id


def delete_seed_candidates(db: Session, batch_id: Optional[str] = None) -> int:
    """
    Delete only candidates where is_seed_data=1.
    If batch_id is provided, only delete seed data from that batch.
    Returns the number of deleted records.
    Uses a strict filter on is_seed_data to never touch real candidates.
    """
    query = db.query(Candidate).filter(Candidate.is_seed_data == 1)
    if batch_id:
        query = query.filter(Candidate.seed_batch_id == batch_id)

    count = query.count()
    if count == 0:
        return 0

    # Delete in a transaction
    query.delete(synchronize_session="fetch")
    db.commit()
    return count


def count_seed_candidates(db: Session) -> int:
    """Count how many seed data candidates exist."""
    return db.query(Candidate).filter(Candidate.is_seed_data == 1).count()


def _parse_skills(candidate: Candidate) -> list:
    """Parse skills JSON string with error handling."""
    try:
        return json.loads(candidate.skills) if candidate.skills else []
    except (json.JSONDecodeError, TypeError):
        return []


def _candidate_to_list_item(candidate: Candidate) -> CandidateListItem:
    """Convert a Candidate model to a CandidateListItem schema."""
    return CandidateListItem(
        id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        role_applied=candidate.role_applied,
        status=candidate.status,
        skills=_parse_skills(candidate),
        created_at=candidate.created_at,
    )


def serialize_candidate_detail(
    db: Session,
    candidate: Candidate,
    current_user: User,
) -> CandidateDetail:
    """
    Build a CandidateDetail response respecting RBAC:
    - Admin sees all scores, internal_notes
    - Reviewer sees only their own scores, no internal_notes
    """
    # RBAC: admin sees all scores, reviewer sees only their own
    if current_user.role == "admin":
        scores = get_scores_for_candidate(db, candidate.id)
        internal_notes = candidate.internal_notes
    else:
        scores = get_scores_for_reviewer(db, candidate.id, current_user.id)
        internal_notes = None

    is_reviewed = (
        has_reviewer_submitted_scores(db, candidate.id, current_user.id)
        if current_user.role == "reviewer"
        else False
    )

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
        ai_summary=candidate.ai_summary,
        ai_summary_generated_at=candidate.ai_summary_generated_at,
    )


def get_candidates_average_scores(db: Session, candidate_ids: list[int]) -> dict[int, tuple[Optional[float], int]]:
    """
    Get the overall average score and score count for each candidate across ALL reviewers.
    Returns dict of {candidate_id: (avg_score, score_count)}.
    Uses a single grouped query for efficiency.
    """
    if not candidate_ids:
        return {}
    results = (
        db.query(
            Score.candidate_id,
            func.avg(Score.score),
            func.count(Score.id),
        )
        .filter(Score.candidate_id.in_(candidate_ids))
        .group_by(Score.candidate_id)
        .all()
    )
    return {r[0]: (round(float(r[1]), 2), r[2]) for r in results}
