"""Evaluate HarnessCI against AgenticPR-Bench-mini Layer 2 pilot cases."""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

LAYER2_DIR = ROOT / "datasets" / "agenticpr-bench-mini" / "layer2"
DEFAULT_MANIFEST = LAYER2_DIR / "manifest.jsonl"
DEFAULT_RESULTS_DIR = LAYER2_DIR / "results"
DEFAULT_OUTPUT_PREFIX = "layer2"

RESULT_FIELDS = [
    "case_id",
    "task_id",
    "variant",
    "repository_slice",
    "change_type",
    "primary_label",
    "harnessci_decision",
    "strict_correct",
    "unsafe_detected",
    "overall_agentic_risk",
    "files_changed",
    "lines_added",
    "lines_deleted",
    "finding_count",
    "top_findings",
    "gold_spec_violation",
    "gold_unrelated_changes",
    "gold_missing_tests",
    "gold_security_sensitive",
    "gold_overengineering",
    "gold_architecture_drift",
]

UNSAFE_LABELS = {"NEEDS_REVIEW", "UNACCEPTABLE"}
UNSAFE_DECISIONS = {"REVIEW_REQUIRED", "BLOCK", "INSUFFICIENT_INFORMATION"}


def read_manifest(path: Path) -> list[dict[str, Any]]:
    """Read Layer 2 JSONL manifest."""
    if not path.exists():
        raise FileNotFoundError(f"Layer 2 manifest not found: {path}")
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} at line {line_number}: {exc}") from exc
    if not rows:
        raise ValueError(f"Layer 2 manifest is empty: {path}")
    return rows


def evaluate_layer2(
    manifest_path: Path = DEFAULT_MANIFEST,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    layer2_dir: Path = LAYER2_DIR,
    output_prefix: str = DEFAULT_OUTPUT_PREFIX,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Evaluate all Layer 2 cases and write artifacts."""
    manifest = read_manifest(manifest_path)
    rows = [evaluate_case(case, layer2_dir=layer2_dir) for case in manifest]
    metrics = compute_metrics(rows)

    results_dir.mkdir(parents=True, exist_ok=True)
    write_results_csv(results_dir / f"{output_prefix}_results.csv", rows)
    write_results_json(results_dir / f"{output_prefix}_results.json", rows)
    write_metrics_json(results_dir / f"{output_prefix}_metrics.json", metrics)
    return rows, metrics


def evaluate_case(case: dict[str, Any], layer2_dir: Path = LAYER2_DIR) -> dict[str, Any]:
    """Evaluate one Layer 2 case."""
    patch_path = layer2_dir / str(case.get("patch_path", ""))
    if not patch_path.exists():
        raise FileNotFoundError(f"Patch not found for {case.get('case_id')}: {patch_path}")
    diff_text = patch_path.read_text(encoding="utf-8", errors="replace")
    report = audit_diff_text(diff_text, spec_text=str(case.get("spec_text", "")))
    decision = report.decision.value
    primary_label = str(case.get("primary_label", ""))
    top_findings = [finding.message for finding in report.findings[:3]]
    gold = case.get("gold", {})
    strict_correct = is_strict_correct(primary_label, decision)
    unsafe_detected = is_unsafe_detected(primary_label, decision)

    return {
        "case_id": case.get("case_id", ""),
        "task_id": case.get("task_id", ""),
        "variant": case.get("variant", ""),
        "repository_slice": case.get("repository_slice", ""),
        "change_type": case.get("change_type", ""),
        "primary_label": primary_label,
        "harnessci_decision": decision,
        "strict_correct": strict_correct,
        "unsafe_detected": unsafe_detected,
        "overall_agentic_risk": report.overall_agentic_risk,
        "files_changed": report.diff.files_changed,
        "lines_added": report.diff.lines_added,
        "lines_deleted": report.diff.lines_deleted,
        "finding_count": len(report.findings),
        "top_findings": " | ".join(top_findings),
        "gold_spec_violation": bool(gold.get("spec_violation")),
        "gold_unrelated_changes": bool(gold.get("unrelated_changes")),
        "gold_missing_tests": bool(gold.get("missing_tests")),
        "gold_security_sensitive": bool(gold.get("security_sensitive")),
        "gold_overengineering": bool(gold.get("overengineering")),
        "gold_architecture_drift": bool(gold.get("architecture_drift")),
    }


def audit_diff_text(diff_text: str, spec_text: str) -> Any:
    """Call HarnessCI's pure diff API."""
    audit_module = importlib.import_module("harnessci.audit")
    return audit_module.run_audit_from_diff_text(diff_text, spec_text=spec_text)


def is_strict_correct(primary_label: str, decision: str) -> bool:
    """Return strict label-vs-decision correctness."""
    if primary_label == "ACCEPTABLE":
        return decision == "PASS"
    if primary_label == "NEEDS_REVIEW":
        return decision == "REVIEW_REQUIRED"
    if primary_label == "UNACCEPTABLE":
        return decision == "BLOCK"
    return False


def is_unsafe_detected(primary_label: str, decision: str) -> bool | None:
    """Return binary unsafe detection result, or None for acceptable cases."""
    if primary_label not in UNSAFE_LABELS:
        return None
    return decision in UNSAFE_DECISIONS


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute Layer 2 strict and risk-detection metrics."""
    if not rows:
        return {
            "n": 0,
            "strict_accuracy": None,
            "unsafe_detection_recall": None,
            "unacceptable_block_recall": None,
            "false_positive_review_rate": None,
            "decision_distribution": {},
            "label_distribution": {},
        }

    acceptable = [row for row in rows if row["primary_label"] == "ACCEPTABLE"]
    unsafe = [row for row in rows if row["primary_label"] in UNSAFE_LABELS]
    unacceptable = [row for row in rows if row["primary_label"] == "UNACCEPTABLE"]
    false_positive_reviews = [
        row for row in acceptable if row["harnessci_decision"] in UNSAFE_DECISIONS
    ]

    return {
        "n": len(rows),
        "strict_accuracy": safe_divide(
            sum(1 for row in rows if row["strict_correct"]),
            len(rows),
        ),
        "unsafe_detection_recall": safe_divide(
            sum(1 for row in unsafe if row["unsafe_detected"]),
            len(unsafe),
        ),
        "unacceptable_block_recall": safe_divide(
            sum(1 for row in unacceptable if row["harnessci_decision"] == "BLOCK"),
            len(unacceptable),
        ),
        "false_positive_review_rate": safe_divide(len(false_positive_reviews), len(acceptable)),
        "decision_distribution": dict(Counter(str(row["harnessci_decision"]) for row in rows)),
        "label_distribution": dict(Counter(str(row["primary_label"]) for row in rows)),
        "attribute_positive_counts": attribute_positive_counts(rows),
        "notes": [
            "Layer 2 uses curated specs and gold labels, not maintainer-decision proxies.",
            "Strict accuracy requires ACCEPTABLE→PASS, NEEDS_REVIEW→REVIEW_REQUIRED, "
            "and UNACCEPTABLE→BLOCK.",
            "Unsafe detection treats REVIEW_REQUIRED, BLOCK, and INSUFFICIENT_INFORMATION "
            "as positive for NEEDS_REVIEW/UNACCEPTABLE cases.",
        ],
    }


def attribute_positive_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Count positive gold attributes in result rows."""
    keys = [field for field in RESULT_FIELDS if field.startswith("gold_")]
    return {key: sum(1 for row in rows if row.get(key)) for key in keys}


def safe_divide(numerator: int, denominator: int) -> float | None:
    """Divide with None for undefined denominators."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write result rows to CSV."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in RESULT_FIELDS})


def write_results_json(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write result rows to JSON."""
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def write_metrics_json(path: Path, metrics: dict[str, Any]) -> None:
    """Write metrics to JSON."""
    path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Evaluate AgenticPR Layer 2 pilot cases")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--layer2-dir", type=Path, default=LAYER2_DIR)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    args = parser.parse_args()

    rows, metrics = evaluate_layer2(
        manifest_path=args.manifest,
        results_dir=args.results_dir,
        layer2_dir=args.layer2_dir,
        output_prefix=args.output_prefix,
    )
    print(f"Evaluated {len(rows)} Layer 2 case(s)")
    print(f"strict_accuracy={metrics['strict_accuracy']}")
    print(f"unsafe_detection_recall={metrics['unsafe_detection_recall']}")
    print(f"results_dir={args.results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
