import json

import pytest
from pydantic import ValidationError

from harnessci.models import (
    AuditFinding,
    AuditReport,
    ChangeType,
    Decision,
    DiffFeatures,
    DiffFileChange,
    ExpectedScope,
    FindingCategory,
    FindingSeverity,
    ScoreBreakdown,
    SpecModel,
)

SCORES = {
    "spec_compliance_score": 90,
    "diff_minimality_score": 80,
    "test_adequacy_score": 70,
    "security_risk_score": 30,
    "architecture_drift_score": 20,
    "harness_efficiency_score": 50,
    "overall_agentic_risk": 29,
}


def test_audit_report_serializes_public_contract() -> None:
    report = AuditReport(
        decision=Decision.PASS,
        overall_agentic_risk=29,
        scores=ScoreBreakdown(**SCORES),
        spec=SpecModel(goal="Fix redirect", expected_scope=ExpectedScope.SMALL_BUGFIX),
        diff=DiffFeatures(
            files_changed=1,
            lines_added=4,
            lines_deleted=1,
            total_churn=5,
            test_files_changed=1,
            config_files_changed=0,
            dependency_changes=0,
            database_migration_added=False,
            public_api_changed=False,
            sensitive_files_touched=["auth/session.py"],
            change_type=ChangeType.BUGFIX,
            files=[DiffFileChange(path="auth/session.py", status="modified", lines_added=4)],
        ),
        findings=[
            AuditFinding(
                severity=FindingSeverity.INFO,
                category=FindingCategory.SPEC,
                message="Spec is usable",
            )
        ],
        recommendation="Safe for normal review.",
    )

    dumped = report.model_dump(mode="json")
    assert dumped["decision"] == "PASS"
    assert dumped["overall_agentic_risk"] == 29
    assert dumped["spec"]["expected_scope"] == "small_bugfix"
    assert dumped["diff"]["change_type"] == "bugfix"
    assert json.loads(report.model_dump_json())["findings"][0]["severity"] == "info"


def test_models_reject_invalid_enums_and_bounds() -> None:
    with pytest.raises(ValidationError):
        AuditFinding(severity="urgent", category=FindingCategory.SECURITY, message="bad")
    with pytest.raises(ValidationError):
        ScoreBreakdown(**{**SCORES, "spec_compliance_score": 101})
    with pytest.raises(ValidationError):
        DiffFileChange(path="x.py", status="modified", lines_added=-1)


def test_unusable_spec_is_explicit_not_optimistic() -> None:
    spec = SpecModel(goal="", acceptance_criteria=[])
    assert spec.usable is False
    assert spec.expected_scope == ExpectedScope.UNKNOWN
