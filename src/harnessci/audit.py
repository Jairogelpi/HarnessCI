"""Audit orchestration for HarnessCI.

Ties together spec loading, diff parsing, scoring, and decision into a
single AuditReport. Does not call LLMs, GitHub APIs, or external services.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .config import load_config
from .diff import build_diff_features, classify_files, parse_diff_text
from .errors import HarnessCIError
from .models import AuditReport, SpecModel, TelemetrySummary, TestSignals
from .scoring import build_findings, compute_scores, decide
from .spec import parse_spec_file

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_audit(
    base_rev: str,
    head_rev: str,
    spec_path: str | Path | None = None,
    config: dict[str, Any] | None = None,
    git_cwd: str | Path | None = None,
) -> AuditReport:
    """Run a full deterministic audit and return an AuditReport.

    Steps:
    1. Load config.
    2. Load spec (use empty SpecModel if missing or unreadable).
    3. Obtain git diff via subprocess.
    4. Parse diff → classify → build DiffFeatures.
    5. Build empty TestSignals and TelemetrySummary (not in PR5 scope).
    6. Compute ScoreBreakdown.
    7. Build findings.
    8. Apply decision rules.
    9. Return AuditReport.
    """
    cfg = config if config is not None else load_config(None)

    # --- Spec ---
    spec = _load_spec(spec_path)

    # --- Git diff ---
    diff_text = _git_diff(base_rev, head_rev, git_cwd)

    # --- Diff parsing ---
    raw_files = parse_diff_text(diff_text)
    classified = classify_files(raw_files)
    diff_features = build_diff_features(classified)

    # --- Signals (stubs for PR5) ---
    test_signals = TestSignals()
    telemetry = TelemetrySummary()

    # --- Scoring ---
    scores = compute_scores(spec, diff_features, test_signals, telemetry)

    # --- Findings ---
    risk_cfg = cfg.get("risk", {})
    findings = build_findings(spec, diff_features, test_signals, telemetry)

    # --- Decision ---
    decision = decide(
        scores=scores,
        test_signals=test_signals,
        findings=findings,
        block_on_failed_tests=risk_cfg.get("block_on_failed_tests", True),
        block_on_security_critical=risk_cfg.get("block_on_security_critical", True),
        no_spec=not spec.usable,
        insufficient_on_missing_spec=True,
    )

    # --- Recommendation ---
    recommendation = _recommendation(decision)

    return AuditReport(
        decision=decision,
        overall_agentic_risk=scores.overall_agentic_risk,
        scores=scores,
        spec=spec,
        diff=diff_features,
        test_signals=test_signals,
        telemetry=telemetry,
        findings=findings,
        recommendation=recommendation,
        metadata={"base_rev": base_rev, "head_rev": head_rev},
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _load_spec(spec_path: str | Path | None) -> SpecModel:
    """Try to parse the spec file; return an unusable SpecModel on any failure."""
    if spec_path is None:
        return SpecModel()
    try:
        return parse_spec_file(Path(spec_path))
    except Exception:  # noqa: BLE001
        return SpecModel()


def _git_diff(base_rev: str, head_rev: str, cwd: str | Path | None) -> str:
    """Run `git diff <base_rev> <head_rev>` and return stdout."""
    try:
        result = subprocess.run(
            ["git", "diff", base_rev, head_rev],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as exc:
        raise HarnessCIError(f"Failed to run git: {exc}") from exc

    if result.returncode != 0:
        raise HarnessCIError(f"git diff failed (exit {result.returncode}): {result.stderr.strip()}")
    return result.stdout


def _recommendation(decision: str) -> str:  # noqa: ARG001
    """Generate a brief recommendation string from the decision."""
    from .models import Decision  # local import avoids circular at module level

    if decision == Decision.BLOCK:
        return (
            "Do not merge. This PR requires immediate attention: "
            "review all findings before proceeding."
        )
    if decision == Decision.REVIEW_REQUIRED:
        return "Do not auto-merge. Request human review from a relevant code owner before merging."
    if decision == Decision.INSUFFICIENT_INFORMATION:
        return (
            "Cannot make a reliable decision without a specification. "
            "Add a spec file or issue description and re-run the audit."
        )
    return "This PR appears safe to merge based on available evidence."
