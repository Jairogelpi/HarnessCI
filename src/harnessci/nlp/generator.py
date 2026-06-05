"""NL generation: explanations and PR summaries via Groq LLM.

Provides natural language output for findings and PRs.
Only used when GROQ_API_KEY is available (graceful no-op otherwise).
"""

from __future__ import annotations

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

_SYSTEM_EXPLANATION = (
    "You are a senior code reviewer. For each finding, produce a clear "
    "explanation in 1-2 sentences: what was detected, why it matters, "
    "and a concrete fix suggestion. Format: [SEV] CAT: Explain | Impact | Fix. "
    "Be concise. Plain text only, no markdown."
)

_SYSTEM_SUMMARY = (
    "You are a senior software engineer summarizing pull requests. "
    "Generate: one-line summary (imperative, max 15 words), key risks "
    "(1-3 bullets), test coverage (covered/partial/missing), security note. "
    "Format:\nSUMMARY: <one line>\nRISKS: <bullets>\nTESTS: <status>\nSECURITY: <note or 'None'>"
    "Plain text only."
)


def _groq_complete(
    messages: list[dict[str, str]],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.3,
    max_tokens: int = 512,
) -> str | None:
    """Call Groq API with messages. Returns None on failure."""
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
            timeout=30,
        )
        if resp.status_code == 200:
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        return None
    except Exception:  # noqa: BLE001
        return None


def generate_explanations(
    findings: list[dict[str, Any]],
    model: str = DEFAULT_MODEL,
) -> list[str]:
    """Generate natural language explanations for findings via Groq.

    Falls back to message field if Groq unavailable.
    """
    if not findings:
        return []

    # Fallback: use message as-is
    fallbacks = [str(f.get("message", "See finding details.")) for f in findings]

    if not _GROQ_AVAILABLE or not os.environ.get("GROQ_API_KEY"):
        return fallbacks

    finding_texts = []
    for i, f in enumerate(findings, 1):
        sev = f.get("severity", "?")
        cat = f.get("category", "?")
        msg = f.get("message", "")
        ev = f.get("evidence", "")
        entry = f"{i}. [{sev.upper()}] {cat.upper()}: {msg}"
        if ev:
            entry += f" | Evidence: {ev}"
        finding_texts.append(entry)

    messages = [
        {"role": "system", "content": _SYSTEM_EXPLANATION},
        {
            "role": "user",
            "content": f"Explain these {len(findings)} findings:\n\n" + "\n".join(finding_texts),
        },
    ]

    response = _groq_complete(messages, model=model)
    if response:
        lines = [ln.strip() for ln in response.split("\n") if ln.strip()]
        if len(lines) >= len(findings):
            return lines[: len(findings)]
        return lines + fallbacks[len(lines) :]

    return fallbacks


def generate_pr_summary(
    diff_text: str,
    decision: str,
    risk_score: int,
    findings: list[dict[str, Any]],
    model: str = DEFAULT_MODEL,
) -> dict[str, str]:
    """Generate a changelog-style PR summary via Groq.

    Returns dict with keys: summary, risks, tests, security.
    Falls back to simple text if Groq unavailable.
    """
    truncated = diff_text[:3072] if diff_text else ""

    finding_summary = f"{len(findings)} finding(s): "
    finding_summary += ", ".join(f.get("message", "?")[:60] for f in findings[:5])
    if len(findings) > 5:
        finding_summary += f" (+{len(findings) - 5} more)"

    user_prompt = (
        f"DIFF (first 3KB):\n{truncated}\n\n"
        f"DECISION: {decision}\nRISK SCORE: {risk_score}/100\n"
        f"FINDINGS: {finding_summary}\n\nGenerate the PR summary."
    )

    if not _GROQ_AVAILABLE or not os.environ.get("GROQ_API_KEY"):
        return _simple_fallback(decision, risk_score, findings)

    messages = [
        {"role": "system", "content": _SYSTEM_SUMMARY},
        {"role": "user", "content": user_prompt},
    ]

    response = _groq_complete(messages, model=model, max_tokens=384)
    return _parse_summary(response, decision, risk_score, findings)


def _simple_fallback(
    decision: str,
    risk_score: int,
    findings: list[dict[str, Any]],
) -> dict[str, str]:
    """Fallback summary when Groq is unavailable."""
    if decision == "BLOCK":
        summary = "This PR requires immediate review before merging."
    elif decision == "REVIEW_REQUIRED":
        summary = "This PR should be reviewed before merging."
    else:
        summary = "This PR appears safe to merge."

    severity_counts: dict[str, int] = {}
    for f in findings:
        sev = f.get("severity", "unknown")
        severity_counts[sev] = severity_counts.get(sev, 0) + 1

    risks = [
        f"{sev}: {count} finding(s)"
        for sev, count in sorted(severity_counts.items(), reverse=True)
        if sev in ("critical", "high", "medium")
    ]

    test_coverage = "covered" if any(f.get("category") == "tests" for f in findings) else "missing"

    security_note = (
        "Security concerns detected — review required."
        if any(f.get("category") == "security" for f in findings)
        else "None"
    )

    return {
        "summary": summary,
        "risks": "\n- ".join(risks) if risks else "No significant risks.",
        "tests": test_coverage,
        "security": security_note,
    }


def _parse_summary(
    response: str | None,
    decision: str,
    risk_score: int,
    findings: list[dict[str, Any]],
) -> dict[str, str]:
    """Parse Groq response into structured summary."""
    if not response:
        return _simple_fallback(decision, risk_score, findings)

    result = {
        "summary": "Summary not available.",
        "risks": "No risks identified.",
        "tests": "coverage unknown",
        "security": "None",
    }

    for line in response.split("\n"):
        line = line.strip()
        if line.startswith("SUMMARY:"):
            result["summary"] = line[8:].strip()
        elif line.startswith("RISKS:"):
            result["risks"] = line[6:].strip()
        elif line.startswith("TESTS:"):
            result["tests"] = line[6:].strip().lower()
        elif line.startswith("SECURITY:"):
            result["security"] = line[9:].strip()

    return result


class NLGenerator:
    """Configurable NL generator for findings and PR summaries."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        enabled: bool = True,
    ) -> None:
        self.model = model
        self.enabled = enabled and _GROQ_AVAILABLE and bool(os.environ.get("GROQ_API_KEY"))

    def explain_findings(self, findings: list[dict[str, Any]]) -> list[str]:
        """Generate explanations for findings."""
        if not self.enabled:
            return [str(f.get("message", "See finding details.")) for f in findings]
        return generate_explanations(findings, model=self.model)

    def summarize_pr(
        self,
        diff_text: str,
        decision: str,
        risk_score: int,
        findings: list[dict[str, Any]],
    ) -> dict[str, str]:
        """Generate a PR summary."""
        if not self.enabled:
            return _simple_fallback(decision, risk_score, findings)
        return generate_pr_summary(
            diff_text=diff_text,
            decision=decision,
            risk_score=risk_score,
            findings=findings,
            model=self.model,
        )
