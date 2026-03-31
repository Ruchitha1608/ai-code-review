"""Celery tasks: ingest developer feedback and nightly prompt versioning."""
import os
from datetime import datetime, timedelta

import structlog

from app.celery_app import celery_app
from app.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

PROMPTS_DIR = os.environ.get("PROMPTS_DIR", "./prompts")


@celery_app.task(name="app.tasks.feedback.ingest_feedback", bind=True)
def ingest_feedback(self, comment_id: int, signal: str) -> None:
    """Store a developer feedback signal in Postgres."""
    log = logger.bind(comment_id=comment_id, signal=signal, task_id=self.request.id)
    log.info("ingest_feedback_started")

    from app.database import get_sync_db
    from app.models import Feedback, FeedbackSignal

    try:
        signal_enum = FeedbackSignal(signal)
    except ValueError:
        log.error("invalid_signal", signal=signal)
        return

    db = get_sync_db()
    try:
        db.add(Feedback(comment_id=comment_id, signal=signal_enum))
        db.commit()
        log.info("ingest_feedback_complete")
    except Exception as exc:
        db.rollback()
        log.error("ingest_feedback_failed", error=str(exc))
        raise
    finally:
        db.close()


@celery_app.task(name="app.tasks.feedback.update_prompt_version")
def update_prompt_version() -> None:
    """Nightly task: build few-shot prompt from accepted comments and save a new version."""
    log = logger.bind(task="update_prompt_version")
    log.info("update_prompt_version_started")

    examples = _fetch_accepted_examples()
    if not examples:
        log.info("update_prompt_version_no_examples")
        return

    version = datetime.utcnow().strftime("v%Y%m%d_%H%M%S")
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    file_path = os.path.join(PROMPTS_DIR, f"prompt_{version}.txt")

    prompt_content = _build_prompt(examples)
    with open(file_path, "w") as f:
        f.write(prompt_content)

    _save_prompt_version(version, file_path)
    log.info("update_prompt_version_complete", version=version, example_count=len(examples))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fetch_accepted_examples() -> list[dict]:
    from app.database import get_sync_db
    from app.models import Comment, Feedback, FeedbackSignal
    from sqlalchemy import select

    cutoff = datetime.utcnow() - timedelta(days=30)
    db = get_sync_db()
    try:
        rows = db.execute(
            select(Comment.body, Comment.diff_snippet)
            .join(Feedback, Feedback.comment_id == Comment.id)
            .where(
                Feedback.signal == FeedbackSignal.accepted,
                Feedback.created_at >= cutoff,
                Comment.diff_snippet.isnot(None),
            )
            .limit(50)
        ).fetchall()
        return [{"body": r.body, "diff_snippet": r.diff_snippet} for r in rows]
    except Exception as exc:
        logger.error("fetch_accepted_examples_failed", error=str(exc))
        return []
    finally:
        db.close()


def _build_prompt(examples: list[dict]) -> str:
    lines = [
        "You are an expert code reviewer. Analyze the provided diff and identify issues.\n",
        "Return ONLY a JSON array of objects with keys: file, line, severity, comment.\n",
        "severity must be one of: info, warning, error.\n",
        "Focus on bugs, security issues, and significant code quality problems.\n",
        "\n--- Few-shot examples from accepted reviews ---\n",
    ]
    for ex in examples:
        lines.append(f"\nDiff snippet:\n```\n{ex['diff_snippet']}\n```")
        lines.append(f"Comment: {ex['body']}\n")
    lines.append("\n--- End of examples ---\n")
    return "".join(lines)


def _save_prompt_version(version: str, file_path: str) -> None:
    from app.database import get_sync_db
    from app.models import PromptVersion

    db = get_sync_db()
    try:
        # Deactivate all previous versions
        db.query(PromptVersion).filter(PromptVersion.is_active == True).update(  # noqa: E712
            {"is_active": False}
        )
        db.add(PromptVersion(version=version, file_path=file_path, is_active=True))
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("save_prompt_version_failed", error=str(exc))
        raise
    finally:
        db.close()
