"""Tests for AgenticPR-Bench-mini Layer 2 manifest builder."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]


def _load_builder() -> ModuleType:
    script_path = ROOT / "scripts" / "build_agenticpr_layer2_manifest.py"
    spec = importlib.util.spec_from_file_location("build_agenticpr_layer2_manifest", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_layer2_manifest_builder_loads_pilot_tasks():
    builder = _load_builder()

    tasks = builder.load_tasks(builder.DEFAULT_TASKS_DIR)
    rows = builder.build_manifest(tasks)

    assert len(tasks) == 10
    assert len(rows) == 30
    case_ids = {row["case_id"] for row in rows}
    assert "task_001__acceptable" in case_ids
    assert "task_002__unacceptable" in case_ids
    assert all(row["spec_text"].startswith("## Goal") for row in rows)
    assert all("## Acceptance Criteria" in row["spec_text"] for row in rows)


def test_layer2_manifest_writer_outputs_jsonl(tmp_path: Path):
    builder = _load_builder()
    tasks = builder.load_tasks(builder.DEFAULT_TASKS_DIR)
    rows = builder.build_manifest(tasks)
    output = tmp_path / "manifest.jsonl"

    builder.write_manifest(output, rows)

    written = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    assert len(written) == 30
    assert written[0]["primary_label"] in {"ACCEPTABLE", "NEEDS_REVIEW", "UNACCEPTABLE"}
    assert set(written[0]["gold"]) == builder.REQUIRED_GOLD_KEYS
