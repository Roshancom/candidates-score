from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Column, Integer, String, Float, ForeignKey, Text, Index
from sqlalchemy.orm import relationship
from app.database import Base, UtcDateTime


class CandidateStatus(str, Enum):
    """Allowed statuses for a candidate's lifecycle."""
    NEW = "new"
    REVIEWED = "reviewed"
    HIRED = "hired"
    REJECTED = "rejected"
    ARCHIVED = "archived"


VALID_STATUSES = {s.value for s in CandidateStatus}


class Candidate(Base):
    __tablename__ = "candidates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    role_applied = Column(String(255), nullable=False)
    status = Column(String(50), default="new", index=True)
    skills = Column(Text, default="[]")  # JSON list
    internal_notes = Column(Text, default="")
    cv_file_url = Column(String(500), nullable=True)  # path/name to uploaded CV
    cv_content_type = Column(String(100), nullable=True, default="application/pdf")  # MIME type
    assigned_reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    assigned_date = Column(UtcDateTime, nullable=True)
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc))
    deleted_at = Column(UtcDateTime, nullable=True)  # soft delete
    is_seed_data = Column(Integer, default=0)  # 0 = real, 1 = seed/test data
    seed_batch_id = Column(String(36), nullable=True)  # UUID batch identifier
    ai_summary = Column(Text, nullable=True)  # Cached AI-generated summary
    ai_summary_generated_at = Column(UtcDateTime, nullable=True)  # When summary was generated

    scores = relationship("Score", back_populates="candidate", cascade="all, delete-orphan")
    assigned_reviewer = relationship("User", foreign_keys=[assigned_reviewer_id])

    __table_args__ = (
        Index("idx_candidates_role_applied", "role_applied"),
    )


class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=False, index=True)
    category = Column(String(100), nullable=False)
    score = Column(Float, nullable=False)  # 1-5
    reviewer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    note = Column(Text, default="")
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc))

    candidate = relationship("Candidate", back_populates="scores")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    type = Column(String(50), nullable=False)  # "assignment", "score_submitted", "candidate_created"
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    candidate_id = Column(Integer, ForeignKey("candidates.id"), nullable=True)
    is_read = Column(Integer, default=0)  # 0 = unread, 1 = read
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(50), default="reviewer")  # "reviewer" or "admin"
    created_at = Column(UtcDateTime, default=lambda: datetime.now(timezone.utc))
