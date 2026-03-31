"""Unified diff parser that extracts changed lines with file paths and line numbers."""
import re
from dataclasses import dataclass


@dataclass
class DiffHunk:
    file: str
    line: int      # line number in the new file
    content: str   # line content (without the leading '+')


def parse_diff(diff_text: str) -> list[DiffHunk]:
    """Parse a unified diff and return all added lines with their positions."""
    hunks: list[DiffHunk] = []
    current_file: str | None = None
    new_line_num = 0

    for line in diff_text.splitlines():
        if line.startswith("+++ b/"):
            current_file = line[6:].strip()
        elif line.startswith("@@ "):
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@", line)
            if match:
                new_line_num = int(match.group(1))
        elif current_file:
            if line.startswith("+") and not line.startswith("+++"):
                hunks.append(DiffHunk(file=current_file, line=new_line_num, content=line[1:]))
                new_line_num += 1
            elif line.startswith("-") and not line.startswith("---"):
                pass  # deleted lines don't advance the new-file counter
            elif line.startswith(" "):
                new_line_num += 1

    return hunks


def get_changed_lines(diff_text: str) -> set[tuple[str, int]]:
    """Return a set of (file_path, line_number) pairs for all added lines."""
    return {(h.file, h.line) for h in parse_diff(diff_text)}
