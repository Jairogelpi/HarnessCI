"""Tests for AgenticPR-Bench-mini layer-1 evaluator."""

from __future__ import annotations

import csv
import importlib.util
import json
from pathlib import Path
from types import ModuleType

SAMPLE_DIFF = """diff --git a/app.py b/app.py
index e69de29..9daeafb 100644
--- a/app.py
+++ b/app.py
@@ -0,0 +1,2 @@
+def login():
+    return True
"""


def _load_evaluator() -> ModuleType:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "evaluate_agenticpr_layer1.py"
    spec = importlib.util.spec_from_file_location("evaluate_agenticpr_layer1", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_compute_metrics_proxy_confusion_matrix():
    evaluator = _load_evaluator()
    rows = [
        {
            "agent": "A",
            "human_label": "ACCEPTABLE",
            "harnessci_decision": "PASS",
            "overall_agentic_risk": 10,
        },
        {
            "agent": "A",
            "human_label": "ACCEPTABLE",
            "harnessci_decision": "REVIEW_REQUIRED",
            "overall_agentic_risk": 30,
        },
        {
            "agent": "B",
            "human_label": "NEEDS_REVIEW",
            "harnessci_decision": "BLOCK",
            "overall_agentic_risk": 90,
        },
        {
            "agent": "B",
            "human_label": "NEEDS_REVIEW",
            "harnessci_decision": "PASS",
            "overall_agentic_risk": 20,
        },
    ]

    metrics = evaluator.compute_metrics(rows)

    assert metrics["n"] == 4
    assert metrics["accuracy_proxy"] == 0.5
    assert metrics["precision_needs_review_or_block"] == 0.5
    assert metrics["recall_needs_review_or_block"] == 0.5
    assert metrics["confusion_matrix_needs_review_or_block"] == {
        "tp": 1,
        "fp": 1,
        "tn": 1,
        "fn": 1,
    }
    assert metrics["mean_risk_by_label"] == {"ACCEPTABLE": 20.0, "NEEDS_REVIEW": 55.0}
    assert metrics["agent_breakdown"]["A"]["n"] == 2


def test_evaluate_layer1_writes_results_and_metrics(tmp_path: Path):
    evaluator = _load_evaluator()
    diff_dir = tmp_path / "diffs"
    diff_dir.mkdir()
    diff_path = diff_dir / "sample.diff"
    diff_path.write_text(SAMPLE_DIFF, encoding="utf-8")

    manifest = tmp_path / "manifest.jsonl"
    manifest.write_text(
        json.dumps(
            {
                "dataset_id": "sample__repo__pull_1",
                "agent": "Copilot",
                "owner": "sample",
                "repo": "repo",
                "number": 1,
                "html_url": "https://github.com/sample/repo/pull/1",
                "human_label": "ACCEPTABLE",
                "changed_files": 1,
                "additions": 2,
                "deletions": 0,
                "diff_path": "diffs/sample.diff",
                "diff_sha256": "test-sha",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    results_dir = tmp_path / "results"

    rows, metrics = evaluator.evaluate_layer1(
        manifest_path=manifest,
        results_dir=results_dir,
        repo_root=tmp_path,
    )

    assert len(rows) == 1
    assert metrics["n"] == 1
    assert (results_dir / "layer1_results.csv").exists()
    assert (results_dir / "layer1_results.json").exists()
    assert (results_dir / "layer1_metrics.json").exists()

    with (results_dir / "layer1_results.csv").open(encoding="utf-8", newline="") as fh:
        csv_rows = list(csv.DictReader(fh))
    assert csv_rows[0]["dataset_id"] == "sample__repo__pull_1"
    assert csv_rows[0]["harnessci_decision"] == "INSUFFICIENT_INFORMATION"

    parsed_json = json.loads((results_dir / "layer1_results.json").read_text(encoding="utf-8"))
    assert "body" not in parsed_json[0]
