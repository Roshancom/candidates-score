"""
Candidates router — combines sub-routers for CRUD, scores, CV files,
admin seed data, and streaming into a single /candidates router.

Route registration order (critical: fixed paths like /archived, /review,
/seed/count must be registered BEFORE /{candidate_id} to avoid FastAPI
matching them as candidate_id parameters):

1. crud (includes /, /review, /archived, /{candidate_id}, create, update, delete, restore)
2. scores (includes /{candidate_id}/scores, /{candidate_id}/admin-score, /{candidate_id}/summary)
3. cv_files (includes /{candidate_id}/cv GET + POST)
4. seed (includes /seed/count, /admin/seed POST + DELETE)
5. streaming (includes /{candidate_id}/stream SSE)
"""

from fastapi import APIRouter
from app.routers.candidates import crud, scores, cv_files, seed, streaming

router = APIRouter(tags=["candidates"])

# Order matters — fixed paths before parameterized paths
# Each sub-router's routes are prefixed with /candidates here
router.include_router(crud.router, prefix="/candidates")
router.include_router(scores.router, prefix="/candidates")
router.include_router(cv_files.router, prefix="/candidates")
router.include_router(seed.router, prefix="/candidates")
router.include_router(streaming.router, prefix="/candidates")
