"""Pure unified diff parser — no subprocess, no git CLI calls."""

from __future__ import annotations

import re

from ..models import DiffFileChange

_DIFF_GIT_RE = re.compile(r"^diff --git a/(.+) b/(.+)$")
_OLD_PATH_RE = re.compile(r"^--- (.+)$")
_NEW_PATH_RE = re.compile(r"^\+\+\+ (.+)$")


def parse_diff_text(diff_text: str) -> list[DiffFileChange]:
    """Parse a unified diff string into a list of DiffFileChange objects.

    Counts only real added/deleted lines; skips all metadata lines.
    Does not run git or any subprocess.
    """
    if not diff_text.strip():
        return []

    results: list[DiffFileChange] = []

    # Current file state
    git_a: str | None = None
    git_b: str | None = None
    old_path: str | None = None
    new_path: str | None = None
    lines_added: int = 0
    lines_deleted: int = 0
    in_hunk: bool = False

    def _flush() -> None:
        nonlocal git_a, git_b, old_path, new_path, lines_added, lines_deleted, in_hunk
        if git_b is None:
            return
        # Determine status and effective paths
        if old_path == "/dev/null":
            status = "added"
            path = git_b
            effective_old: str | None = None
        elif new_path == "/dev/null":
            status = "deleted"
            path = git_a or git_b
            effective_old = None
        elif git_a != git_b:
            status = "renamed"
            path = git_b
            effective_old = git_a
        else:
            status = "modified"
            path = git_b
            effective_old = None

        results.append(
            DiffFileChange(
                path=path,
                old_path=effective_old,
                status=status,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
            )
        )
        git_a = git_b = old_path = new_path = None
        lines_added = lines_deleted = 0
        in_hunk = False

    for line in diff_text.splitlines():
        # New file section
        m = _DIFF_GIT_RE.match(line)
        if m:
            _flush()
            git_a = _strip_prefix(m.group(1))
            git_b = _strip_prefix(m.group(2))
            in_hunk = False
            continue

        # Old path (--- line)
        if line.startswith("--- ") and not in_hunk:
            m2 = _OLD_PATH_RE.match(line)
            if m2:
                raw = m2.group(1).strip()
                old_path = "/dev/null" if raw == "/dev/null" else _strip_prefix(raw)
            continue

        # New path (+++ line)
        if line.startswith("+++ ") and not in_hunk:
            m3 = _NEW_PATH_RE.match(line)
            if m3:
                raw = m3.group(1).strip()
                new_path = "/dev/null" if raw == "/dev/null" else _strip_prefix(raw)
            continue

        # Hunk header — enters hunk mode
        if line.startswith("@@"):
            in_hunk = True
            continue

        # Only count lines inside a hunk
        if not in_hunk:
            continue

        if line.startswith("+"):
            lines_added += 1
        elif line.startswith("-"):
            lines_deleted += 1
        # context lines (space prefix) and "\ No newline at end of file" are skipped

    _flush()
    return results


def _strip_prefix(path: str) -> str:
    """Remove a/ or b/ prefix that git adds to paths."""
    if path.startswith(("a/", "b/")):
        return path[2:]
    return path
