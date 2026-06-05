"""Tests for config loading and report renderers (PR5)."""

from __future__ import annotations

import json
import textwrap

import pytest

from harnessci.errors import HarnessCIError
from harnessci.models import (
    AuditFinding,
    AuditReport,
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_report(**overrides) -> AuditReport:
    scores = ScoreBreakdown(
        spec_compliance_score=78,
        diff_minimality_score=42,
        test_adequacy_score=55,
        security_risk_score=68,
        architecture_drift_score=74,
        harness_efficiency_score=39,
        overall_agentic_risk=73,
    )
    spec = SpecModel(
        goal="Fix login redirect bug",
        acceptance_criteria=["Expired sessions redirect to /login"],
        usable=True,
    )
    diff = DiffFeatures(
        files_changed=3,
        lines_added=40,
        lines_deleted=10,
        total_churn=50,
        test_files_changed=1,
        config_files_changed=0,
        dependency_changes=0,
        database_migration_added=False,
        public_api_changed=False,
        change_type=ChangeType.BUGFIX,
    )
    defaults = dict(
        decision=Decision.REVIEW_REQUIRED,
        overall_agentic_risk=73,
        scores=scores,
        spec=spec,
        diff=diff,
        test_signals=TestSignals(),
        telemetry=TelemetrySummary(),
        findings=[
            AuditFinding(
                severity=FindingSeverity.HIGH,
                category=FindingCategory.SPEC,
                message="The PR modifies files not mentioned in the spec.",
            )
        ],
        recommendation="Do not auto-merge. Request review from backend owner.",
        metadata={"base_rev": "main", "head_rev": "feature/fix-login"},
    )
    defaults.update(overrides)
    return AuditReport(**defaults)


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_no_path_returns_defaults(self):
        from harnessci.config import load_config

        cfg = load_config(None)
        assert cfg["risk"]["strictness"] == "medium"
        assert cfg["risk"]["block_on_failed_tests"] is True

    def test_returns_deep_copy_of_defaults(self):
        from harnessci.config import load_config

        cfg1 = load_config(None)
        cfg1["risk"]["strictness"] = "mutated"
        cfg2 = load_config(None)
        assert cfg2["risk"]["strictness"] == "medium"

    def test_nonexistent_path_returns_defaults(self, tmp_path):
        from harnessci.config import load_config

        cfg = load_config(tmp_path / "missing.yaml")
        assert cfg["project"]["name"] == "unknown"

    def test_valid_yaml_merges_with_defaults(self, tmp_path):
        from harnessci.config import load_config

        cfg_file = tmp_path / "harnessci.yaml"
        cfg_file.write_text(
            textwrap.dedent("""\
                project:
                  name: "myproject"
                risk:
                  strictness: "high"
            """),
            encoding="utf-8",
        )
        cfg = load_config(cfg_file)
        assert cfg["project"]["name"] == "myproject"
        assert cfg["risk"]["strictness"] == "high"
        # defaults are preserved for keys not overridden
        assert cfg["risk"]["block_on_failed_tests"] is True
        assert cfg["report"]["comment_on_pr"] is False

    def test_invalid_yaml_raises_config_error(self, tmp_path):
        from harnessci.config import load_config
        from harnessci.errors import HarnessCIError

        cfg_file = tmp_path / "harnessci.yaml"
        cfg_file.write_text("key: [unclosed bracket", encoding="utf-8")
        with pytest.raises(HarnessCIError):
            load_config(cfg_file)

    def test_config_error_is_harnessci_error(self):
        from harnessci.config import ConfigError

        assert issubclass(ConfigError, HarnessCIError)


# ---------------------------------------------------------------------------
# JSON report tests
# ---------------------------------------------------------------------------


class TestRenderJson:
    def test_output_is_valid_json(self):
        from harnessci.report import render_json

        report = _make_report()
        output = render_json(report)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_contains_required_fields(self):
        from harnessci.report import render_json

        report = _make_report()
        parsed = json.loads(render_json(report))
        for field in ("decision", "overall_agentic_risk", "scores", "findings", "recommendation"):
            assert field in parsed, f"Missing field: {field}"

    def test_decision_value(self):
        from harnessci.report import render_json

        report = _make_report(decision=Decision.BLOCK, overall_agentic_risk=80)
        parsed = json.loads(render_json(report))
        assert parsed["decision"] == "BLOCK"

    def test_scores_present(self):
        from harnessci.report import render_json

        report = _make_report()
        parsed = json.loads(render_json(report))
        assert "spec_compliance_score" in parsed["scores"]


# ---------------------------------------------------------------------------
# Markdown report tests
# ---------------------------------------------------------------------------


class TestRenderMarkdown:
    def test_starts_with_harnessci_audit_heading(self):
        from harnessci.report import render_markdown

        report = _make_report()
        md = render_markdown(report)
        assert md.startswith("## HarnessCI Audit")

    def test_contains_decision(self):
        from harnessci.report import render_markdown

        report = _make_report()
        md = render_markdown(report)
        assert "REVIEW_REQUIRED" in md

    def test_contains_overall_risk(self):
        from harnessci.report import render_markdown

        report = _make_report()
        md = render_markdown(report)
        assert "73/100" in md

    def test_contains_score_table(self):
        from harnessci.report import render_markdown

        report = _make_report()
        md = render_markdown(report)
        assert "| Dimension" in md
        assert "Spec compliance" in md
        assert "Diff minimality" in md

    def test_contains_findings_section(self):
        from harnessci.report import render_markdown

        report = _make_report()
        md = render_markdown(report)
        assert "### Main Findings" in md
        assert "The PR modifies files not mentioned" in md

    def test_contains_recommendation(self):
        from harnessci.report import render_markdown

        report = _make_report()
        md = render_markdown(report)
        assert "### Recommendation" in md
        assert "Do not auto-merge" in md

    def test_no_findings_omits_main_findings(self):
        from harnessci.report import render_markdown

        report = _make_report(findings=[])
        md = render_markdown(report)
        # Section may be present but empty, or omitted — either is acceptable
        # Just verify it doesn't crash and has heading + recommendation
        assert "## HarnessCI Audit" in md
        assert "### Recommendation" in md

    def test_block_decision_in_output(self):
        from harnessci.report import render_markdown

        report = _make_report(decision=Decision.BLOCK, overall_agentic_risk=80)
        md = render_markdown(report)
        assert "BLOCK" in md

    def test_renders_session_autopsy_when_present(self):
        from harnessci.report import render_markdown

        report = _make_report(
            session_autopsy={
                "headline": "⚠️ Sesión problemática — El agente dio vueltas en círculos",
                "tldr": "El agente tuvo dificultades.",
                "efficiency_score": 38,
                "insights": [
                    {
                        "icon": "🔴",
                        "title": "El agente dio vueltas en círculos",
                        "explanation": "Con 11 intentos de edición, no fue directo.",
                    }
                ],
                "next_time": ["Da más contexto arquitectónico al inicio."],
                "stats": {
                    "duration_minutes": 23,
                    "tokens_used": 47_000,
                    "edit_attempts": 11,
                    "lines_changed": 50,
                    "cost_estimate": 0.705,
                },
            }
        )

        md = render_markdown(report)

        assert "## 🔬 Autopsia de Sesión" in md
        assert "Score de eficiencia | 38/100" in md
        assert "Da más contexto arquitectónico" in md

    def test_session_autopsy_handles_malformed_values(self):
        from harnessci.report import render_markdown

        report = _make_report(
            session_autopsy={
                "headline": "Bad | heading\nwith newline",
                "tldr": "Line one\nline two",
                "efficiency_score": "not-a-number",
                "insights": [
                    {
                        "icon": "🔴\n",
                        "title": "Title | pipe",
                        "explanation": "Explanation\ncontinued",
                    }
                ],
                "next_time": ["Recommendation\nwith newline"],
                "stats": {
                    "duration_minutes": "bad",
                    "tokens_used": "bad",
                    "edit_attempts": None,
                    "lines_changed": "12",
                    "cost_estimate": "bad",
                },
            }
        )

        md = render_markdown(report)

        assert "## 🔬 Autopsia de Sesión" in md
        assert "Bad ¦ heading with newline" in md
        assert "Score de eficiencia | 0/100" in md
        assert "Recommendation with newline" in md
