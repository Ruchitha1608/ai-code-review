"""Celery task: fetch PR diff, call LLM, post GitHub review, persist results."""
import os
from datetime import datetime

import structlog

from app.celery_app import celery_app
from app.logging_config import configure_logging

configure_logging()
logger = structlog.get_logger(__name__)

PROMPTS_DIR = os.environ.get("PROMPTS_DIR", "./prompts")


@celery_app.task(name="app.tasks.review.review_pr", bind=True, max_retries=3)
def review_pr(self, payload: dict) -> None:
    """Review a pull request end-to-end."""
    repo = payload["repo_full_name"]
    pr_number = payload["pr_number"]
    head_sha = payload["head_sha"]
    pr_title = payload.get("pr_title", "")
    token = payload.get("installation_token", "")

    log = logger.bind(repo=repo, pr_number=pr_number, task_id=self.request.id)
    log.info("review_pr_started")

    try:
        from app.github import client as gh
        from app.llm import client as llm
        from app.diff_parser import get_changed_lines, parse_diff

        # 1. Set commit status to pending
        try:
            gh.set_commit_status(repo, head_sha, "pending", "AI review in progress…", token)
        except Exception:
            pass  # Don't block the review if status API fails

        # 2. Fetch diff
        diff_text = gh.get_pr_diff(repo, pr_number, token)
        if not diff_text.strip():
            log.info("review_pr_empty_diff")
            gh.set_commit_status(repo, head_sha, "success", "No changes to review", token)
            return

        # 3. Get repo primary language
        try:
            languages = gh.get_repo_languages(repo, token)
            repo_language = max(languages, key=languages.get) if languages else "unknown"
        except Exception:
            repo_language = "unknown"

        # 4. Load past accepted comments (few-shot examples) from DB
        few_shot_examples = _get_few_shot_examples(repo)

        # 5. Load latest prompt version
        prompt_template = _load_latest_prompt()

        # 6. Call LLM
        comments = llm.review_diff(diff_text, repo_language, few_shot_examples, prompt_template)
        log.info("llm_review_complete", comment_count=len(comments))

        if not comments:
            log.info("review_pr_no_comments")
            gh.set_commit_status(repo, head_sha, "success", "No issues found", token)
            return

        # 7. Filter out ignored file patterns
        ignore_patterns = _get_ignore_patterns(repo)
        comments = _filter_ignored_files(comments, ignore_patterns)

        # 8. Filter comments to lines that actually appear in the diff
        changed = get_changed_lines(diff_text)
        valid_comments = [c for c in comments if (c.get("file"), c.get("line")) in changed]
        if not valid_comments:
            log.info("review_pr_no_valid_comments")
            gh.set_commit_status(repo, head_sha, "success", "No issues found", token)
            return

        # 9. Post inline review comments
        from app import metrics
        github_review_id = gh.post_review(repo, pr_number, head_sha, valid_comments, token)
        metrics.review_posted_total.labels(repo=repo).inc()
        log.info("review_posted", github_review_id=github_review_id)

        # 10. Post summary comment
        try:
            gh.post_summary_comment(repo, pr_number, valid_comments, token)
        except Exception:
            pass  # Summary is best-effort

        # 11. Set final commit status
        error_count = sum(1 for c in valid_comments if c.get("severity") == "error")
        if error_count:
            gh.set_commit_status(
                repo, head_sha, "failure",
                f"AI review found {error_count} error(s)", token
            )
        else:
            gh.set_commit_status(repo, head_sha, "success", "AI review passed", token)

        # 12. Persist to DB
        prompt_version = _get_active_prompt_version()
        _persist_review(
            repo, pr_number, pr_title, head_sha,
            github_review_id, prompt_version, valid_comments, diff_text
        )
        log.info("review_pr_complete")

    except Exception as exc:
        log.error("review_pr_failed", error=str(exc))
        try:
            from app.github import client as gh
            gh.set_commit_status(repo, head_sha, "error", "AI review failed", token)
        except Exception:
            pass
        raise self.retry(exc=exc, countdown=60)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_few_shot_examples(repo: str) -> list[dict]:
    from app.database import get_sync_db
    from app.models import Comment, Feedback, FeedbackSignal, Review
    from sqlalchemy import select
    from datetime import timedelta

    cutoff = datetime.utcnow() - timedelta(days=30)
    db = get_sync_db()
    try:
        stmt = (
            select(Comment.body, Comment.diff_snippet)
            .join(Review, Comment.review_id == Review.id)
            .join(Feedback, Feedback.comment_id == Comment.id)
            .where(
                Review.repo_full_name == repo,
                Feedback.signal == FeedbackSignal.accepted,
                Feedback.created_at >= cutoff,
            )
            .limit(10)
        )
        rows = db.execute(stmt).fetchall()
        return [{"body": r.body, "diff_snippet": r.diff_snippet or ""} for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def _load_latest_prompt() -> str | None:
    version_path = _get_active_prompt_file_path()
    if version_path and os.path.exists(version_path):
        with open(version_path) as f:
            return f.read()
    return None


def _get_active_prompt_file_path() -> str | None:
    from app.database import get_sync_db
    from app.models import PromptVersion
    from sqlalchemy import select

    db = get_sync_db()
    try:
        row = db.execute(
            select(PromptVersion.file_path)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .order_by(PromptVersion.created_at.desc())
            .limit(1)
        ).fetchone()
        return row.file_path if row else None
    except Exception:
        return None
    finally:
        db.close()


def _get_active_prompt_version() -> str | None:
    from app.database import get_sync_db
    from app.models import PromptVersion
    from sqlalchemy import select

    db = get_sync_db()
    try:
        row = db.execute(
            select(PromptVersion.version)
            .where(PromptVersion.is_active == True)  # noqa: E712
            .order_by(PromptVersion.created_at.desc())
            .limit(1)
        ).fetchone()
        return row.version if row else None
    except Exception:
        return None
    finally:
        db.close()


def _get_ignore_patterns(repo: str) -> list[str]:
    from app.database import get_sync_db
    from app.models import IgnorePattern
    from sqlalchemy import select

    db = get_sync_db()
    try:
        rows = db.execute(
            select(IgnorePattern.pattern).where(IgnorePattern.repo_full_name == repo)
        ).fetchall()
        return [r.pattern for r in rows]
    except Exception:
        return []
    finally:
        db.close()


def _filter_ignored_files(comments: list[dict], patterns: list[str]) -> list[dict]:
    if not patterns:
        return comments
    import fnmatch
    return [
        c for c in comments
        if not any(fnmatch.fnmatch(c.get("file", ""), p) for p in patterns)
    ]


def _persist_review(
    repo: str,
    pr_number: int,
    pr_title: str,
    head_sha: str,
    github_review_id: int,
    prompt_version: str | None,
    comments: list[dict],
    diff_text: str,
) -> None:
    from app.database import get_sync_db
    from app.models import Comment, Review, SeverityLevel
    from app.diff_parser import parse_diff

    # Build a lookup: (file, line) -> content for snippets
    hunk_map = {(h.file, h.line): h.content for h in parse_diff(diff_text)}

    db = get_sync_db()
    try:
        review = Review(
            repo_full_name=repo,
            pr_number=pr_number,
            pr_title=pr_title,
            head_sha=head_sha,
            github_review_id=github_review_id,
            prompt_version=prompt_version,
        )
        db.add(review)
        db.flush()

        for c in comments:
            severity_val = c.get("severity", "info")
            try:
                severity = SeverityLevel(severity_val)
            except ValueError:
                severity = SeverityLevel.info

            snippet = hunk_map.get((c["file"], c["line"]), "")
            comment = Comment(
                review_id=review.id,
                file_path=c["file"],
                line_number=c["line"],
                severity=severity,
                body=c["comment"],
                diff_snippet=snippet,
            )
            db.add(comment)

        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
