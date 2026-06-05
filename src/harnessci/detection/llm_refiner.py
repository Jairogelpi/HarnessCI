"""LLM-based finding refiner for HarnessCI.

Takes initial findings from rules + bug patterns, validates them semantically,
and adds deep semantic analysis that regex/AST cannot provide.

Architecture:
  rules + bug_patterns → initial findings
  → LLM refiner → enhanced findings with semantic depth
  → final score

Groq is used for lightweight semantic validation (not full LLM review).
"""

from __future__ import annotations

import json
import os
from typing import Any

try:
    import requests as _requests

    _GROQ_AVAILABLE = True
except Exception:  # noqa: BLE001
    _GROQ_AVAILABLE = False
    _requests = None

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "llama-3.1-8b-instant"


def _groq_complete(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.1,
    max_tokens: int = 1024,
) -> str | None:
    """Call Groq API. Returns None on failure."""
    if not _GROQ_AVAILABLE or _requests is None:
        return None
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        resp = _requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=45,
        )
        if resp.status_code == 200:
            return resp.json()["choices"][0]["message"]["content"].strip()
        return None
    except Exception:  # noqa: BLE001
        return None


_SYSTEM_REFINE = (
    "You are a senior code reviewer analyzing a pull request diff. "
    "You have initial findings from static analysis. Your job is to:\n"
    "1. VALIDATE each finding — confirm or reject it based on actual code context\n"
    "2. REFINE severity — escalate if worse than it looks, de-escalate if false positive\n"
    "3. ADD semantic findings — detect bugs that static analysis missed:\n"
    "   - Null/none dereferences that will cause runtime errors\n"
    "   - Missing error handling that will cause silent failures\n"
    "   - Race conditions in async code\n"
    "   - Resource leaks (unclosed files, connections, handles)\n"
    "   - Type mismatches in function calls\n"
    "   - Unused imports or variables\n"
    "   - Logic errors (off-by-one, wrong conditions, inverted logic)\n"
    "   - Security issues in authentication, authorization, input validation\n"
    "4. CLASSIFY each finding by type and severity.\n\n"
    "Output JSON only, no markdown, no explanation outside JSON."
)

_JSON_OUTPUT_SCHEMA = """
Output format (JSON):
{
  "validated_findings": [
    {
      "original": "<original finding message or null if new>",
      "validated": true/false,
      "message": "<refined or new finding message>",
      "severity": "critical/high/medium/low/info",
      "category": "security/quality/correctness/resource/architecture",
      "reason": "<why this was validated/rejected/new>"
    }
  ],
  "summary": {
    "total_findings": 0,
    "validated": 0,
    "rejected": 0,
    "new_semantic": 0,
    "escalations": 0,
    "de_escalations": 0
  }
}
"""


def refine_findings(
    initial_findings: list[dict[str, Any]],
    diff_text: str,
    file_paths: list[str],
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Refine findings using Groq LLM semantic analysis.

    Args:
        initial_findings: List of finding dicts from rules/bug_patterns
        diff_text: Unified diff text
        file_paths: List of changed file paths
        model: Groq model

    Returns:
        Dict with validated_findings and summary statistics
    """
    if not _GROQ_AVAILABLE or not os.environ.get("GROQ_API_KEY"):
        return {
            "validated_findings": [
                {
                    "original": f.get("message"),
                    "validated": True,
                    "message": f.get("message"),
                    "severity": f.get("severity", "info"),
                    "category": f.get("category", "unknown"),
                    "reason": "Groq unavailable — original finding kept",
                }
                for f in initial_findings
            ],
            "summary": {
                "total_findings": len(initial_findings),
                "validated": len(initial_findings),
                "rejected": 0,
                "new_semantic": 0,
                "escalations": 0,
                "de_escalations": 0,
            },
        }

    # Truncate diff to save tokens (first 6KB per file, max 20 files)
    _ = _truncate_diff(diff_text, max_bytes=6000, max_files=20)

    # Format initial findings
    finding_text = ""
    for i, f in enumerate(initial_findings, 1):
        sev = f.get("severity", "?")
        cat = f.get("category", "?")
        msg = f.get("message", "")
        ev = f.get("evidence", "")
        finding_text += (
            f"{i}. [{sev.upper()}] [{cat.upper()}] {msg}"
            + (f" | Evidence: {ev}" if ev else "")
            + "\n"
        )

    user_prompt = (
        "INITIAL FINDINGS FROM STATIC ANALYSIS:\n"
        f"{finding_text}\n\n"
        "DIFF (truncated):\n{truncated_diff}\n\n"
        "CHANGED FILES: {', '.join(file_paths[:20])}\n\n"
        f"Respond ONLY with valid JSON in this exact schema:\n{_JSON_OUTPUT_SCHEMA}"
    )

    messages = [
        {"role": "system", "content": _SYSTEM_REFINE},
        {"role": "user", "content": user_prompt},
    ]

    response = _groq_complete(messages, model=model, max_tokens=1024, temperature=0.1)

    if not response:
        return _fallback_refine(initial_findings)

    return _parse_refinement_response(response, initial_findings)


def _truncate_diff(diff_text: str, max_bytes: int = 6000, max_files: int = 20) -> str:
    """Truncate diff to reduce token count while keeping context."""
    lines = diff_text.split("\n")
    result: list[str] = []
    current_file = None
    file_count = 0
    bytes_used = 0

    for line in lines:
        if line.startswith("diff --git"):
            file_count += 1
            if file_count > max_files:
                break
            current_file = line
            result.append(line)
            bytes_used += len(line.encode("utf-8"))
        elif line.startswith("--- ") or line.startswith("+++ "):
            result.append(line)
            bytes_used += len(line.encode("utf-8"))
        elif line.startswith("@@ "):
            result.append(line)
            bytes_used += len(line.encode("utf-8"))
        elif line.startswith("+") or line.startswith("-"):
            if bytes_used < max_bytes * file_count:
                result.append(line)
                bytes_used += len(line.encode("utf-8"))
        else:
            result.append(line)
            bytes_used += len(line.encode("utf-8"))

        if bytes_used > max_bytes * 2:
            result.append(f"... (diff truncated, {file_count} files shown)")
            break

    return "\n".join(result)


def _parse_refinement_response(
    response: str,
    initial_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    """Parse LLM JSON response into structured findings."""
    try:
        # Try to extract JSON from response
        json_str = _extract_json(response)
        data = json.loads(json_str)

        validated = data.get("validated_findings", [])
        summary = data.get("summary", {})

        return {
            "validated_findings": validated,
            "summary": summary,
        }
    except Exception:  # noqa: BLE001
        return _fallback_refine(initial_findings)


def _extract_json(text: str) -> str:
    """Extract JSON from LLM response that may have markdown wrapping."""
    text = text.strip()

    # Remove markdown code blocks
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:] if lines[0] == "```" else lines)
        if text.endswith("```"):
            text = text[:-3]

    # Try to find JSON object
    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        return text[start:end]

    # Try array
    start = text.find("[")
    end = text.rfind("]") + 1
    if start >= 0 and end > start:
        return text[start:end]

    return text


def _fallback_refine(initial_findings: list[dict[str, Any]]) -> dict[str, Any]:
    """Fallback when LLM fails — keep original findings."""
    return {
        "validated_findings": [
            {
                "original": f.get("message"),
                "validated": True,
                "message": f.get("message"),
                "severity": f.get("severity", "info"),
                "category": f.get("category", "unknown"),
                "reason": "LLM unavailable — original finding kept",
            }
            for f in initial_findings
        ],
        "summary": {
            "total_findings": len(initial_findings),
            "validated": len(initial_findings),
            "rejected": 0,
            "new_semantic": 0,
            "escalations": 0,
            "de_escalations": 0,
        },
    }


class LLMRefiner:
    """Configurable LLM-based finding refiner."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        enabled: bool = True,
    ) -> None:
        self.model = model
        self.enabled = enabled and _GROQ_AVAILABLE and bool(os.environ.get("GROQ_API_KEY"))

    def refine(
        self,
        initial_findings: list[dict[str, Any]],
        diff_text: str,
        file_paths: list[str],
    ) -> dict[str, Any]:
        """Refine findings. Returns dict with validated_findings and summary."""
        if not self.enabled:
            return _fallback_refine(initial_findings)
        return refine_findings(
            initial_findings=initial_findings,
            diff_text=diff_text,
            file_paths=file_paths,
            model=self.model,
        )

    def refine_to_harnessci_findings(
        self,
        initial_findings: list[dict[str, Any]],
        diff_text: str,
        file_paths: list[str],
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """Refine findings and return as HarnessCI finding dicts + stats."""
        result = self.refine(initial_findings, diff_text, file_paths)
        validated = result.get("validated_findings", [])

        harnessci_findings = []
        for vf in validated:
            harnessci_findings.append(
                {
                    "severity": vf.get("severity", "info"),
                    "category": vf.get("category", "unknown"),
                    "message": vf.get("message", ""),
                    "evidence": vf.get("reason", ""),
                    "validated": vf.get("validated", True),
                    "is_new": vf.get("original") is None,
                }
            )

        return harnessci_findings, result.get("summary", {})