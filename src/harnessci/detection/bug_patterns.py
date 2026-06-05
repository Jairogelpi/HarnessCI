"""Bug pattern detection heuristics for generic code quality issues.

Detects: null derefs, resource leaks, SQL injection, XSS, race conditions,
missing error handling, hardcoded secrets, TODOs, dead code, and more.
Complementary to HarnessCI's spec-driven checks — catches general bugs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

SECURITY_PATTERNS: list[tuple[str, str, str]] = [
    # (pattern_name, regex, severity)
    (
        "hardcoded_secret",
        r'(?:password|secret|api_key|apikey|token|auth|credential)s?\s*[=:]\s*["\'](?!["\']{3,})(?!\$)(?!process\.env)(?![A-Z_]{10,})[\w\-]{4,32}["\']',
        "critical",
    ),
    (
        "sql_injection_risk",
        r'(?:execute|exec|query|cursor\.execute)\s*\(\s*[f]?["\']',
        "high",
    ),
    (
        "xss_risk",
        r"(?:innerHTML|outerHTML|document\.write|insertAdjacentHTML|dangerouslySetInnerHTML)\s*\(",
        "high",
    ),
    (
        "command_injection",
        r"(?:os\.system|subprocess\.(?:call|run|Popen))\s*\(",
        "critical",
    ),
    (
        "path_traversal",
        r"(?:open|read|os\.path\.join)\s*\([^)]*\+\s*(?:request|user|input|path)",
        "high",
    ),
    (
        "insecure_random",
        r"(?:random\.random|random\.randint)\s*\(\s*\)",
        "medium",
    ),
    (
        "eval_usage",
        r"\beval\s*\(",
        "critical",
    ),
    (
        "pickle_load",
        r"pickle\.load\s*\(",
        "high",
    ),
    (
        "yaml_load_unsafe",
        r"yaml\.load\s*\([^)]*(?!Loader\s*=\s*yaml\.SafeLoader)",
        "high",
    ),
    (
        "deserialization_risk",
        r"(?:json\.loads|ast\.literal_eval|yaml\.unsafe_load|marshal\.loads)\s*\(",
        "medium",
    ),
]

CODE_QUALITY_PATTERNS: list[tuple[str, str, str]] = [
    (
        "null_check_missing",
        r"(?:if\s+\w+\s+is\s+None|if\s+not\s+\w+\s+is\s+None)(?!\s*:)",
        "medium",
    ),
    (
        "broad_exception",
        r"except\s*:\s*raise|except\s+\w+:\s*pass\s*(?:#|$)|except\s+\w+\s*as\s+\w+:\s*pass",
        "medium",
    ),
    (
        "print_debug_in_code",
        r"\bprint\s*\(",
        "low",
    ),
    (
        "todo_comment",
        r"#\s*(?:TODO|FIXME|HACK|XXX|BUG|RUDE):",
        "info",
    ),
    (
        "todo_comment_urgent",
        r"#\s*(?:TODO|FIXME)\s+[A-Z]",
        "low",
    ),
    (
        "nested_loops_complex",
        r"for\s+\w+\s+in\s+.*:\s*\n\s+for\s+\w+\s+in\s+",
        "low",
    ),
    (
        "magic_number",
        r"(?:timeout|sleep|delay|retry|max_retries|limit|size|count|size)\s*[=:]\s*\b(?:\d{2,}|0x[0-9a-fA-F]{2,})\b",
        "low",
    ),
    (
        "unused_variable",
        r"^\s*(?:_|_{2,}\w+_{2,})\s*=",
        "info",
    ),
    (
        "commented_out_code",
        r"^\s*#\s*(?:def|class|function|if|for|while|return|import)\s+",
        "low",
    ),
    (
        "complex_regex",
        r're\.compile\s*\(\s*["\'][^"\']{80,}[^\\\\]?["\']',
        "low",
    ),
    (
        "long_line",
        r"^.{121,}$",
        "info",
    ),
    (
        "empty_except",
        r"except\s*:\s*(?:#.*)?\s*(?:\n|$)",
        "medium",
    ),
    (
        "return_in_finally",
        r"finally\s*:[^{]*(?:return|break|continue)\s*;",
        "high",
    ),
]

RESOURCE_PATTERNS: list[tuple[str, str, str]] = [
    (
        "file_handle_leak",
        r"open\s*\([^)]+\)\s*(?!\s*(?:with|as|close))",
        "high",
    ),
    (
        "connection_not_closed",
        r"(?:requests\.|urllib\.)?(?:get|post|open)\s*\([^)]+\)\s*(?!\s*(?:with|as))",
        "medium",
    ),
    (
        "thread_without_join",
        r"Thread\s*\([^)]+\)\.start\s*\(\s*\)(?!\s*(?:join|\.daemon))",
        "medium",
    ),
    (
        "lock_without_unlock",
        r"(?:threading\.)?Lock\s*\(\s*\)\s*(?:\.acquire)?(?!\s*with)",
        "medium",
    ),
    (
        "socket_without_close",
        r"\.socket\s*\([^)]*\)\s*(?!\s*(?:with|close))",
        "medium",
    ),
]


@dataclass
class BugMatch:
    pattern_name: str
    file_path: str
    line_number: int
    matched_text: str
    rule_type: str  # 'security', 'quality', 'resource'
    severity: str


@dataclass
class BugPatternReport:
    matches: list[BugMatch] = field(default_factory=list)
    summary: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.matches)

    @property
    def critical_count(self) -> int:
        return sum(1 for m in self.matches if m.severity == "critical")

    @property
    def high_count(self) -> int:
        return sum(1 for m in self.matches if m.severity == "high")

    def to_findings(self) -> list[dict]:
        """Convert to HarnessCI Finding format."""
        from ..models import AuditFinding, FindingCategory, FindingSeverity

        findings = []
        for m in self.matches:
            sev = {
                "critical": FindingSeverity.CRITICAL,
                "high": FindingSeverity.HIGH,
                "medium": FindingSeverity.MEDIUM,
                "low": FindingSeverity.LOW,
                "info": FindingSeverity.INFO,
            }.get(m.severity, FindingSeverity.INFO)

            cat = {
                "security": FindingCategory.SECURITY,
                "quality": FindingCategory.DIFF,
                "resource": FindingCategory.DIFF,
            }.get(m.rule_type, FindingCategory.DIFF)

            findings.append(
                AuditFinding(
                    severity=sev,
                    category=cat,
                    message=f"[{m.rule_type.upper()}] {m.pattern_name}: {m.matched_text[:80]}",
                    evidence=f"{m.file_path}:{m.line_number}",
                )
            )
        return findings


def _compile_patterns(patterns: list[tuple[str, str, str]]) -> list[tuple[str, re.Pattern, str]]:
    return [(name, re.compile(pat, re.MULTILINE), sev) for name, pat, sev in patterns]


_SECURITY_COMPILED = _compile_patterns(SECURITY_PATTERNS)
_QUALITY_COMPILED = _compile_patterns(CODE_QUALITY_PATTERNS)
_RESOURCE_COMPILED = _compile_patterns(RESOURCE_PATTERNS)


def detect_bugs(
    diff_text: str,
    file_paths: list[str],
    lines_per_file: dict[str, list[str]] | None = None,
) -> BugPatternReport:
    """Detect bug patterns in diff text.

    Args:
        diff_text: Unified diff text
        file_paths: Ordered list of file paths in the diff
        lines_per_file: Optional dict of file_path -> list of (patched) lines for
            deeper pattern analysis

    Returns:
        BugPatternReport with all matches and a summary
    """
    matches: list[BugMatch] = []

    # Group patterns by rule type
    all_patterns = (
        [(name, regex, sev, "security") for name, regex, sev in _SECURITY_COMPILED]
        + [(name, regex, sev, "quality") for name, regex, sev in _QUALITY_COMPILED]
        + [(name, regex, sev, "resource") for name, regex, sev in _RESOURCE_COMPILED]
    )

    if lines_per_file:
        # Deep analysis: check actual file content
        for file_path, lines in lines_per_file.items():
            for line_no, line in enumerate(lines, start=1):
                for name, regex, sev, rule_type in all_patterns:
                    if regex.search(line):
                        matches.append(
                            BugMatch(
                                pattern_name=name,
                                file_path=file_path,
                                line_number=line_no,
                                matched_text=line.strip(),
                                rule_type=rule_type,
                                severity=sev,
                            )
                        )
    else:
        # Surface analysis: check diff hunks
        hunks = _split_diff_hunks(diff_text)
        for hunk in hunks:
            hunk_lines = hunk.split("\n")
            for line in hunk_lines:
                for name, regex, sev, rule_type in all_patterns:
                    if regex.search(line):
                        file_path = _extract_file_from_hunk(hunk) or "unknown"
                        line_no = _estimate_line_number(hunk, line)
                        matches.append(
                            BugMatch(
                                pattern_name=name,
                                file_path=file_path,
                                line_number=line_no,
                                matched_text=line.strip()[:120],
                                rule_type=rule_type,
                                severity=sev,
                            )
                        )

    # Deduplicate: same pattern + file + similar line
    seen: set[tuple[str, str, int]] = set()
    unique: list[BugMatch] = []
    for m in matches:
        key = (m.pattern_name, m.file_path, m.line_number)
        if key not in seen:
            seen.add(key)
            unique.append(m)

    # Build summary
    summary: dict[str, int] = {"total": len(unique), "security": 0, "quality": 0, "resource": 0}
    for m in unique:
        summary[m.rule_type] = summary.get(m.rule_type, 0) + 1

    return BugPatternReport(matches=unique, summary=summary)


def _split_diff_hunks(diff_text: str) -> list[str]:
    """Split unified diff into individual file hunk blocks."""
    hunks: list[str] = []
    lines = diff_text.split("\n")
    current: list[str] = []

    for line in lines:
        if line.startswith("diff --git") or line.startswith("--- ") or line.startswith("+++ "):
            if current:
                hunks.append("\n".join(current))
                current = []
        current.append(line)

    if current:
        hunks.append("\n".join(current))

    return hunks


def _extract_file_from_hunk(hunk: str) -> str | None:
    m = re.search(r"\+\+\+ b/(.+)", hunk)
    if m:
        return m.group(1)
    m = re.search(r"\+\+\+ /dev/null", hunk)
    if m:
        return "(new file)"
    return None


def _estimate_line_number(hunk: str, target_line: str) -> int:
    """Estimate the actual line number from a diff hunk header."""
    m = re.search(r"@@ -\d+(?:,\d+)? \+(\d+)", hunk)
    if m:
        base = int(m.group(1))
        # Count + lines before target
        count = 0
        for line in hunk.split("\n"):
            if line.startswith("+") and line != target_line:
                count += 1
            if line.strip() == target_line.strip():
                return base + count
        return base + count
    return 1


class BugPatternDetector:
    """Configurable bug pattern detector for HarnessCI audit pipeline."""

    def __init__(
        self,
        include_security: bool = True,
        include_quality: bool = True,
        include_resource: bool = True,
        min_severity: str = "low",
        exclude_paths: list[str] | None = None,
    ) -> None:
        self.include_security = include_security
        self.include_quality = include_quality
        self.include_resource = include_resource
        self.min_severity = min_severity
        self.exclude_paths = exclude_paths or []

    def detect(self, diff_text: str, file_paths: list[str]) -> BugPatternReport:
        """Run detection on diff text."""
        # Filter excluded paths
        if self.exclude_paths:
            filtered_paths = [
                p for p in file_paths if not any(re.search(ep, p) for ep in self.exclude_paths)
            ]
        else:
            filtered_paths = file_paths

        # Build lines per file from diff
        lines_per_file = _build_lines_from_diff(diff_text)

        return detect_bugs(
            diff_text=diff_text,
            file_paths=filtered_paths,
            lines_per_file=lines_per_file,
        )

    def detect_from_code(
        self,
        file_changes: list[dict],
    ) -> BugPatternReport:
        """Run detection on actual file content from PR changes.

        Args:
            file_changes: List of dicts with keys: path, old_lines, new_lines
        """
        lines_per_file: dict[str, list[str]] = {}
        for fc in file_changes:
            new_lines = fc.get("new_lines", [])
            if new_lines:
                lines_per_file[fc["path"]] = new_lines

        if not lines_per_file:
            return BugPatternReport()

        return detect_bugs(
            diff_text="",
            file_paths=list(lines_per_file.keys()),
            lines_per_file=lines_per_file,
        )


def _build_lines_from_diff(diff_text: str) -> dict[str, list[str]]:
    """Parse diff and extract new/added lines per file.

    Handles both unified diff format (+ prefix) and raw file content.
    """
    lines_per_file: dict[str, list[str]] = {}
    current_file: str | None = None

    for line in diff_text.split("\n"):
        # Handle +++ header
        if line.startswith("+++ "):
            m = re.search(r"\+\+\+ b?/(.+)", line)
            if m:
                current_file = m.group(1)
                if current_file and current_file not in lines_per_file:
                    lines_per_file[current_file] = []
        # Handle + lines (added content)
        elif line.startswith("+") and not line.startswith("+++"):
            content = line[1:]  # Strip the + prefix
            if current_file:
                lines_per_file[current_file].append(content)
        # Handle bare added lines (no diff header, just raw content)
        elif line.strip() and not line.startswith("-") and not line.startswith(" "):
            # Could be raw content with no diff header
            if current_file and ":" in line and not line.startswith("diff"):
                # Likely a line-number reference, skip
                pass
        # Detect file path from hunk header when available
        elif line.startswith("@@ "):
            # New file detection
            pass

    return lines_per_file


def _build_diff_from_lines(lines_per_file: dict[str, list[str]]) -> str:
    """Build a minimal diff text from file->lines mapping."""
    parts = []
    for path, lines in lines_per_file.items():
        parts.append(f"diff --git a/{path} b/{path}")
        parts.append("--- /dev/null")
        parts.append(f"+++ b/{path}")
        parts.append(f"@@ -0,0 +1,{len(lines)} @@")
        for line in lines:
            parts.append(f"+{line}")
    return "\n".join(parts)
