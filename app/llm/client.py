"""Anthropic LLM client for code review."""
import json
import os
import time
from typing import Any

import anthropic

from app import metrics
from app.logging_config import get_logger

logger = get_logger(__name__)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

_DEFAULT_SYSTEM_PROMPT = """You are an expert code reviewer. Analyze the provided diff and identify issues.

Return ONLY a JSON array of objects. Each object must have:
- "file": the file path (string)
- "line": the line number in the new file (integer, must be an added line)
- "severity": one of "info", "warning", "error"
- "comment": a clear, actionable review comment (string)

Focus on: bugs, security vulnerabilities, performance problems, and significant code quality issues.
Ignore minor style issues. Return an empty array [] if there are nothing worth flagging."""


def review_diff(
    diff: str,
    repo_language: str,
    few_shot_examples: list[dict[str, Any]],
    prompt_template: str | None = None,
) -> list[dict[str, Any]]:
    """Call Claude to review a diff. Returns a list of comment objects."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    system_prompt = prompt_template or _DEFAULT_SYSTEM_PROMPT

    examples_text = ""
    if few_shot_examples:
        examples_text = "\n\nExamples of good review comments accepted by developers:\n"
        for ex in few_shot_examples[:10]:
            examples_text += f"\nDiff snippet:\n```\n{ex['diff_snippet']}\n```\nComment: {ex['body']}\n"

    user_message = (
        f"Repository primary language: {repo_language}\n"
        f"{examples_text}\n"
        f"Review this diff:\n\n```diff\n{diff}\n```\n\n"
        "Return only a JSON array of review comments."
    )

    start = time.time()
    try:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        metrics.llm_latency_seconds.observe(time.time() - start)

        content = response.content[0].text.strip()
        # Strip markdown code fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
            content = content.strip()

        result = json.loads(content)
        return result if isinstance(result, list) else []
    except Exception as exc:
        metrics.llm_latency_seconds.observe(time.time() - start)
        logger.error("llm_review_failed", error=str(exc))
        return []
