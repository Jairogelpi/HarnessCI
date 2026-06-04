"""Tests for AgenticPR-Bench-mini baseline comparison."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_baselines() -> ModuleType:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "compare_agenticpr_layer1_baselines.py"
    )
    spec = importlib.util.spec_from_file_location("compare_agenticpr_layer1_baselines", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_comparison_includes_harnessci_and_churn_baselines():
    baselines = _load_baselines()
    rows = [
        {
            "human_label": "ACCEPTABLE",
            "harnessci_decision": "PASS",
            "manifest_changed_files": "1",
            "manifest_additions": "10",
            "manifest_deletions": "0",
        },
        {
            "human_label": "NEEDS_REVIEW",
            "harnessci_decision": "REVIEW_REQUIRED",
            "manifest_changed_files": "8",
            "manifest_additions": "200",
            "manifest_deletions": "100",
        },
    ]

    comparison = baselines.build_comparison(rows)

    assert comparison["baselines"]["harnessci_layer1.1"]["accuracy_proxy"] == 1.0
    assert comparison["baselines"]["accept_all"]["recall_needs_review_or_block"] == 0.0
    assert comparison["baselines"]["files_or_churn"]["positive_predictions"] == 1
