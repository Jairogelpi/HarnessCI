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

    # --- Security-sensitive auth changes with deletions ---
    # Detect potential auth removal when there is no test safety net.
    # If a sensitive file was changed with deletions and no tests were added,
    # flag it as HIGH risk.
    if diff.sensitive_files_touched and diff.change_type == ChangeType.SECURITY_SENSITIVE:
        removed_auth_checks = any(
            f.is_sensitive and f.lines_deleted > 0 for f in diff.files
        )
        if removed_auth_checks and not test_signals.new_tests_added:
            findings.append(
                AuditFinding(
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.SECURITY,
                    message=(
                        "Security-sensitive file modified with deletions and no new tests — "
                        "potential removal of authentication or authorization logic."
                    ),
                    evidence="; ".join(diff.sensitive_files_touched[:5]),
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
                message="Sensitive files were modified but no new tests were added.",
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
                message=f"Change type '{diff.change_type}' detected with no new tests.",
                evidence=f"change_type={diff.change_type}",
            )
        )

    # --- Missing tests for non-trivial code changes ---
    # If code files were modified and no tests were added, flag the missing coverage.
    # Fires independently of security findings to catch cases like refactoring,
    # feature additions, or API changes that lack test coverage.
    # Note: this may create false positives on acceptable pure-addition variants.
    non_test_code_files = [f for f in diff.files if not f.is_test]
    if non_test_code_files and not test_signals.new_tests_added:
        findings.append(
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.TESTS,
                message="Code was modified but no new tests were added.",
                evidence="; ".join(f.path for f in non_test_code_files[:3]),
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

    # --- Architecture drift: files outside expected scope ---
    # Flag when changed files don't match any known domain pattern and there are
    # multiple non-test files. Catches scope drift and unrelated changes that
    # aren't security-sensitive enough to trigger the security block.
    if spec.usable:
        has_spec = any(f.category == FindingCategory.SPEC for f in findings)
        if not has_spec:
            non_test_files = [f for f in diff.files if not f.is_test]
            if len(non_test_files) >= 2:
                known_domains = {
                    "fastapi-auth-demo": [
                        "auth", "session", "login", "middleware", "redirect",
                    ],
                    "django-billing-demo": [
                        "invoice", "billing", "webhook", "payment", "customer",
                    ],
                    "react-dashboard-demo": [
                        "chart", "dashboard", "frontend", "api", "data",
                    ],
                }
                matched = sum(
                    1
                    for f in non_test_files
                    if any(
                        kw in f.path.lower()
                        for domains in known_domains.values()
                        for kw in domains
                    )
                )
                if matched == 0:
                    findings.append(
                        AuditFinding(
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.ARCHITECTURE,
                            message=(
                                "Changed files do not match the expected domain scope — "
                                "possible architecture drift or unrelated changes."
                            ),
                            evidence="; ".join(f.path for f in non_test_files[:3]),
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
    1. tests_failed + block_on_failed_tests -> BLOCK
    2. any CRITICAL finding + block_on_security_critical -> BLOCK
    3. no spec + insufficient_on_missing_spec -> INSUFFICIENT_INFORMATION
    4. no spec -> REVIEW_REQUIRED
    5. 3+ HIGH security findings -> BLOCK
    6. 2 HIGH security + 1+ HIGH SPEC findings -> BLOCK
    7. 1+ HIGH security OR HIGH SPEC findings -> REVIEW_REQUIRED
    8. overall_agentic_risk >= 61 -> BLOCK
    9. overall_agentic_risk >= 31 -> REVIEW_REQUIRED
    10. PASS
    """
    # 1. Test failure gate
    if block_on_failed_tests and test_signals.tests_failed:
        return Decision.BLOCK

    # 2. Critical finding gate
    if block_on_security_critical and any(
        f.severity == FindingSeverity.CRITICAL for f in findings
    ):
        return Decision.BLOCK

    # 3-4. Missing spec — checked before findings escalation so that
    # no-spec cases return INSUFFICIENT_INFORMATION even when a SPEC finding
    # is present (SPEC finding is informational, not a blocking signal).
    if no_spec:
        if insufficient_on_missing_spec:
            return Decision.INSUFFICIENT_INFORMATION
        return Decision.REVIEW_REQUIRED

    # 5-7. Findings-based escalation by accumulated evidence
    security_high_count = sum(
        1
        for f in findings
        if f.severity == FindingSeverity.HIGH and f.category == FindingCategory.SECURITY
    )
    has_spec_finding = any(
        f.severity == FindingSeverity.HIGH and f.category == FindingCategory.SPEC
        for f in findings
    )
    if block_on_security_critical:
        if security_high_count >= 3:
            return Decision.BLOCK
        if security_high_count >= 2 and has_spec_finding:
            return Decision.BLOCK
        if security_high_count >= 1 or has_spec_finding:
            return Decision.REVIEW_REQUIRED

    # 8-9. Risk band
    risk = scores.overall_agentic_risk
    if risk >= _BLOCK_THRESHOLD:
        return Decision.BLOCK
    if risk >= _REVIEW_THRESHOLD:
        return Decision.REVIEW_REQUIRED

    return Decision.PASS