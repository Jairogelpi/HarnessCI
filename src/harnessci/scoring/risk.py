"""Deterministic scoring formula for HarnessCI.

Computes ScoreBreakdown from spec, diff, test signals, and telemetry.
Weights are named constants — any change must also update docs/scoring_model.md.
"""

from __future__ import annotations

from harnessci.models import (
    ChangeType,
    DiffFeatures,
    ScoreBreakdown,
    SpecModel,
    TelemetrySummary,
    TestSignals,
)

# ---------------------------------------------------------------------------
# Formula weights — keep aligned with docs/scoring_model.md
# ---------------------------------------------------------------------------
_W_SPEC = 0.25
_W_DIFF = 0.20
_W_TEST = 0.20
_W_SEC = 0.20
_W_ARCH = 0.10
_W_HARNESS = 0.05

_NEUTRAL_HARNESS = 50  # used when telemetry is unavailable

# ---------------------------------------------------------------------------
# Sensitive change-type signals
# ---------------------------------------------------------------------------
_SENSITIVE_TYPES = {
    ChangeType.SECURITY_SENSITIVE,
    ChangeType.DATABASE_CHANGE,
    ChangeType.DEPENDENCY_UPDATE,
}

_SENSITIVE_KEYWORDS = (
    "auth",
    "session",
    "token",
    "password",
    "credential",
    "secret",
    "permission",
    "role",
    "access",
    "billing",
    "payment",
    "invoice",
    "subscription",
    "charge",
    "crypto",
    "encrypt",
    "decrypt",
    "hash",
    "sign",
    "jwt",
    "oauth",
    "migration",
    "database",
    "db",
)


def _clamp(value: float) -> int:
    return max(0, min(100, round(value)))


# ---------------------------------------------------------------------------
# Sub-score heuristics
# ---------------------------------------------------------------------------


def _spec_compliance_score(spec: SpecModel) -> int:
    """Estimate spec compliance from available static evidence."""
    if not spec.usable:
        return 0
    score = 50  # baseline: spec exists but no runtime alignment info
    if spec.acceptance_criteria:
        score += 20
    if spec.risk_areas:
        score += 10
    if spec.out_of_scope:
        score += 10
    if spec.goal.strip():
        score += 10
    return _clamp(score)


def _diff_minimality_score(spec: SpecModel, diff: DiffFeatures) -> int:
    """Estimate diff minimality: fewer files + smaller churn → higher score."""
    score = 100

    # Penalise by number of non-test files changed (expected small for bugfixes)
    non_test_files = max(0, diff.files_changed - diff.test_files_changed)
    if non_test_files > 10:
        score -= 50
    elif non_test_files > 5:
        score -= 30
    elif non_test_files > 3:
        score -= 15

    # Penalise large total churn
    if diff.total_churn > 1000:
        score -= 30
    elif diff.total_churn > 500:
        score -= 20
    elif diff.total_churn > 200:
        score -= 10

    # Penalise files listed as out-of-scope being touched
    if spec.usable and spec.out_of_scope:
        file_paths = {f.path for f in diff.files}
        for oos in spec.out_of_scope:
            if any(oos in p for p in file_paths):
                score -= 15
                break

    return _clamp(score)


def _test_adequacy_score(diff: DiffFeatures, signals: TestSignals) -> int:
    """Estimate test adequacy from test signals."""
    score = 50  # neutral baseline

    if signals.tests_failed:
        return 0
    if signals.tests_passed is True:
        score += 20
    if signals.new_tests_added:
        score += 20
    if signals.changed_tests > 0:
        score += 5
    if diff.test_files_changed > 0 and diff.files_changed > 0:
        ratio = diff.test_files_changed / diff.files_changed
        if ratio >= 0.5:
            score += 10
        elif ratio < 0.2:
            score -= 10

    # Coverage delta bonus/penalty
    if signals.coverage_delta is not None:
        if signals.coverage_delta > 0:
            score += 5
        elif signals.coverage_delta < -2:
            score -= 15

    return _clamp(score)


def _security_risk_score(diff: DiffFeatures) -> int:
    """Estimate security risk from sensitive file touches."""
    score = 0

    if diff.sensitive_files_touched:
        # Each sensitive file increases risk
        score += min(60, len(diff.sensitive_files_touched) * 15)

    if diff.change_type in _SENSITIVE_TYPES:
        score += 20

    if diff.database_migration_added:
        score += 15

    if diff.dependency_changes > 0:
        score += min(20, diff.dependency_changes * 5)

    if diff.public_api_changed:
        score += 10

    return _clamp(score)


def _architecture_drift_score(spec: SpecModel, diff: DiffFeatures) -> int:
    """Estimate architecture drift from unexpected scope expansion."""
    score = 0

    if diff.public_api_changed:
        score += 20

    # Large file count suggests broad scope creep
    if diff.files_changed > 10:
        score += 30
    elif diff.files_changed > 6:
        score += 15

    # Out-of-scope violations
    if spec.usable and spec.out_of_scope:
        file_paths = {f.path for f in diff.files}
        violations = sum(1 for oos in spec.out_of_scope if any(oos in p for p in file_paths))
        if violations:
            score += min(40, violations * 15)

    return _clamp(score)


def _harness_efficiency_score(tel: TelemetrySummary) -> int:
    """Estimate harness efficiency from telemetry. Returns 50 when unavailable."""
    if not tel.available:
        return _NEUTRAL_HARNESS

    score = 100

    # Too many edit attempts indicate instability
    if tel.edit_attempts is not None:
        if tel.edit_attempts > 10:
            score -= 30
        elif tel.edit_attempts > 5:
            score -= 15

    # Failed test runs indicate convergence issues
    if tel.failed_test_runs is not None and tel.test_runs:
        fail_ratio = tel.failed_test_runs / tel.test_runs
        if fail_ratio > 0.5:
            score -= 25
        elif fail_ratio > 0.2:
            score -= 10

    # Retries and errors add instability
    if tel.retries is not None:
        score -= min(20, tel.retries * 5)

    if tel.error_count is not None:
        score -= min(20, tel.error_count * 5)

    return _clamp(score)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_scores(
    spec: SpecModel,
    diff: DiffFeatures,
    test_signals: TestSignals,
    telemetry: TelemetrySummary,
) -> ScoreBreakdown:
    """Compute all scoring dimensions and the weighted overall risk."""
    sc = _spec_compliance_score(spec)
    dm = _diff_minimality_score(spec, diff)
    ta = _test_adequacy_score(diff, test_signals)
    sr = _security_risk_score(diff)
    ad = _architecture_drift_score(spec, diff)
    he = _harness_efficiency_score(telemetry)

    hi = 100 - he  # harness_instability

    overall = (
        _W_SPEC * (100 - sc)
        + _W_DIFF * (100 - dm)
        + _W_TEST * (100 - ta)
        + _W_SEC * sr
        + _W_ARCH * ad
        + _W_HARNESS * hi
    )

    return ScoreBreakdown(
        spec_compliance_score=sc,
        diff_minimality_score=dm,
        test_adequacy_score=ta,
        security_risk_score=sr,
        architecture_drift_score=ad,
        harness_efficiency_score=he,
        overall_agentic_risk=_clamp(overall),
    )
