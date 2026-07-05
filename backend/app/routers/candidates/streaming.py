import asyncio
import json

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import ScoreResponse
from app.auth import get_current_user
from app.services.candidate_service import get_scores_for_candidate

router = APIRouter()


@router.get("/{candidate_id}/stream")
async def stream_scores(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    SSE endpoint streaming score updates in real time (stretch goal).
    """
    async def event_generator():
        # In a real app, this would listen to a pub/sub channel
        # For now, send initial scores and keep connection open
        scores = get_scores_for_candidate(db, candidate_id)
        yield {"event": "scores", "data": json.dumps([ScoreResponse.model_validate(s).model_dump(mode="json") for s in scores])}

        # Keep alive
        while True:
            await asyncio.sleep(30)
            yield {"event": "ping", "data": "keepalive"}

    return EventSourceResponse(event_generator())
