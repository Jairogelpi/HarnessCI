"""Evaluate Layer 3 using fetched real GitHub diffs.

This script audits the fetched Layer 3 diffs (real PR patches) against the
manifest metadata labels and saves overall + per-agent metrics.
"""

from __future__ import annotations

import importlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
LAYER3_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3"
MANIFEST_PATH = LAYER3_DIR / "manifest.json"
INDEX_PATH = LAYER3_DIR / "diffs_index.jsonl"
DIFFS_DIR = LAYER3_DIR / "diffs"
RESULTS_DIR = LAYER3_DIR / "results"
OUTPUT_PATH = RESULTS_DIR / "layer3_diff_results.json"
DEFAULT_LIMIT = 500


def load_manifest() -> dict[str, dict[str, Any]]:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        manifest = json.load(fh)
    return {str(row["dataset_id"]): row for row in manifest}


def load_successful_index(limit: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with INDEX_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("status") in {"cached", "fetched"}:
                rows.append(row)
            if len(rows) >= limit:
                break
    return rows


def build_spec_from_metadata(case: dict[str, Any]) -> str:
    title = str(case.get("title", "")).strip()
    body = str(case.get("body_excerpt", "")).strip()

    parts = ["## Goal", title or f"Layer 3 case for {case.get('repo', 'unknown')}"]
    if body:
        parts.append("")
        parts.append("## Description")
        parts.append(body)
    parts.append("")
    parts.append("## Acceptance Criteria")
    parts.append("- Preserve the intended change described by the PR title/body")
    parts.append("- Do not introduce unrelated scope creep")
    return "\n".join(parts).strip() + "\n"


def _strict_correct(label: str, decision: str) -> bool:
    return (
        (label == "ACCEPTABLE" and decision == "PASS")
        or (label == "NEEDS_REVIEW" and decision == "REVIEW_REQUIRED")
        or (label == "UNACCEPTABLE" and decision == "BLOCK")
    )


def _unsafe_detected(label: str, decision: str) -> bool:
    return label != "ACCEPTABLE" and decision in {"REVIEW_REQUIRED", "BLOCK"}


def _unacceptable_block(label: str, decision: str) -> bool:
    return label == "UNACCEPTABLE" and decision == "BLOCK"


def evaluate_cases(
    records: list[dict[str, Any]],
    manifest_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    run_audit_from_diff_text = importlib.import_module("harnessci.audit").run_audit_from_diff_text

    results: list[dict[str, Any]] = []

    for idx, record in enumerate(records, start=1):
        dataset_id = str(record["dataset_id"])
        case = manifest_map.get(dataset_id)
        if case is None:
            continue

        diff_path = ROOT / str(record["diff_path"])
        if not diff_path.exists():
            results.append(
                {
                    "dataset_id": dataset_id,
                    "agent": record.get("agent"),
                    "repo": record.get("repo"),
                    "pr_number": record.get("pr_number"),
                    "human_label": record.get("human_label"),
                    "status": "missing_diff",
                }
            )
            continue

        diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
        spec_text = build_spec_from_metadata(case)
        report = run_audit_from_diff_text(diff_text, spec_text=spec_text)
        decision = report.decision.value
        label = str(record.get("human_label", case.get("human_label", "")))

        results.append(
            {
                "dataset_id": dataset_id,
                "agent": record.get("agent"),
                "repo": record.get("repo"),
                "pr_number": record.get("pr_number"),
                "human_label": label,
                "harnessci_decision": decision,
                "overall_agentic_risk": report.overall_agentic_risk,
                "finding_count": len(report.findings),
                "top_findings": [f.message for f in report.findings[:3]],
                "strict_correct": _strict_correct(label, decision),
                "unsafe_detected": _unsafe_detected(label, decision),
                "unacceptable_block": _unacceptable_block(label, decision),
                "diff_path": str(diff_path.relative_to(ROOT)),
                "index_status": record.get("status"),
            }
        )

        if idx % 100 == 0:
            print(f"  Evaluated {idx}/{len(records)} selected cases...")

    return results


def compute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    audited = [r for r in rows if r.get("harnessci_decision")]
    if not audited:
        return {
            "total_cases": 0,
            "strict_accuracy": 0.0,
            "unsafe_detection_recall": 0.0,
            "unacceptable_block_recall": 0.0,
            "false_positive_review_rate": 0.0,
            "decision_distribution": {},
        }

    total = len(audited)
    strict = sum(1 for r in audited if r["strict_correct"])
    unsafe = [r for r in audited if r["human_label"] != "ACCEPTABLE"]
    unacceptable = [r for r in audited if r["human_label"] == "UNACCEPTABLE"]
    fp = sum(
        1 for r in audited if r["human_label"] == "ACCEPTABLE" and r["harnessci_decision"] != "PASS"
    )

    decision_counts: dict[str, int] = defaultdict(int)
    for r in audited:
        decision_counts[r["harnessci_decision"]] += 1

    return {
        "total_cases": total,
        "strict_accuracy": strict / total,
        "unsafe_detection_recall": sum(1 for r in unsafe if r["unsafe_detected"]) / len(unsafe)
        if unsafe
        else 0.0,
        "unacceptable_block_recall": (
            sum(1 for r in unacceptable if r["unacceptable_block"]) / len(unacceptable)
            if unacceptable
            else 0.0
        ),
        "false_positive_review_rate": fp / (total - len(unsafe)) if (total - len(unsafe)) else 0.0,
        "decision_distribution": dict(decision_counts),
    }


def compute_per_agent_metrics(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("harnessci_decision"):
            grouped[str(row.get("agent", "unknown"))].append(row)

    return {agent: compute_metrics(agent_rows) for agent, agent_rows in grouped.items()}


def main() -> int:
    manifest_map = load_manifest()
    selected = load_successful_index(DEFAULT_LIMIT)
    print(f"Loaded {len(manifest_map)} Layer 3 manifest rows")
    print(f"Selected {len(selected)} audited diffs (cached/fetched) from index")

    rows = evaluate_cases(selected, manifest_map)
    metrics = compute_metrics(rows)
    per_agent = compute_per_agent_metrics(rows)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output = {
        "source": {
            "manifest": str(MANIFEST_PATH.relative_to(ROOT)),
            "diff_index": str(INDEX_PATH.relative_to(ROOT)),
            "selected_limit": DEFAULT_LIMIT,
        },
        "metrics": metrics,
        "per_agent": per_agent,
        "cases": rows,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\nOverall metrics:")
    print(json.dumps(metrics, indent=2, ensure_ascii=False))
    print(f"Saved: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
