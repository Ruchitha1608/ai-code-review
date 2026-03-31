"""POST /feedback — record developer signals on review comments."""
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from app import metrics
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()


class FeedbackRequest(BaseModel):
    comment_id: int
    signal: Literal["accepted", "rejected", "ignored"]


@router.post("/feedback", status_code=202)
async def record_feedback(body: FeedbackRequest) -> dict:
    from app.tasks.feedback import ingest_feedback

    ingest_feedback.delay(body.comment_id, body.signal)
    metrics.feedback_signal_total.labels(signal=body.signal).inc()
    logger.info("feedback_enqueued", comment_id=body.comment_id, signal=body.signal)
    return {"status": "accepted"}
