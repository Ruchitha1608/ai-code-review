"""POST /webhook — receive GitHub events, validate HMAC, enqueue review tasks."""
import hashlib
import hmac
import json
import os

from fastapi import APIRouter, HTTPException, Request, Response

from app import metrics
from app.logging_config import get_logger

logger = get_logger(__name__)
router = APIRouter()

_WEBHOOK_SECRET: bytes = os.environ.get("GITHUB_WEBHOOK_SECRET", "").encode()


def validate_signature(secret: bytes, body: bytes, signature_header: str) -> bool:
    """Return True if the HMAC-SHA256 signature matches the request body."""
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_header)


@router.post("/webhook")
async def handle_webhook(request: Request) -> Response:
    body = await request.body()
    sig = request.headers.get("X-Hub-Signature-256", "")

    if _WEBHOOK_SECRET and not validate_signature(_WEBHOOK_SECRET, body, sig):
        logger.warning("invalid_webhook_signature", sig=sig[:20])
        raise HTTPException(status_code=401, detail="Invalid signature")

    event_type = request.headers.get("X-GitHub-Event", "unknown")
    payload = json.loads(body)
    action = payload.get("action", "unknown")

    metrics.webhook_received_total.labels(event_type=event_type, action=action).inc()

    if event_type == "pull_request" and action in ("opened", "synchronize"):
        pr = payload["pull_request"]
        task_payload = {
            "repo_full_name": pr["base"]["repo"]["full_name"],
            "pr_number": pr["number"],
            "head_sha": pr["head"]["sha"],
            "pr_title": pr.get("title", ""),
        }
        from app.tasks.review import review_pr
        review_pr.delay(task_payload)
        logger.info(
            "review_enqueued",
            repo=task_payload["repo_full_name"],
            pr_number=task_payload["pr_number"],
        )

    return Response(status_code=200)
