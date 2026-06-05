"""Tests for HarnessCI session autopsy telemetry narratives."""

from __future__ import annotations

import json

from harnessci.autopsy.analyzer import SessionAnalyzer
from harnessci.autopsy.collector import TraceCollector, normalize_telemetry
from harnessci.autopsy.narrator import SessionNarrator
from harnessci.models import (
    AuditReport,
    ChangeType,
    Decision,
    DiffFeatures,
    ScoreBreakdown,
    SpecModel,
    TelemetrySummary,
    TestSignals,
)


def _diff_features(total_churn: int = 20, files_changed: int = 2) -> DiffFeatures:
    return DiffFeatures(
        files_changed=files_changed,
        lines_added=total_churn,
        lines_deleted=0,
        total_churn=total_churn,
        test_files_changed=0,
        config_files_changed=0,
        dependency_changes=0,
        database_migration_added=False,
        public_api_changed=False,
        change_type=ChangeType.BUGFIX,
    )


def _report(
    diff: DiffFeatures | None = None,
    telemetry: TelemetrySummary | None = None,
) -> AuditReport:
    return AuditReport(
        decision=Decision.REVIEW_REQUIRED,
        overall_agentic_risk=60,
        scores=ScoreBreakdown(
            spec_compliance_score=80,
            diff_minimality_score=80,
            test_adequacy_score=60,
            security_risk_score=20,
            architecture_drift_score=20,
            harness_efficiency_score=40,
            overall_agentic_risk=60,
        ),
        spec=SpecModel(goal="Fix login", usable=True),
        diff=diff or _diff_features(),
        test_signals=TestSignals(),
        telemetry=telemetry or TelemetrySummary(available=True),
        findings=[],
        recommendation="Review before merging.",
    )


def test_analyzer_detects_thrashing():
    insights = SessionAnalyzer().analyze(
        trace={"edit_attempts": 11, "test_runs": 10, "failed_test_runs": 7},
        diff_features=_diff_features(),
    )

    assert [i.type for i in insights] == ["thrashing"]
    assert insights[0].severity == "critical"
    assert "vueltas" in insights[0].title


def test_analyzer_detects_context_gap_inefficiency_and_scope_creep():
    insights = SessionAnalyzer().analyze(
        trace={
            "latency_ms": 1_900_000,
            "tokens": 30_000,
            "retries": 4,
            "edit_attempts": 2,
            "test_runs": 1,
            "failed_test_runs": 0,
        },
        diff_features=_diff_features(total_churn=20, files_changed=10),
    )

    assert {i.type for i in insights} == {
        "context_gap",
        "inefficiency",
        "scope_creep_pattern",
    }


def test_narrator_generates_serializable_autopsy():
    trace = {
        "available": True,
        "latency_ms": 1_380_000,
        "tokens": 47_000,
        "edit_attempts": 11,
        "test_runs": 10,
        "failed_test_runs": 7,
    }
    report = _report(diff=_diff_features(total_churn=40))
    insights = SessionAnalyzer().analyze(trace, report.diff)

    autopsy = SessionNarrator().generate_report(insights, report, trace)

    assert autopsy["headline"].startswith("⚠️")
    assert autopsy["efficiency_score"] < 50
    assert autopsy["stats"]["duration_minutes"] == 23
    json.dumps(autopsy, ensure_ascii=False)


def test_collector_normalizes_harnessci_schema(tmp_path):
    trace_path = tmp_path / ".harnessci" / "telemetry.json"
    trace_path.parent.mkdir()
    trace_path.write_text(
        json.dumps(
            {
                "agent": {"name": "claude-code", "model": "sonnet"},
                "harness": {"name": "plan-execute-repair"},
                "execution": {
                    "tokens_in": 100,
                    "tokens_out": 50,
                    "edit_attempts": 9,
                    "test_runs": 4,
                    "failed_test_runs": 2,
                    "latency_ms": 120_000,
                },
            }
        ),
        encoding="utf-8",
    )

    telemetry = TraceCollector().collect(tmp_path)

    assert telemetry.available is True
    assert telemetry.agent_name == "claude-code"
    assert telemetry.model_name == "sonnet"
    assert telemetry.tokens == 150
    assert telemetry.edit_attempts == 9


def test_normalize_flat_explicit_telemetry_dict():
    telemetry = normalize_telemetry(
        {
            "available": True,
            "tokens": 12_000,
            "edit_attempts": 8,
            "test_runs": 2,
            "failed_test_runs": 1,
        }
    )

    assert telemetry.available is True
    assert telemetry.tokens == 12_000
    assert telemetry.edit_attempts == 8
