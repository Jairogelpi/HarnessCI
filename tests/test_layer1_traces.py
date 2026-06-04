"""Tests for synthetic Layer 1 harness trace generation."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_traces():
    script_path = ROOT / "scripts" / "generate_layer1_traces.py"
    spec = importlib.util.spec_from_file_location("generate_layer1_traces", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generate_telemetry_produces_reasonable_values():
    traces = _load_traces()
    record = {
        "dataset_id": "test__repo__pull_1",
        "files_changed": 5,
        "lines_added": 200,
        "lines_deleted": 50,
        "finding_count": 1,
        "top_findings": "Sensitive files were modified but no new tests were added.",
        "overall_agentic_risk": 30,
    }
    t = traces.generate_telemetry(record)
    # Verify all expected fields are present and have reasonable values
    assert 0 <= t["edit_attempts"] <= 15
    assert 0 <= t["retries"] <= 3
    assert 0 <= t["test_runs"] <= 20
    assert 0 <= t["failed_test_runs"] <= t["test_runs"]
    assert 0 <= t["error_count"] <= 5
    assert t["tokens_estimate"] > 0
    assert t["source"] == "synthetic_from_diff_metadata"


def test_telemetry_scales_with_size():
    traces = _load_traces()
    small = {
        "files_changed": 2,
        "lines_added": 50,
        "lines_deleted": 10,
        "finding_count": 0,
        "top_findings": "",
    }
    large = {
        "files_changed": 20,
        "lines_added": 2000,
        "lines_deleted": 500,
        "finding_count": 3,
        "top_findings": "security-sensitive auth",
    }
    t_small = traces.generate_telemetry(small)
    t_large = traces.generate_telemetry(large)
    assert t_large["edit_attempts"] > t_small["edit_attempts"]
    assert t_large["tokens_estimate"] > t_small["tokens_estimate"]
    assert t_large["retries"] >= t_small["retries"]


def test_security_files_increase_edit_attempts():
    traces = _load_traces()
    base = {
        "files_changed": 3,
        "lines_added": 100,
        "lines_deleted": 20,
        "finding_count": 1,
        "top_findings": "code modified",
    }
    security = {
        "files_changed": 3,
        "lines_added": 100,
        "lines_deleted": 20,
        "finding_count": 1,
        "top_findings": "security-sensitive billing auth",
    }
    t_base = traces.generate_telemetry(base)
    t_sec = traces.generate_telemetry(security)
    assert t_sec["edit_attempts"] >= t_base["edit_attempts"]


def test_add_traces_to_results(tmp_path: Path):
    traces = _load_traces()
    case_a = {
        "dataset_id": "a__r__1",
        "files_changed": 2,
        "lines_added": 50,
        "lines_deleted": 10,
        "finding_count": 0,
        "top_findings": "",
    }
    case_b = {
        "dataset_id": "b__r__2",
        "files_changed": 10,
        "lines_added": 500,
        "lines_deleted": 100,
        "finding_count": 2,
        "top_findings": "security",
    }
    input_path = tmp_path / "results.json"
    output_path = tmp_path / "traces.json"
    input_path.write_text(json.dumps([case_a, case_b]), encoding="utf-8")
    traces.add_traces_to_results(input_path, output_path)
    assert output_path.exists()
    enriched = json.loads(output_path.read_text(encoding="utf-8"))
    assert len(enriched) == 2
    assert "edit_attempts" in enriched[0]
    assert "tokens_estimate" in enriched[1]
    assert enriched[0]["source"] == "synthetic_from_diff_metadata"
