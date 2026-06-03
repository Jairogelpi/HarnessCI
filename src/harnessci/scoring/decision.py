"""Decision logic and findings generation for HarnessCI.

All decisions are deterministic. LLM judge output is treated as
an additional finding only — it never replaces the deterministic decision.
"""

from __future__ import annotations

from harnessci.models import (
    AuditFinding,
    ChangeType,
    Decision,
    DiffFeatures,
    FindingCategory,
    FindingSeverity,
    ScoreBreakdown,
    SpecModel,
    TelemetrySummary,
    TestSignals,
)

# Decision band thresholds (see docs/scoring_model.md)
_BLOCK_THRESHOLD = 61
_REVIEW_THRESHOLD = 31

# Harness instability thresholds for findings
_HIGH_EDIT_ATTEMPTS = 8
_HIGH_FAIL_RATIO = 0.4
_HIGH_ERROR_COUNT = 4
_HIGH_RETRIES = 3


# ---------------------------------------------------------------------------
# build_findings
# ---------------------------------------------------------------------------


def build_findings(
    spec: SpecModel,
    diff: DiffFeatures,
    test_signals: TestSignals,
    telemetry: TelemetrySummary,
) -> list[AuditFinding]:
    """Generate deterministic findings from available audit evidence."""
    findings: list[AuditFinding] = []

    # --- Spec findings ---
    if not spec.usable:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SPEC,
                message="No usable specification found.",
                evidence="spec.usable=False; goal and acceptance criteria are both absent.",
            )
        )

    # --- Out-of-scope violations ---
    if spec.usable and spec.out_of_scope:
        file_paths = {f.path for f in diff.files}
        violations = [oos for oos in spec.out_of_scope if any(oos in p for p in file_paths)]
        if violations:
            findings.append(
                AuditFinding(
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.SPEC,
                    message=(
                        f"PR touches {len(violations)} file(s) explicitly listed as out of scope."
                    ),
                    evidence="; ".join(violations[:5]),
                )
            )

    # --- Test failure finding ---
    if test_signals.tests_failed:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.TESTS,
                message="Configured tests failed.",
                evidence="test_signals.tests_failed=True",
            )
        )

    # --- Sensitive change without tests ---
    if diff.sensitive_files_touched and not test_signals.new_tests_added:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SECURITY,
                message=("Sensitive files were modified but no new tests were added."),
                evidence="; ".join(diff.sensitive_files_touched[:5]),
            )
        )

    # --- Security-sensitive change type without tests ---
    if (
        diff.change_type in (ChangeType.SECURITY_SENSITIVE, ChangeType.DATABASE_CHANGE)
        and not test_signals.new_tests_added
    ):
        findings.append(
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SECURITY,
                message=(f"Change type '{diff.change_type}' detected with no new tests."),
                evidence=f"change_type={diff.change_type}",
            )
        )

    # --- Database migration without tests ---
    if diff.database_migration_added and not test_signals.new_tests_added:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SECURITY,
                message="Database migration added with no new tests.",
                evidence="database_migration_added=True",
            )
        )

    # --- Public API change without tests ---
    if diff.public_api_changed and not test_signals.new_tests_added:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.MEDIUM,
                category=FindingCategory.ARCHITECTURE,
                message="Public API changed but no new tests were added to verify the contract.",
                evidence="public_api_changed=True",
            )
        )

    # --- Telemetry instability ---
    if telemetry.available:
        instability_reasons: list[str] = []

        if telemetry.edit_attempts is not None and telemetry.edit_attempts >= _HIGH_EDIT_ATTEMPTS:
            instability_reasons.append(f"{telemetry.edit_attempts} edit attempts")

        if (
            telemetry.failed_test_runs is not None
            and telemetry.test_runs
            and telemetry.failed_test_runs / telemetry.test_runs >= _HIGH_FAIL_RATIO
        ):
            instability_reasons.append(
                f"{telemetry.failed_test_runs}/{telemetry.test_runs} test runs failed"
            )

        if telemetry.retries is not None and telemetry.retries >= _HIGH_RETRIES:
            instability_reasons.append(f"{telemetry.retries} retries")

        if telemetry.error_count is not None and telemetry.error_count >= _HIGH_ERROR_COUNT:
            instability_reasons.append(f"{telemetry.error_count} errors")

        if instability_reasons:
            findings.append(
                AuditFinding(
                    severity=FindingSeverity.MEDIUM,
                    category=FindingCategory.TELEMETRY,
                    message="Harness showed signs of unstable convergence.",
                    evidence="; ".join(instability_reasons),
                )
            )

    return findings


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


def decide(
    scores: ScoreBreakdown,
    test_signals: TestSignals,
    findings: list[AuditFinding],
    block_on_failed_tests: bool = True,
    block_on_security_critical: bool = True,
    no_spec: bool = False,
    insufficient_on_missing_spec: bool = True,
) -> Decision:
    """Apply deterministic decision rules in priority order.

    Priority:
    1. tests_failed + block_on_failed_tests → BLOCK
    2. any CRITICAL finding + block_on_security_critical → BLOCK
    3. no spec + insufficient_on_missing_spec → INSUFFICIENT_INFORMATION
    4. no spec → REVIEW_REQUIRED
    5. overall_agentic_risk >= 61 → BLOCK
    6. overall_agentic_risk >= 31 → REVIEW_REQUIRED
    7. PASS
    """
    # 1. Test failure gate
    if block_on_failed_tests and test_signals.tests_failed:
        return Decision.BLOCK

    # 2. Critical finding gate
    if block_on_security_critical and any(f.severity == FindingSeverity.CRITICAL for f in findings):
        return Decision.BLOCK

    # 3-4. Missing spec
    if no_spec:
        if insufficient_on_missing_spec:
            return Decision.INSUFFICIENT_INFORMATION
        return Decision.REVIEW_REQUIRED

    # 5-6. Risk band
    risk = scores.overall_agentic_risk
    if risk >= _BLOCK_THRESHOLD:
        return Decision.BLOCK
    if risk >= _REVIEW_THRESHOLD:
        return Decision.REVIEW_REQUIRED

    return Decision.PASS
