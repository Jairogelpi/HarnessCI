"""Evaluate HarnessCI against AgenticPR-Bench-mini layer 1.

The evaluator reads the safe layer-1 manifest, audits each local PR diff with
HarnessCI's pure diff API, and writes layer-1.1 proxy comparison artifacts:

- datasets/agenticpr-bench-mini/results/layer1.1_results.csv
- datasets/agenticpr-bench-mini/results/layer1.1_results.json
- datasets/agenticpr-bench-mini/results/layer1.1_metrics.json

Layer 1 labels are maintainer-decision proxies, not perfect correctness labels:
merged PRs are `ACCEPTABLE`; closed-without-merge PRs are `NEEDS_REVIEW`.
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

DATASET_DIR = ROOT / "datasets" / "agenticpr-bench-mini"
DEFAULT_MANIFEST = DATASET_DIR / "raw" / "layer1_real_github_prs.jsonl"
DEFAULT_SPECS = DATASET_DIR / "raw" / "layer1.1_specs.jsonl"
DEFAULT_RESULTS_DIR = DATASET_DIR / "results"
DEFAULT_OUTPUT_PREFIX = "layer1.1"

RESULT_FIELDS = [
    "dataset_id",
    "agent",
    "owner",
    "repo",
    "pr_number",
    "html_url",
    "human_label",
    "harnessci_decision",
    "overall_agentic_risk",
    "files_changed",
    "lines_added",
    "lines_deleted",
    "manifest_changed_files",
    "manifest_additions",
    "manifest_deletions",
    "spec_used",
    "finding_count",
    "top_findings",
    "diff_sha256",
]

MODEL_POSITIVE_DECISIONS = {
    "REVIEW_REQUIRED",
    "BLOCK",
    "INSUFFICIENT_INFORMATION",
}


def _load_spec_cache(specs_path: Path) -> dict[str, str]:
    """Load layer-1.1 specs into a dict keyed by dataset_id."""
    if not specs_path.exists():
        return {}
    cache: dict[str, str] = {}
    with specs_path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                cache[str(rec.get("dataset_id", ""))] = str(rec.get("spec_text", ""))
            except json.JSONDecodeError:
                continue
    return cache


def evaluate_layer1(
    manifest_path: Path = DEFAULT_MANIFEST,
    specs_path: Path = DEFAULT_SPECS,
    results_dir: Path = DEFAULT_RESULTS_DIR,
    repo_root: Path = ROOT,
    output_prefix: str = DEFAULT_OUTPUT_PREFIX,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Evaluate all layer-1 manifest entries and write result artifacts."""
    records = read_manifest(manifest_path)
    spec_cache = _load_spec_cache(specs_path)
    print(f"Loaded {len(spec_cache)} layer-1.1 specs from {specs_path.name}")
    rows = [evaluate_record(record, spec_cache, repo_root=repo_root) for record in records]
    metrics = compute_metrics(rows)

    results_dir.mkdir(parents=True, exist_ok=True)
    write_results_csv(results_dir / f"{output_prefix}_results.csv", rows)
    write_results_json(results_dir / f"{output_prefix}_results.json", rows)
    write_metrics_json(results_dir / f"{output_prefix}_metrics.json", metrics)
    return rows, metrics


def read_manifest(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL manifest with clear errors for missing/empty input."""
    if not path.exists():
        raise FileNotFoundError(f"Layer 1 manifest not found: {path}")

    records: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as fh:
        for line_number, line in enumerate(fh, start=1):
            if not line.strip():
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path} at line {line_number}: {exc}") from exc

    if not records:
        raise ValueError(f"Layer 1 manifest is empty: {path}")
    return records


def evaluate_record(
    record: dict[str, Any],
    spec_cache: dict[str, str],
    repo_root: Path = ROOT,
) -> dict[str, Any]:
    """Audit one manifest record with optional spec and return a safe result row."""
    diff_path = repo_root / str(record.get("diff_path", ""))
    if not diff_path.exists():
        raise FileNotFoundError(
            f"Diff file not found for {record.get('dataset_id', '<unknown>')}: {diff_path}"
        )

    diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    dataset_id = str(record.get("dataset_id", ""))
    spec_text = spec_cache.get(dataset_id)

    report = audit_diff_text(diff_text, spec_text=spec_text)

    decision = report.decision.value
    top_findings = [finding.message for finding in report.findings[:3]]
    return {
        "dataset_id": record.get("dataset_id", ""),
        "agent": record.get("agent", ""),
        "owner": record.get("owner", ""),
        "repo": record.get("repo", ""),
        "pr_number": record.get("number", ""),
        "html_url": record.get("html_url", ""),
        "human_label": record.get("human_label", ""),
        "harnessci_decision": decision,
        "overall_agentic_risk": report.overall_agentic_risk,
        "files_changed": report.diff.files_changed,
        "lines_added": report.diff.lines_added,
        "lines_deleted": report.diff.lines_deleted,
        "manifest_changed_files": record.get("changed_files"),
        "manifest_additions": record.get("additions"),
        "manifest_deletions": record.get("deletions"),
        "spec_used": bool(spec_text),
        "finding_count": len(report.findings),
        "top_findings": " | ".join(top_findings),
        "diff_sha256": record.get("diff_sha256", ""),
    }


def audit_diff_text(diff_text: str, spec_text: str | None = None) -> Any:
    """Call HarnessCI's pure diff API with optional spec text."""
    audit_module = importlib.import_module("harnessci.audit")
    return audit_module.run_audit_from_diff_text(diff_text, spec_text=spec_text)


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute proxy metrics against maintainer merge/close labels."""
    if not rows:
        return {
            "n": 0,
            "accuracy_proxy": None,
            "precision_needs_review_or_block": None,
            "recall_needs_review_or_block": None,
            "confusion_matrix_needs_review_or_block": {"tp": 0, "fp": 0, "tn": 0, "fn": 0},
            "mean_risk_by_label": {},
            "decision_distribution": {},
            "spec_used_count": 0,
            "agent_breakdown": {},
        }

    confusion = confusion_counts(rows)
    tp = confusion["tp"]
    fp = confusion["fp"]
    tn = confusion["tn"]
    fn = confusion["fn"]
    n = len(rows)

    return {
        "n": n,
        "accuracy_proxy": safe_divide(tp + tn, n),
        "precision_needs_review_or_block": safe_divide(tp, tp + fp),
        "recall_needs_review_or_block": safe_divide(tp, tp + fn),
        "confusion_matrix_needs_review_or_block": confusion,
        "mean_risk_by_label": mean_risk_by(rows, key="human_label"),
        "decision_distribution": dict(Counter(str(row["harnessci_decision"]) for row in rows)),
        "spec_used_count": sum(1 for row in rows if row.get("spec_used")),
        "agent_breakdown": agent_breakdown(rows),
        "notes": [
            "Metrics use maintainer merge/close decisions as proxy labels, "
            "not perfect correctness.",
            "Human positive means human_label != ACCEPTABLE.",
            "Model positive means decision is REVIEW_REQUIRED, BLOCK, or INSUFFICIENT_INFORMATION.",
            "Layer 1.1 uses weak specs reconstructed from PR metadata, not hidden gold specs.",
        ],
    }


def confusion_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Return TP/FP/TN/FN for the needs-review-or-block proxy target."""
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for row in rows:
        human_positive = str(row.get("human_label")) != "ACCEPTABLE"
        model_positive = str(row.get("harnessci_decision")) in MODEL_POSITIVE_DECISIONS
        if human_positive and model_positive:
            counts["tp"] += 1
        elif not human_positive and model_positive:
            counts["fp"] += 1
        elif not human_positive and not model_positive:
            counts["tn"] += 1
        else:
            counts["fn"] += 1
    return counts


def agent_breakdown(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Return per-agent label, decision, risk, and confusion summaries."""
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get("agent", "unknown"))].append(row)

    summary: dict[str, Any] = {}
    for agent, agent_rows in sorted(grouped.items()):
        summary[agent] = {
            "n": len(agent_rows),
            "human_label_distribution": dict(
                Counter(str(row.get("human_label", "")) for row in agent_rows)
            ),
            "decision_distribution": dict(
                Counter(str(row.get("harnessci_decision", "")) for row in agent_rows)
            ),
            "mean_overall_agentic_risk": mean_int(
                int(row["overall_agentic_risk"]) for row in agent_rows
            ),
            "confusion_matrix_needs_review_or_block": confusion_counts(agent_rows),
        }
    return summary


def mean_risk_by(rows: list[dict[str, Any]], key: str) -> dict[str, float]:
    """Return mean overall risk grouped by row key."""
    grouped: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        grouped[str(row.get(key, ""))].append(int(row["overall_agentic_risk"]))
    return {group: mean_int(values) for group, values in sorted(grouped.items())}


def mean_int(values: Any) -> float:
    """Return a rounded mean for an iterable of ints."""
    materialized = list(values)
    if not materialized:
        return 0.0
    return round(float(statistics.mean(materialized)), 2)


def safe_divide(numerator: int, denominator: int) -> float | None:
    """Divide with None for undefined metric denominators."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def write_results_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write evaluator rows to CSV."""
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in RESULT_FIELDS})


def write_results_json(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write evaluator rows to JSON."""
    path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")


def write_metrics_json(path: Path, metrics: dict[str, Any]) -> None:
    """Write evaluator metrics to JSON."""
    path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Evaluate HarnessCI on AgenticPR-Bench-mini layer 1"
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--results-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument(
        "--specs",
        type=Path,
        default=DEFAULT_SPECS,
        help="Path to layer-1.1 specs JSONL (default: auto-detected)",
    )
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    args = parser.parse_args()

    rows, metrics = evaluate_layer1(
        manifest_path=args.manifest,
        specs_path=args.specs,
        results_dir=args.results_dir,
        repo_root=args.repo_root,
        output_prefix=args.output_prefix,
    )
    print(f"Evaluated {len(rows)} PRs")
    print(f"accuracy_proxy={metrics['accuracy_proxy']}")
    print(f"results_dir={args.results_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
