import json
import os

from app.models import Candidate
from app.schemas import CandidateListItem

# Path where uploaded CVs are stored
# Current file: backend/app/routers/candidates/helpers.py
# Go up 3 levels to reach backend/app/
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
)
os.makedirs(UPLOAD_DIR, exist_ok=True)

VALID_STATUSES = {"new", "reviewed", "hired", "rejected", "archived"}


def _parse_skills(candidate: Candidate) -> list:
    try:
        return json.loads(candidate.skills) if candidate.skills else []
    except (json.JSONDecodeError, TypeError):
        return []


def _candidate_to_list_item(candidate: Candidate) -> CandidateListItem:
    return CandidateListItem(
        id=candidate.id,
        name=candidate.name,
        email=candidate.email,
        role_applied=candidate.role_applied,
        status=candidate.status,
        skills=_parse_skills(candidate),
        created_at=candidate.created_at,
    )
