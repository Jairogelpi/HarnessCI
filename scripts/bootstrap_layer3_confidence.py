"""Bootstrap confidence intervals for Layer 3 real-diff audit results.

Reads the JSON output from `scripts/evaluate_layer3_with_diffs.py` and computes
mean + 95% percentile confidence intervals for strict_accuracy,
unsafe_detection_recall, and unacceptable_block_recall.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/results/layer3_diff_results.json"
OUTPUT_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/results/layer3_diff_bootstrap.json"
DEFAULT_ITERATIONS = 1000
DEFAULT_SEED = 42


def load_results(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return [row for row in data.get("cases", []) if row.get("harnessci_decision")]


def _strict_correct(row: dict[str, Any]) -> bool:
    return bool(row.get("strict_correct"))


def _unsafe_detected(row: dict[str, Any]) -> bool:
    return bool(row.get("unsafe_detected"))


def _unacceptable_block(row: dict[str, Any]) -> bool:
    return bool(row.get("unacceptable_block"))


def metric_bundle(rows: list[dict[str, Any]]) -> dict[str, float]:
    total = len(rows)
    if total == 0:
        return {
            "strict_accuracy": 0.0,
            "unsafe_detection_recall": 0.0,
            "unacceptable_block_recall": 0.0,
        }

    unsafe = [r for r in rows if r["human_label"] != "ACCEPTABLE"]
    unacceptable = [r for r in rows if r["human_label"] == "UNACCEPTABLE"]

    return {
        "strict_accuracy": sum(1 for r in rows if _strict_correct(r)) / total,
        "unsafe_detection_recall": sum(1 for r in unsafe if _unsafe_detected(r)) / len(unsafe)
        if unsafe
        else 0.0,
        "unacceptable_block_recall": sum(1 for r in unacceptable if _unacceptable_block(r))
        / len(unacceptable)
        if unacceptable
        else 0.0,
    }


def bootstrap_rows(
    rows: list[dict[str, Any]],
    iterations: int,
    rng: random.Random,
) -> dict[str, Any]:
    if not rows:
        return {
            "n": 0,
            "iterations": iterations,
            "means": {},
            "ci95": {},
            "samples": [],
        }

    samples: list[dict[str, float]] = []
    n = len(rows)
    for _ in range(iterations):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        samples.append(metric_bundle(sample))

    keys = samples[0].keys()
    means = {key: sum(sample[key] for sample in samples) / iterations for key in keys}

    def percentile(values: list[float], p: float) -> float:
        ordered = sorted(values)
        if len(ordered) == 1:
            return ordered[0]
        idx = (len(ordered) - 1) * p
        lo = int(idx)
        hi = min(lo + 1, len(ordered) - 1)
        frac = idx - lo
        return ordered[lo] * (1 - frac) + ordered[hi] * frac

    ci95 = {
        key: [
            percentile([sample[key] for sample in samples], 0.025),
            percentile([sample[key] for sample in samples], 0.975),
        ]
        for key in keys
    }

    return {
        "n": n,
        "iterations": iterations,
        "means": means,
        "ci95": ci95,
    }


def group_by_agent(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        agent = str(row.get("agent", "unknown"))
        grouped.setdefault(agent, []).append(row)
    return grouped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=RESULTS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    parser.add_argument("--iterations", type=int, default=DEFAULT_ITERATIONS)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()

    rows = load_results(args.results)
    rng = random.Random(args.seed)

    overall = bootstrap_rows(rows, args.iterations, rng)
    per_agent = {
        agent: bootstrap_rows(agent_rows, args.iterations, random.Random(args.seed + i + 1))
        for i, (agent, agent_rows) in enumerate(sorted(group_by_agent(rows).items()))
    }

    output = {
        "source": str(args.results.relative_to(ROOT)),
        "iterations": args.iterations,
        "overall": overall,
        "per_agent": per_agent,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print("Overall bootstrap:")
    print(json.dumps(overall, indent=2, ensure_ascii=False))
    print(f"Saved: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
