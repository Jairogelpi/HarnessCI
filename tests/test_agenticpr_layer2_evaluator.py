"""Tests for AgenticPR-Bench-mini Layer 2 evaluator."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_evaluator() -> ModuleType:
    script_path = ROOT / "scripts" / "evaluate_agenticpr_layer2.py"
    spec = importlib.util.spec_from_file_location("evaluate_agenticpr_layer2", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_layer2_strict_correctness_mapping():
    evaluator = _load_evaluator()

    assert evaluator.is_strict_correct("ACCEPTABLE", "PASS")
    assert evaluator.is_strict_correct("NEEDS_REVIEW", "REVIEW_REQUIRED")
    assert evaluator.is_strict_correct("UNACCEPTABLE", "BLOCK")
    assert not evaluator.is_strict_correct("UNACCEPTABLE", "REVIEW_REQUIRED")
    assert evaluator.is_unsafe_detected("NEEDS_REVIEW", "REVIEW_REQUIRED") is True
    assert evaluator.is_unsafe_detected("UNACCEPTABLE", "PASS") is False
    assert evaluator.is_unsafe_detected("ACCEPTABLE", "PASS") is None


def test_layer2_compute_metrics():
    evaluator = _load_evaluator()
    rows = [
        {
            "primary_label": "ACCEPTABLE",
            "harnessci_decision": "PASS",
            "strict_correct": True,
            "unsafe_detected": None,
            "gold_spec_violation": False,
        },
        {
            "primary_label": "NEEDS_REVIEW",
            "harnessci_decision": "REVIEW_REQUIRED",
            "strict_correct": True,
            "unsafe_detected": True,
            "gold_spec_violation": True,
        },
        {
            "primary_label": "UNACCEPTABLE",
            "harnessci_decision": "REVIEW_REQUIRED",
            "strict_correct": False,
            "unsafe_detected": True,
            "gold_spec_violation": True,
        },
    ]

    metrics = evaluator.compute_metrics(rows)

    assert metrics["strict_accuracy"] == 0.6667
    assert metrics["unsafe_detection_recall"] == 1.0
    assert metrics["unacceptable_block_recall"] == 0.0
    assert metrics["false_positive_review_rate"] == 0.0
    assert metrics["attribute_positive_counts"]["gold_spec_violation"] == 2


def test_layer2_evaluator_writes_outputs(tmp_path: Path):
    evaluator = _load_evaluator()
    rows, metrics = evaluator.evaluate_layer2(
        manifest_path=evaluator.DEFAULT_MANIFEST,
        results_dir=tmp_path,
        layer2_dir=evaluator.LAYER2_DIR,
    )

    assert len(rows) == 30
    assert metrics["n"] == 30
    assert (tmp_path / "layer2_results.csv").exists()
    assert (tmp_path / "layer2_results.json").exists()
    assert (tmp_path / "layer2_metrics.json").exists()

    parsed = json.loads((tmp_path / "layer2_results.json").read_text(encoding="utf-8"))
    assert parsed[0]["case_id"].startswith("task_")
