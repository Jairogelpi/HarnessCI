"""Build AgenticPR-Bench-mini Layer 2 manifest from curated task YAML files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LAYER2_DIR = ROOT / "datasets" / "agenticpr-bench-mini" / "layer2"
DEFAULT_TASKS_DIR = LAYER2_DIR / "tasks"
DEFAULT_OUTPUT = LAYER2_DIR / "manifest.jsonl"

REQUIRED_GOLD_KEYS = {
    "spec_violation",
    "unrelated_changes",
    "missing_tests",
    "security_sensitive",
    "overengineering",
    "architecture_drift",
}
VALID_PRIMARY_LABELS = {"ACCEPTABLE", "NEEDS_REVIEW", "UNACCEPTABLE"}


def load_task_file(path: Path) -> list[dict[str, Any]]:
    """Load one task YAML file, accepting either one object or a list of objects."""
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if isinstance(loaded, list):
        tasks = loaded
    elif isinstance(loaded, dict):
        tasks = [loaded]
    else:
        raise ValueError(f"Task file must contain a task object or list: {path}")
    for task in tasks:
        if not isinstance(task, dict):
            raise ValueError(f"Task entries must be objects: {path}")
    return tasks


def load_tasks(tasks_dir: Path) -> list[dict[str, Any]]:
    """Load all task YAML files in stable order."""
    if not tasks_dir.exists():
        raise FileNotFoundError(f"Layer 2 tasks directory not found: {tasks_dir}")
    tasks: list[dict[str, Any]] = []
    for path in sorted(tasks_dir.glob("*.yaml")):
        tasks.extend(load_task_file(path))
    if not tasks:
        raise ValueError(f"No Layer 2 task YAML files found in: {tasks_dir}")
    return tasks


def spec_to_text(spec: dict[str, Any], expected_scope: str) -> str:
    """Convert Layer 2 task spec object to HarnessCI parser-supported text."""
    parts = ["## Goal", str(spec.get("goal", "")).strip()]
    parts.extend(section("Acceptance Criteria", spec.get("acceptance_criteria", [])))
    parts.extend(section("Out of Scope", spec.get("out_of_scope", [])))
    parts.extend(section("Risk Areas", spec.get("risk_areas", [])))
    parts.extend(["", "## Expected Scope", expected_scope])
    return "\n".join(part for part in parts if part is not None).strip() + "\n"


def section(title: str, values: list[str]) -> list[str]:
    """Render a bullet-list spec section."""
    lines = ["", f"## {title}"]
    lines.extend(f"- {value}" for value in values)
    return lines


def build_manifest(
    tasks: list[dict[str, Any]],
    layer2_dir: Path = LAYER2_DIR,
) -> list[dict[str, Any]]:
    """Flatten task YAML objects into manifest records."""
    rows: list[dict[str, Any]] = []
    seen_case_ids: set[str] = set()
    for task in tasks:
        validate_task(task)
        task_id = str(task["id"])
        variants = task["variants"]
        for variant_name, variant in sorted(variants.items()):
            case_id = f"{task_id}__{variant_name}"
            if case_id in seen_case_ids:
                raise ValueError(f"Duplicate Layer 2 case id: {case_id}")
            seen_case_ids.add(case_id)
            validate_variant(task_id, variant_name, variant, layer2_dir)
            rows.append(
                {
                    "case_id": case_id,
                    "task_id": task_id,
                    "variant": variant_name,
                    "title": task["title"],
                    "repository_slice": task["repository_slice"],
                    "change_type": task["change_type"],
                    "expected_scope": task["expected_scope"],
                    "spec_text": spec_to_text(task["spec"], task["expected_scope"]),
                    "patch_path": variant["patch"],
                    "expected_touched_files": task["expected_touched_files"],
                    "primary_label": variant["primary_label"],
                    "gold": variant["gold"],
                }
            )
    return rows


def validate_task(task: dict[str, Any]) -> None:
    """Validate required task fields."""
    required = {
        "id",
        "title",
        "repository_slice",
        "change_type",
        "expected_scope",
        "spec",
        "expected_touched_files",
        "variants",
    }
    missing = sorted(required - set(task))
    if missing:
        raise ValueError(f"Task {task.get('id', '<unknown>')} missing fields: {missing}")
    if not isinstance(task["expected_touched_files"], list) or not task["expected_touched_files"]:
        raise ValueError(f"Task {task['id']} must list expected_touched_files")
    if not isinstance(task["variants"], dict) or not task["variants"]:
        raise ValueError(f"Task {task['id']} must define variants")
    spec = task["spec"]
    if not isinstance(spec, dict) or not spec.get("goal"):
        raise ValueError(f"Task {task['id']} must define spec.goal")


def validate_variant(
    task_id: str,
    variant_name: str,
    variant: dict[str, Any],
    layer2_dir: Path,
) -> None:
    """Validate one variant object."""
    if variant.get("primary_label") not in VALID_PRIMARY_LABELS:
        raise ValueError(f"{task_id}/{variant_name} has invalid primary_label")
    gold = variant.get("gold")
    if not isinstance(gold, dict):
        raise ValueError(f"{task_id}/{variant_name} must define gold labels")
    missing_gold = sorted(REQUIRED_GOLD_KEYS - set(gold))
    if missing_gold:
        raise ValueError(f"{task_id}/{variant_name} missing gold labels: {missing_gold}")
    patch = variant.get("patch")
    if not isinstance(patch, str) or not patch:
        raise ValueError(f"{task_id}/{variant_name} must define patch path")
    if not (layer2_dir / patch).exists():
        raise FileNotFoundError(f"{task_id}/{variant_name} patch not found: {patch}")


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL manifest."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Build AgenticPR Layer 2 manifest")
    parser.add_argument("--tasks-dir", type=Path, default=DEFAULT_TASKS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    tasks = load_tasks(args.tasks_dir)
    rows = build_manifest(tasks, layer2_dir=args.tasks_dir.parent)
    write_manifest(args.output, rows)
    print(f"Loaded {len(tasks)} task(s)")
    print(f"Written {len(rows)} case(s): {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
