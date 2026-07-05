import os

from app.models import VALID_STATUSES
from app.schemas import PaginationInfo
from app.services.candidate_service import _parse_skills, _candidate_to_list_item

# Path where uploaded CVs are stored
# Current file: backend/app/routers/candidates/helpers.py
# Go up 3 levels to reach backend/app/
UPLOAD_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "uploads",
)
os.makedirs(UPLOAD_DIR, exist_ok=True)



def make_pagination(page: int, page_size: int, total_count: int) -> PaginationInfo:
    """Build a PaginationInfo from page/page_size/total_count."""
    total_pages = max(1, (total_count + page_size - 1) // page_size) if total_count > 0 else 0
    return PaginationInfo(
        page=page,
        page_size=page_size,
        total_count=total_count,
        total_pages=total_pages,
    )

