"""Audit orchestration for HarnessCI.

Ties together spec loading, diff parsing, scoring, and decision into a
single AuditReport. Does not call LLMs, GitHub APIs, or external services.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .config import load_config
from .diff import build_diff_features, classify_files, parse_diff_text
from .errors import HarnessCIError
from .models import AuditReport, DiffFeatures, SpecModel, TelemetrySummary, TestSignals
from .scoring import build_findings, compute_scores, decide
from .spec import parse_spec_file, parse_spec_text

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_audit(
    base_rev: str,
    head_rev: str,
    spec_path: str | Path | None = None,
    spec_text: str | None = None,
    config: dict[str, Any] | None = None,
    git_cwd: str | Path | None = None,
) -> AuditReport:
    """Run a full deterministic audit from a git revision range."""
    diff_text = _git_diff(base_rev, head_rev, git_cwd)
    return _build_audit_report(
        diff_text=diff_text,
        spec_path=spec_path,
        spec_text=spec_text,
        config=config,
        metadata={"base_rev": base_rev, "head_rev": head_rev},
    )


def run_audit_from_diff_text(
    diff_text: str,
    spec_path: str | Path | None = None,
    spec_text: str | None = None,
    config: dict[str, Any] | None = None,
) -> AuditReport:
    """Run a deterministic audit from already loaded unified diff text.

    Provide either ``spec_path`` (path to a spec file) or ``spec_text`` (raw spec
    content).  If both are given, ``spec_text`` takes precedence and is written to
    a temporary on-disk file so the existing spec-file parser is reused.

    This pure API is intended for benchmarks and offline analysis where a PR diff
    is already available and cloning the source repository would be unnecessary.
    It does not call git, GitHub, LLMs, or external services.
    """
    return _build_audit_report(
        diff_text=diff_text,
        spec_path=spec_path,
        spec_text=spec_text,
        config=config,
        metadata={
            "source": "diff_text",
            "diff_sha256": hashlib.sha256(diff_text.encode("utf-8")).hexdigest(),
            "diff_bytes": len(diff_text.encode("utf-8")),
            "spec_source": "inline" if spec_text else "file" if spec_path else "none",
        },
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _build_audit_report(
    diff_text: str,
    spec_path: str | Path | None,
    spec_text: str | None,
    config: dict[str, Any] | None,
    metadata: dict[str, str | int | float | bool | None],
) -> AuditReport:
    """Build an AuditReport from loaded diff text and optional spec/config."""
    cfg = config if config is not None else load_config(None)
    spec = _load_spec(spec_path, spec_text)

    raw_files = parse_diff_text(diff_text)
    classified = classify_files(raw_files)
    diff_features = build_diff_features(classified)

    test_signals = _derive_test_signals(diff_features)
    telemetry = TelemetrySummary()

    scores = compute_scores(spec, diff_features, test_signals, telemetry)
    risk_cfg = cfg.get("risk", {})
    findings = build_findings(spec, diff_features, test_signals, telemetry)
    decision = decide(
        scores=scores,
        test_signals=test_signals,
        findings=findings,
        block_on_failed_tests=risk_cfg.get("block_on_failed_tests", True),
        block_on_security_critical=risk_cfg.get("block_on_security_critical", True),
        no_spec=not spec.usable,
        insufficient_on_missing_spec=True,
    )

    return AuditReport(
        decision=decision,
        overall_agentic_risk=scores.overall_agentic_risk,
        scores=scores,
        spec=spec,
        diff=diff_features,
        test_signals=test_signals,
        telemetry=telemetry,
        findings=findings,
        recommendation=_recommendation(decision),
        metadata=metadata,
    )


def _derive_test_signals(diff_features: DiffFeatures) -> TestSignals:
    """Derive deterministic test signals from diff structure when no runner data exists."""
    return TestSignals(
        new_tests_added=diff_features.test_files_changed > 0,
        changed_tests=diff_features.test_files_changed,
    )


def _load_spec(spec_path: str | Path | None, spec_text: str | None = None) -> SpecModel:
    """Try to parse the spec; return an unusable SpecModel on any failure."""
    try:
        if spec_text is not None:
            return parse_spec_text(spec_text, source_path="<inline>")
        if spec_path is not None:
            return parse_spec_file(Path(spec_path))
    except Exception:  # noqa: BLE001
        return SpecModel()
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
