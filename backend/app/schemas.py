from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime


# -------- Auth --------

class UserCreate(BaseModel):
    email: str
    password: str


class UserLogin(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str


class UserResponse(BaseModel):
    id: int
    email: str
    role: str

    model_config = {"from_attributes": True}


# -------- Candidate --------

class ScoreResponse(BaseModel):
    id: int
    category: str
    score: float
    reviewer_id: int
    note: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CandidateListItem(BaseModel):
    id: int
    name: str
    email: str
    role_applied: str
    status: str
    skills: List[str]
    created_at: datetime
    average_score: Optional[float] = None
    score_count: Optional[int] = None

    model_config = {"from_attributes": True}


class ReviewCandidateListItem(BaseModel):
    id: int
    name: str
    email: str
    role_applied: str
    status: str
    skills: List[str]
    created_at: datetime
    assigned_date: Optional[datetime] = None
    assigned_reviewer_id: Optional[int] = None
    cv_file_url: Optional[str] = None
    is_reviewed_by_current_user: bool = False
    is_reviewed_by_anyone: bool = False
    average_score: Optional[float] = None

    model_config = {"from_attributes": True}


class CandidateDetail(BaseModel):
    id: int
    name: str
    email: str
    role_applied: str
    status: str
    skills: List[str]
    internal_notes: Optional[str] = None
    cv_file_url: Optional[str] = None
    is_reviewed_by_current_user: bool = False
    created_at: datetime
    scores: List[ScoreResponse] = []

    model_config = {"from_attributes": True}


class CandidateCreate(BaseModel):
    name: str
    email: str
    role_applied: str
    skills: List[str] = []
    assigned_reviewer_id: Optional[int] = None


class CandidateUpdate(BaseModel):
    status: Optional[str] = None
    internal_notes: Optional[str] = None
    cv_file_url: Optional[str] = None
    assigned_reviewer_id: Optional[int] = None


class PaginationInfo(BaseModel):
    page: int
    page_size: int
    total_count: int
    total_pages: int


class CandidateListResponse(BaseModel):
    data: List[CandidateListItem]
    pagination: PaginationInfo


# -------- Score --------

class ScoreCreate(BaseModel):
    category: str
    score: float
    note: str = ""

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if v < 1 or v > 5:
            raise ValueError("Score must be between 1 and 5")
        return v


class ScoreUpdate(BaseModel):
    score: float
    note: str = ""

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if v < 1 or v > 5:
            raise ValueError("Score must be between 1 and 5")
        return v


class AdminScoreUpdate(BaseModel):
    """Admin-only score update: can only change the numeric score value, not the reviewer's note."""
    score: float

    @field_validator("score")
    @classmethod
    def validate_score(cls, v):
        if v < 1 or v > 5:
            raise ValueError("Score must be between 1 and 5")
        return v


# -------- Summary --------

class SummaryResponse(BaseModel):
    summary: str


# -------- Notifications --------

class NotificationResponse(BaseModel):
    id: int
    user_id: int
    type: str
    title: str
    message: str
    candidate_id: Optional[int] = None
    is_read: bool
    created_at: datetime

    model_config = {"from_attributes": True}

    @field_validator("is_read", mode="before")
    @classmethod
    def coerce_is_read(cls, v):
        if isinstance(v, int):
            return bool(v)
        return v


class NotificationListResponse(BaseModel):
    items: List[NotificationResponse]
    unread_count: int


class NotificationUpdate(BaseModel):
    is_read: bool = True
