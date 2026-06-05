"""Tests for deterministic scoring and decision rules — PR4."""

from harnessci.models import (
    AuditFinding,
    ChangeType,
    Decision,
    DiffFeatures,
    DiffFileChange,
    FindingCategory,
    FindingSeverity,
    ScoreBreakdown,
    SpecModel,
    TelemetrySummary,
    TestSignals,
)
from harnessci.scoring import build_findings, compute_scores, decide

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EMPTY_SPEC = SpecModel()  # usable=False


def _spec(**kw) -> SpecModel:
    defaults: dict = {"goal": "Fix login redirect", "acceptance_criteria": ["Redirect works"]}
    defaults.update(kw)
    return SpecModel(**defaults)


def _diff(
    files: list[DiffFileChange] | None = None,
    sensitive: list[str] | None = None,
    change_type: ChangeType = ChangeType.BUGFIX,
    files_changed: int = 2,
    lines_added: int = 20,
    lines_deleted: int = 5,
    test_files_changed: int = 1,
    public_api_changed: bool = False,
    database_migration_added: bool = False,
    dependency_changes: int = 0,
    config_files_changed: int = 0,
) -> DiffFeatures:
    return DiffFeatures(
        files_changed=files_changed,
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        total_churn=lines_added + lines_deleted,
        test_files_changed=test_files_changed,
        config_files_changed=config_files_changed,
        dependency_changes=dependency_changes,
        database_migration_added=database_migration_added,
        public_api_changed=public_api_changed,
        sensitive_files_touched=sensitive or [],
        change_type=change_type,
        files=files or [],
    )


def _telemetry(**kw) -> TelemetrySummary:
    return TelemetrySummary(available=True, **kw)


def _signals(**kw) -> TestSignals:
    return TestSignals(**kw)


# ---------------------------------------------------------------------------
# compute_scores — formula tests
# ---------------------------------------------------------------------------


class TestComputeScores:
    def test_returns_score_breakdown(self):
        scores = compute_scores(_spec(), _diff(), TestSignals(), TelemetrySummary())
        assert isinstance(scores, ScoreBreakdown)

    def test_all_scores_in_range(self):
        scores = compute_scores(_spec(), _diff(), TestSignals(), TelemetrySummary())
        for field in ScoreBreakdown.model_fields:
            val = getattr(scores, field)
            assert 0 <= val <= 100, f"{field} out of range: {val}"

    def test_overall_risk_is_int(self):
        scores = compute_scores(_spec(), _diff(), TestSignals(), TelemetrySummary())
        assert isinstance(scores.overall_agentic_risk, int)

    def test_neutral_telemetry_uses_50(self):
        """When telemetry is unavailable, harness_efficiency_score should be 50."""
        scores = compute_scores(_spec(), _diff(), TestSignals(), TelemetrySummary(available=False))
        assert scores.harness_efficiency_score == 50

    def test_available_telemetry_uses_efficiency(self):
        """High-quality telemetry (few errors, few retries) → high efficiency."""
        tel = _telemetry(
            tool_calls=10,
            edit_attempts=2,
            retries=0,
            test_runs=2,
            failed_test_runs=0,
            error_count=0,
        )
        scores = compute_scores(_spec(), _diff(), TestSignals(), tel)
        assert scores.harness_efficiency_score >= 50

    def test_formula_weights(self):
        """Manual spot-check: known inputs → known overall_risk."""
        scores = compute_scores(
            _spec(),
            _diff(),
            TestSignals(tests_passed=True, new_tests_added=True),
            TelemetrySummary(available=False),
        )
        sp = scores.spec_compliance_score
        dm = scores.diff_minimality_score
        ta = scores.test_adequacy_score
        sr = scores.security_risk_score
        ad = scores.architecture_drift_score
        he = scores.harness_efficiency_score
        expected = round(
            0.25 * (100 - sp)
            + 0.20 * (100 - dm)
            + 0.20 * (100 - ta)
            + 0.20 * sr
            + 0.10 * ad
            + 0.05 * (100 - he)
        )
        expected = max(0, min(100, expected))
        assert scores.overall_agentic_risk == expected

    def test_zero_risk_when_all_perfect(self):
        """Simulate a perfect audit: high compliance/minimality/test, no security risk."""
        scores = compute_scores(
            _spec(acceptance_criteria=["A", "B", "C"]),
            _diff(sensitive=[], files_changed=1, lines_added=5, test_files_changed=1),
            TestSignals(tests_passed=True, new_tests_added=True),
            TelemetrySummary(available=False),
        )
        assert scores.overall_agentic_risk <= 30

    def test_high_risk_when_all_bad(self):
        """Simulate a problematic audit: no spec, sensitive files, no tests."""
        scores = compute_scores(
            _EMPTY_SPEC,
            _diff(
                sensitive=["auth/session.py", "billing/payment.py"],
                files_changed=15,
                lines_added=500,
                test_files_changed=0,
                change_type=ChangeType.SECURITY_SENSITIVE,
            ),
            TestSignals(tests_passed=False, new_tests_added=False),
            TelemetrySummary(available=False),
        )
        assert scores.overall_agentic_risk >= 61

    def test_clamping_overall_risk(self):
        """overall_risk must stay in 0-100 even with extreme penalties."""
        scores = compute_scores(
            _EMPTY_SPEC,
            _diff(
                sensitive=["auth.py"] * 10,
                files_changed=50,
                lines_added=2000,
                test_files_changed=0,
            ),
            TestSignals(tests_passed=False),
            TelemetrySummary(available=False),
        )
        assert 0 <= scores.overall_agentic_risk <= 100

    # Boundary tests: 30/31 and 60/61
    def test_band_boundary_pass_30(self):
        """Scores that produce overall_risk=30 land in PASS."""
        scores = compute_scores(
            _spec(acceptance_criteria=["A"]),
            _diff(sensitive=[], files_changed=2, test_files_changed=1),
            TestSignals(tests_passed=True, new_tests_added=True),
            TelemetrySummary(available=False),
        )
        if scores.overall_agentic_risk <= 30:
            assert decide(scores, TestSignals(tests_passed=True), [], False, False) == Decision.PASS

    def test_band_boundary_block_61(self):
        """overall_risk=61 escalates to BLOCK."""
        sb = ScoreBreakdown(
            spec_compliance_score=39,
            diff_minimality_score=70,
            test_adequacy_score=70,
            security_risk_score=40,
            architecture_drift_score=20,
            harness_efficiency_score=50,
            overall_agentic_risk=61,
        )
        result = decide(sb, TestSignals(), [], False, False)
        assert result == Decision.BLOCK

    def test_band_boundary_review_required_31(self):
        """overall_risk=31 → REVIEW_REQUIRED."""
        sb = ScoreBreakdown(
            spec_compliance_score=70,
            diff_minimality_score=70,
            test_adequacy_score=70,
            security_risk_score=20,
            architecture_drift_score=10,
            harness_efficiency_score=50,
            overall_agentic_risk=31,
        )
        result = decide(sb, TestSignals(), [], False, False)
        assert result == Decision.REVIEW_REQUIRED


# ---------------------------------------------------------------------------
# decide — decision logic
# ---------------------------------------------------------------------------


class TestDecide:
    def test_pass_when_low_risk(self):
        sb = ScoreBreakdown(
            spec_compliance_score=90,
            diff_minimality_score=85,
            test_adequacy_score=80,
            security_risk_score=5,
            architecture_drift_score=5,
            harness_efficiency_score=80,
            overall_agentic_risk=15,
        )
        assert decide(sb, TestSignals(tests_passed=True), [], False, False) == Decision.PASS

    def test_block_when_high_risk(self):
        sb = ScoreBreakdown(
            spec_compliance_score=10,
            diff_minimality_score=10,
            test_adequacy_score=10,
            security_risk_score=90,
            architecture_drift_score=80,
            harness_efficiency_score=10,
            overall_agentic_risk=80,
        )
        assert decide(sb, TestSignals(tests_passed=False), [], False, False) == Decision.BLOCK

    def test_block_on_failed_tests_overrides_low_risk(self):
        sb = ScoreBreakdown(
            spec_compliance_score=90,
            diff_minimality_score=90,
            test_adequacy_score=90,
            security_risk_score=5,
            architecture_drift_score=5,
            harness_efficiency_score=90,
            overall_agentic_risk=5,
        )
        assert (
            decide(
                sb,
                TestSignals(tests_failed=True),
                [],
                block_on_failed_tests=True,
                block_on_security_critical=False,
            )
            == Decision.BLOCK
        )

    def test_failed_tests_no_block_if_policy_off(self):
        sb = ScoreBreakdown(
            spec_compliance_score=90,
            diff_minimality_score=90,
            test_adequacy_score=90,
            security_risk_score=5,
            architecture_drift_score=5,
            harness_efficiency_score=90,
            overall_agentic_risk=5,
        )
        result = decide(
            sb,
            TestSignals(tests_failed=True),
            [],
            block_on_failed_tests=False,
            block_on_security_critical=False,
        )
        assert result == Decision.PASS

    def test_block_on_critical_finding(self):
        sb = ScoreBreakdown(
            spec_compliance_score=90,
            diff_minimality_score=90,
            test_adequacy_score=90,
            security_risk_score=5,
            architecture_drift_score=5,
            harness_efficiency_score=90,
            overall_agentic_risk=10,
        )
        findings = [
            AuditFinding(
                severity=FindingSeverity.CRITICAL,
                category=FindingCategory.SECURITY,
                message="Critical auth bypass",
            )
        ]
        assert (
            decide(
                sb,
                TestSignals(),
                findings,
                block_on_failed_tests=False,
                block_on_security_critical=True,
            )
            == Decision.BLOCK
        )

    def test_high_test_finding_triggers_review(self):
        sb = ScoreBreakdown(
            spec_compliance_score=90,
            diff_minimality_score=90,
            test_adequacy_score=40,
            security_risk_score=5,
            architecture_drift_score=5,
            harness_efficiency_score=90,
            overall_agentic_risk=12,
        )
        findings = [
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.TESTS,
                message="Code changed without new tests",
            )
        ]
        assert (
            decide(
                sb,
                TestSignals(new_tests_added=False),
                findings,
                block_on_failed_tests=False,
                block_on_security_critical=False,
            )
            == Decision.REVIEW_REQUIRED
        )

    def test_block_on_high_security_and_spec_finding(self):
        sb = ScoreBreakdown(
            spec_compliance_score=20,
            diff_minimality_score=80,
            test_adequacy_score=40,
            security_risk_score=70,
            architecture_drift_score=10,
            harness_efficiency_score=90,
            overall_agentic_risk=25,
        )
        findings = [
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SECURITY,
                message="Sensitive file modified without tests",
            ),
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SPEC,
                message="Out of scope path touched",
            ),
        ]
        assert (
            decide(
                sb,
                TestSignals(new_tests_added=False),
                findings,
                block_on_failed_tests=False,
                block_on_security_critical=True,
            )
            == Decision.BLOCK
        )

    def test_insufficient_information_when_no_spec(self):
        sb = ScoreBreakdown(
            spec_compliance_score=0,
            diff_minimality_score=50,
            test_adequacy_score=50,
            security_risk_score=10,
            architecture_drift_score=10,
            harness_efficiency_score=50,
            overall_agentic_risk=35,
        )
        result = decide(
            sb,
            TestSignals(),
            [
                AuditFinding(
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.SPEC,
                    message="No spec available",
                    evidence="spec.usable=False",
                )
            ],
            block_on_failed_tests=False,
            block_on_security_critical=False,
            no_spec=True,
        )
        assert result == Decision.INSUFFICIENT_INFORMATION

    def test_review_required_when_no_spec_and_policy_not_strict(self):
        sb = ScoreBreakdown(
            spec_compliance_score=0,
            diff_minimality_score=50,
            test_adequacy_score=50,
            security_risk_score=10,
            architecture_drift_score=10,
            harness_efficiency_score=50,
            overall_agentic_risk=35,
        )
        result = decide(
            sb,
            TestSignals(),
            [],
            block_on_failed_tests=False,
            block_on_security_critical=False,
            no_spec=True,
            insufficient_on_missing_spec=False,
        )
        assert result == Decision.REVIEW_REQUIRED


# ---------------------------------------------------------------------------
# build_findings — findings generation
# ---------------------------------------------------------------------------


class TestBuildFindings:
    def test_no_spec_produces_finding(self):
        findings = build_findings(_EMPTY_SPEC, _diff(), TestSignals(), TelemetrySummary())
        categories = [f.category for f in findings]
        assert FindingCategory.SPEC in categories

    def test_sensitive_no_tests_produces_finding(self):
        findings = build_findings(
            _spec(),
            _diff(
                sensitive=["auth/session.py"],
                change_type=ChangeType.SECURITY_SENSITIVE,
                test_files_changed=0,
            ),
            TestSignals(new_tests_added=False),
            TelemetrySummary(),
        )
        cats = [f.category for f in findings]
        assert FindingCategory.SECURITY in cats or FindingCategory.TESTS in cats

    def test_out_of_scope_violation_finding(self):
        spec = _spec(out_of_scope=["billing/payment.py"])
        diff = _diff(
            files=[
                DiffFileChange(
                    path="billing/payment.py",
                    status="M",
                    lines_added=10,
                    lines_deleted=2,
                )
            ]
        )
        findings = build_findings(spec, diff, TestSignals(), TelemetrySummary())
        messages = [f.message for f in findings]
        assert any("scope" in m.lower() or "out" in m.lower() for m in messages)

    def test_tests_failed_produces_finding(self):
        findings = build_findings(
            _spec(),
            _diff(),
            TestSignals(tests_failed=True),
            TelemetrySummary(),
        )
        cats = [f.category for f in findings]
        assert FindingCategory.TESTS in cats

    def test_no_findings_for_clean_pr(self):
        findings = build_findings(
            _spec(acceptance_criteria=["A", "B"]),
            _diff(sensitive=[], test_files_changed=2, files_changed=2),
            TestSignals(tests_passed=True, new_tests_added=True),
            TelemetrySummary(),
        )
        # should produce 0 HIGH or CRITICAL findings
        severe = [
            f for f in findings if f.severity in (FindingSeverity.CRITICAL, FindingSeverity.HIGH)
        ]
        assert len(severe) == 0

    def test_unstable_telemetry_finding(self):
        tel = _telemetry(
            test_runs=10,
            failed_test_runs=8,
            edit_attempts=15,
            retries=5,
            error_count=6,
        )
        findings = build_findings(_spec(), _diff(), TestSignals(), tel)
        cats = [f.category for f in findings]
        assert FindingCategory.TELEMETRY in cats

    def test_public_api_change_finding(self):
        findings = build_findings(
            _spec(),
            _diff(public_api_changed=True, test_files_changed=0),
            TestSignals(new_tests_added=False),
            TelemetrySummary(),
        )
        msgs = " ".join(f.message.lower() for f in findings)
        assert "api" in msgs or "public" in msgs

    def test_database_migration_finding(self):
        findings = build_findings(
            _spec(),
            _diff(database_migration_added=True, test_files_changed=0),
            TestSignals(new_tests_added=False),
            TelemetrySummary(),
        )
        msgs = " ".join(f.message.lower() for f in findings)
        assert "migration" in msgs or "database" in msgs
