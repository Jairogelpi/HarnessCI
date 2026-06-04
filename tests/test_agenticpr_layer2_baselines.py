"""Tests for AgenticPR-Bench-mini Layer 2 baseline comparison."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_baselines() -> ModuleType:
    script_path = ROOT / "scripts" / "compare_agenticpr_layer2_baselines.py"
    spec = importlib.util.spec_from_file_location("compare_agenticpr_layer2_baselines", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_patch_features_detect_scope_and_tests():
    baselines = _load_baselines()
    manifest = baselines.read_manifest(baselines.DEFAULT_MANIFEST)
    unacceptable = next(row for row in manifest if row["case_id"] == "task_001__unacceptable")

    features = baselines.patch_features(unacceptable)

    assert "app/password_reset.py" in features["outside_scope_files"]
    assert features["has_sensitive_file"] is True
    assert features["has_test_file"] is False


def test_layer2_baseline_comparison_includes_scope_or_static():
    baselines = _load_baselines()
    manifest = baselines.read_manifest(baselines.DEFAULT_MANIFEST)
    rows = baselines.build_case_rows(manifest)

    comparison = baselines.build_comparison(rows)

    assert set(comparison["baselines"]) == {
        "accept_all",
        "files_only_gt_2",
        "churn_only_gt_20",
        "scope_only",
        "static_sensitive_no_tests",
        "scope_or_static",
    }
    assert comparison["baselines"]["scope_or_static"]["n"] == 30
    assert comparison["baselines"]["scope_or_static"]["recall_unsafe"] is not None
