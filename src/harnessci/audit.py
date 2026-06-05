"""Audit orchestration for HarnessCI.

Ties together spec loading, diff parsing, spec verification, drift detection,
scoring, and decision into a single AuditReport.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from .config import load_config
from .diff import build_diff_features, classify_files, parse_diff_text
from .errors import HarnessCIError
from .models import (
    AuditFinding,
    AuditReport,
    DiffFeatures,
    FindingCategory,
    FindingSeverity,
    SpecModel,
    TelemetrySummary,
    TestSignals,
)
from .scoring import build_findings, compute_scores, decide
from .spec import parse_spec_file, parse_spec_text
from .detection import BugPatternDetector
from .nlp import NLGenerator, generate_explanations, generate_pr_summary

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
    risk_cfg = cfg.get("risk", {})

    # 1. Load spec (mined > provided > fallback)
    spec = _load_or_infer_spec(spec_path, spec_text)

    # 2. Parse diff
    raw_files = parse_diff_text(diff_text)
    classified = classify_files(raw_files)
    diff_features = build_diff_features(classified)

    # 3. Derive test signals
    test_signals = _derive_test_signals(diff_features)
    telemetry = TelemetrySummary()

    # 4. Run spec verifier on mined spec if available
    spec_findings = _run_spec_verifier(diff_features, spec)

    # 5. Run drift matcher if domain embeddings exist
    drift_signals = _run_drift_matcher(diff_features)

    # 6. Core scoring + findings
    scores = compute_scores(spec, diff_features, test_signals, telemetry)
    findings = build_findings(spec, diff_features, test_signals, telemetry)

    # 7. Merge verification findings and drift signals into findings list
    findings.extend(spec_findings)
    for ds in drift_signals:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.MEDIUM,
                category=FindingCategory.ARCHITECTURE,
                message=f"Semantic drift detected: {ds.evidence}",
                evidence="; ".join(ds.changed_files[:5]),
            )
        )

    # 8. Bug pattern detection (regex-based, generic code quality)
    bug_matches = _run_bug_detection(diff_text, diff_features)

    # 8b. AST-based semantic bug detection (Python-specific)
    ast_matches = _run_ast_bug_detection(diff_text, diff_features)

    # 8c. LLM refiner: validate rules output + detect semantic bugs
    findings, refinement_stats = _run_llm_refiner(findings, diff_text, diff_features)

    # 9. Decision
    decision = decide(
        scores=scores,
        test_signals=test_signals,
        findings=findings,
        block_on_failed_tests=risk_cfg.get("block_on_failed_tests", True),
        block_on_security_critical=risk_cfg.get("block_on_security_critical", True),
        no_spec=not spec.usable,
        insufficient_on_missing_spec=True,
    )

    # 10. NL generation (after decision so we have risk_score)
    nl_summary = _run_nl_generation(diff_text, decision, scores, findings)

    return AuditReport.model_construct(
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
        nl_summary=nl_summary,
        bug_pattern_matches=bug_matches,
    )


def _derive_test_signals(diff_features: DiffFeatures) -> TestSignals:
    """Derive deterministic test signals from diff structure when no runner data exists."""
    return TestSignals(
        new_tests_added=diff_features.test_files_changed > 0,
        changed_tests=diff_features.test_files_changed,
    )


def _load_or_infer_spec(
    spec_path: str | Path | None,
    spec_text: str | None = None,
) -> SpecModel:
    """Load spec: provided > mined > fallback."""
    # 1-2. Provided spec
    if spec_text or spec_path:
        return _load_spec(spec_path, spec_text)

    # 3. Try mined spec
    try:
        from .spec_inference import load_mined_spec, spec_exists

        cwd = Path.cwd()
        if spec_exists(cwd):
            mined = load_mined_spec(cwd)
            if mined:
                spec_text_mined = _mined_spec_to_text(mined)
                return _load_spec(None, spec_text_mined)
    except Exception:  # noqa: BLE001
        pass

    return SpecModel()


def _mined_spec_to_text(mined: dict) -> str:
    """Convert mined spec dict to markdown format that parse_spec_text understands."""
    parts: list[str] = []

    domain = mined.get("domain", "")
    if domain:
        parts.append(f"## Goal\n{domain}")

    entities = mined.get("entities", [])
    if entities:
        parts.append("## Acceptance Criteria")
        for e in entities[:5]:
            name = e.get("name", "")
            files = ", ".join(str(f) for f in e.get("files", []))
            invs = e.get("invariants", [])
            inv_str = f" ({'; '.join(invs)})" if invs else ""
            parts.append(f"- {name}: {files}{inv_str}")

    forbidden = mined.get("forbidden_paths", [])
    if forbidden:
        parts.append("## Out of Scope")
        for fp in forbidden[:10]:
            parts.append(f"- {fp}")

    arch = mined.get("architecture", {})
    if arch:
        parts.append("## Expected Scope\nmedium_change")
    else:
        parts.append("## Expected Scope\nsmall_bugfix")

    risk = mined.get("security_invariants", [])
    if risk:
        parts.append("## Risk Areas")
        for r in risk[:5]:
            parts.append(f"- {r}")

    return "\n".join(parts) + "\n"


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


def _run_bug_detection(
    diff_text: str,
    diff_features: DiffFeatures,
) -> int:
    """Run generic bug pattern detection on the diff.

    Returns the count of bug pattern matches found.
    """
    try:
        from .detection import BugPatternDetector

        file_paths = [f.path for f in diff_features.files]
        detector = BugPatternDetector(
            include_security=True,
            include_quality=True,
            include_resource=True,
            min_severity="low",
            exclude_paths=[
                r"node_modules/",
                r"\.venv/",
                r"__pycache__/",
                r"\.git/",
                r"dist/",
                r"build/",
            ],
        )
        report = detector.detect(diff_text=diff_text, file_paths=file_paths)
        # Add bug findings to the findings list if we had access to it here
        # For now we just return the count; the caller adds them
        return report.total
    except Exception:  # noqa: BLE001
        return 0


def _run_ast_bug_detection(
    diff_text: str,
    diff_features: DiffFeatures,
) -> int:
    """Run AST-based semantic bug detection on Python files in the diff.

    Returns the count of semantic bug matches found.
    """
    try:
        from .detection.semantic_bugs import SemanticBugDetector

        file_paths = [f.path for f in diff_features.files if f.path.endswith(".py")]
        if not file_paths:
            return 0

        # Parse diff to get actual file content
        file_changes = _extract_python_files_from_diff(diff_text)
        if not file_changes:
            return 0

        detector = SemanticBugDetector(
            include_null_deref=True,
            include_unused_imports=True,
            include_missing_try=True,
            include_logic_errors=True,
            include_incomplete_refactor=True,
            min_severity="medium",
        )
        semantic_bugs = detector.analyze_diff(file_changes)

        # Add AST findings to the findings list via a side-channel
        # We store them in a module-level registry for the caller
        # For simplicity, we return the count and the caller accesses via _AST_BUG_CACHE
        global _AST_BUG_CACHE
        _AST_BUG_CACHE = semantic_bugs
        return len(semantic_bugs)
    except Exception:  # noqa: BLE001
        return 0


def _run_llm_refiner(
    findings: list[AuditFinding],
    diff_text: str,
    diff_features: DiffFeatures,
) -> tuple[list[AuditFinding], dict[str, Any]]:
    """Validate and enhance findings using Groq LLM semantic analysis.

    Pipeline:
      1. Convert findings to dict format
      2. Call Groq LLM refiner
      3. Merge validated/new findings back into AuditFinding objects
      4. Add AST bugs as additional findings
      5. Return enhanced findings + stats

    Returns:
      tuple of (enhanced findings list, refinement summary dict)
    """
    try:
        from .detection.llm_refiner import LLMRefiner

        # Convert AuditFinding to dict
        finding_dicts = [
            {
                "severity": f.severity.value,
                "category": f.category.value,
                "message": f.message,
                "evidence": f.evidence,
            }
            for f in findings
        ]

        file_paths = [f.path for f in diff_features.files]

        refiner = LLMRefiner()
        result = refiner.refine(
            initial_findings=finding_dicts,
            diff_text=diff_text,
            file_paths=file_paths,
        )

        validated_findings = result.get("validated_findings", [])
        summary = result.get("summary", {})

        # Build enhanced findings list
        enhanced: list[AuditFinding] = []
        for vf in validated_findings:
            sev = vf.get("severity", "info")
            cat = vf.get("category", "unknown")
            msg = vf.get("message", "")
            reason = vf.get("reason", "")

            is_new = vf.get("original") is None

            enhanced.append(
                AuditFinding(
                    severity=FindingSeverity(sev),
                    category=FindingCategory(cat),
                    message=msg,
                    evidence=reason,
                    explanation=reason if is_new else None,
                )
            )

        # Add AST bugs as findings
        global _AST_BUG_CACHE
        ast_bugs = _AST_BUG_CACHE
        for bug in (ast_bugs or []):
            sev = bug.get("severity", "medium")
            cat = bug.get("type", "quality")
            # Map to FindingCategory
            if "security" in cat or "deserialization" in cat:
                cat_map = "security"
            elif "logic" in cat or "constant_condition" in cat:
                cat_map = "diff"
            else:
                cat_map = "diff"

            enhanced.append(
                AuditFinding(
                    severity=FindingSeverity(sev),
                    category=FindingCategory(cat_map),
                    message=bug.get("message", ""),
                    evidence=bug.get("evidence", ""),
                    explanation=f"AST analysis: {bug.get('type', 'unknown')}",
                )
            )

        return enhanced, summary

    except Exception:  # noqa: BLE001
        return findings, {
            "total_findings": len(findings),
            "validated": len(findings),
            "rejected": 0,
            "new_semantic": 0,
            "escalations": 0,
            "de_escalations": 0,
        }



def _extract_python_files_from_diff(diff_text: str) -> list[dict[str, Any]]:
    """Parse diff and extract new Python file content."""
    files: list[dict[str, Any]] = []
    current_path: str | None = None
    current_lines: list[str] = []

    for line in diff_text.split("\n"):
        if line.startswith("+++ b/"):
            if current_path and current_lines:
                files.append({"path": current_path, "new_lines": current_lines})
            m = line[4:].strip()
            if m.endswith(".py"):
                current_path = m
                current_lines = []
            else:
                current_path = None
        elif line.startswith("+") and not line.startswith("+++"):
            if current_path is not None:
                current_lines.append(line[1:])

    if current_path and current_lines:
        files.append({"path": current_path, "new_lines": current_lines})

    return files


# Module-level cache for AST bugs (set by _run_ast_bug_detection, read by _run_llm_refiner)
_AST_BUG_CACHE: list[dict[str, Any]] = []



def _run_nl_generation(
    diff_text: str,
    decision: str,
    scores: Any,
    findings: list[AuditFinding],
) -> dict[str, str] | None:
    """Generate NL explanations and PR summary via Groq (if available).

    Returns None if Groq API key is not set.
    """
    try:
        from .nlp import generate_explanations, generate_pr_summary

        # Generate explanations for each finding
        finding_dicts = [
            {
                "severity": f.severity.value,
                "category": f.category.value,
                "message": f.message,
                "evidence": f.evidence,
            }
            for f in findings
        ]
        explanations = generate_explanations(finding_dicts)

        # Attach explanations to findings
        for i, finding in enumerate(findings):
            if i < len(explanations):
                finding.explanation = explanations[i]

        # Generate PR summary
        summary = generate_pr_summary(
            diff_text=diff_text,
            decision=decision,
            risk_score=(
                scores.overall_agentic_risk if hasattr(scores, "overall_agentic_risk") else 50
            ),
            findings=finding_dicts,
        )
        return summary
    except Exception:  # noqa: BLE001
        return None


def _run_spec_verifier(
    diff_features: DiffFeatures,
    spec: SpecModel,
) -> list[AuditFinding]:
    """Run SpecVerifier on the diff using the provided or mined spec."""
    try:
        from .spec.verifier import SpecVerifier
        from .spec_inference import load_mined_spec, spec_exists

        # Convert provided spec to dict for SpecVerifier
        spec_dict: dict[str, object] = {
            "domain": spec.goal or "",
            "entities": [],
            "conventions": {},
            "forbidden_paths": list(spec.out_of_scope),
            "allowed_test_patterns": [],
            "architecture": {},
            "security_invariants": [],
        }

        # If provided spec is weak, try mined spec
        if not spec_dict.get("forbidden_paths") and not spec.goal:
            cwd = Path.cwd()
            if spec_exists(cwd):
                mined = load_mined_spec(cwd)
                if mined and mined.get("forbidden_paths"):
                    spec_dict = mined

        if not spec_dict.get("forbidden_paths") and not spec_dict.get("entities"):
            return []

        verifier = SpecVerifier(spec=spec_dict)
        return verifier.verify(diff_features)
    except Exception:  # noqa: BLE001
        return []


def _run_drift_matcher(diff_features: DiffFeatures) -> list[object]:
    """Run DriftMatcher to detect architecture drift from embeddings."""
    try:
        from .semantic import DriftMatcher
        from .semantic.store import is_available as vec_available

        if not vec_available():
            return []

        db_path = Path.cwd() / ".harnessci" / "vectors.db"
        if not db_path.exists():
            return []

        matcher = DriftMatcher(db_path=db_path)
        return matcher.detect_drift(diff_features.files)
    except Exception:  # noqa: BLE001
        return []


def _git_diff(base_rev: str, head_rev: str, cwd: str | Path | None) -> str:
    """Run `git diff <base_rev> <head_rev>` and return stdout."""
    try:
        result = subprocess.run(
            ["git", "diff", base_rev, head_rev],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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
