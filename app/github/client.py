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

    gh_comments = [
        {
            "path": c["file"],
            "line": c["line"],
            "side": "RIGHT",
            "body": f"**[{c['severity'].upper()}]** {c['comment']}",
        }
        for c in comments
    ]

    payload = {
        "commit_id": head_sha,
        "body": "AI Code Review",
        "event": "COMMENT",
        "comments": gh_comments,
    }

    resp = httpx.post(url, json=payload, headers=_headers(token), timeout=30)
    resp.raise_for_status()
    return resp.json()["id"]
