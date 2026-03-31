"""GitHub API client for fetching PR diffs and posting reviews."""
import os
from typing import Any

import httpx

from app.logging_config import get_logger

logger = get_logger(__name__)

GITHUB_API_BASE = "https://api.github.com"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")


def _headers(token: str, accept: str = "application/vnd.github.v3+json") -> dict:
    return {"Authorization": f"token {token}", "Accept": accept}


def get_pr_diff(repo_full_name: str, pr_number: int, token: str = "") -> str:
    """Fetch the unified diff for a pull request."""
    token = token or GITHUB_TOKEN
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}"
    resp = httpx.get(
        url,
        headers=_headers(token, "application/vnd.github.v3.diff"),
        follow_redirects=True,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.text


def get_repo_languages(repo_full_name: str, token: str = "") -> dict[str, int]:
    """Fetch the programming languages used in a repo."""
    token = token or GITHUB_TOKEN
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/languages"
    resp = httpx.get(url, headers=_headers(token), timeout=10)
    resp.raise_for_status()
    return resp.json()


def set_commit_status(
    repo_full_name: str,
    head_sha: str,
    state: str,
    description: str,
    token: str = "",
) -> None:
    """Set a GitHub commit status. state is one of: pending, success, failure, error."""
    token = token or GITHUB_TOKEN
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/statuses/{head_sha}"
    payload = {
        "state": state,
        "description": description,
        "context": "ai-code-review",
    }
    resp = httpx.post(url, json=payload, headers=_headers(token), timeout=10)
    resp.raise_for_status()


def post_review(
    repo_full_name: str,
    pr_number: int,
    head_sha: str,
    comments: list[dict[str, Any]],
    token: str = "",
) -> int:
    """Post a PR review with inline comments. Returns the GitHub review ID."""
    token = token or GITHUB_TOKEN
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/pulls/{pr_number}/reviews"

    gh_comments = []
    for c in comments:
        body = f"**[{c['severity'].upper()}]** {c['comment']}"
        if c.get("fix"):
            body += f"\n\n```suggestion\n{c['fix']}\n```"
        gh_comments.append({
            "path": c["file"],
            "line": c["line"],
            "side": "RIGHT",
            "body": body,
        })

    payload = {
        "commit_id": head_sha,
        "body": "AI Code Review",
        "event": "COMMENT",
        "comments": gh_comments,
    }

    resp = httpx.post(url, json=payload, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]


def post_summary_comment(
    repo_full_name: str,
    pr_number: int,
    comments: list[dict[str, Any]],
    token: str = "",
) -> None:
    """Post a top-level PR comment with a severity breakdown table."""
    token = token or GITHUB_TOKEN
    url = f"{GITHUB_API_BASE}/repos/{repo_full_name}/issues/{pr_number}/comments"

    errors = [c for c in comments if c.get("severity") == "error"]
    warnings = [c for c in comments if c.get("severity") == "warning"]
    infos = [c for c in comments if c.get("severity") == "info"]

    status_emoji = "🔴" if errors else ("🟡" if warnings else "🟢")
    lines = [
        f"## {status_emoji} AI Code Review Summary",
        "",
        "| Severity | Count |",
        "|----------|-------|",
        f"| 🔴 Error | {len(errors)} |",
        f"| 🟡 Warning | {len(warnings)} |",
        f"| 🔵 Info | {len(infos)} |",
        "",
    ]
    if errors:
        lines.append("**Errors (must fix):**")
        for c in errors:
            lines.append(f"- `{c['file']}:{c['line']}` — {c['comment']}")
        lines.append("")

    body = "\n".join(lines)
    resp = httpx.post(url, json={"body": body}, headers=_headers(token), timeout=10)
    resp.raise_for_status()
