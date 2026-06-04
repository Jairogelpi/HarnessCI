"""Compare Layer 1.1 HarnessCI results against simple non-circular baselines.

Baselines intentionally use only public manifest/result metadata, not HarnessCI
findings or risk scores:

- accept_all: every PR is predicted acceptable.
- files_only: PRs with more than 5 changed files need review.
- churn_only: PRs with more than 250 added+deleted lines need review.
- files_or_churn: union of the two fixed churn rules.

Outputs:
    datasets/agenticpr-bench-mini/results/layer1.1_baseline_comparison.json
    datasets/agenticpr-bench-mini/results/layer1.1_baseline_comparison.csv
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "agenticpr-bench-mini"
DEFAULT_RESULTS = DATASET_DIR / "results" / "layer1.1_results.csv"
DEFAULT_OUTPUT_DIR = DATASET_DIR / "results"
DEFAULT_OUTPUT_PREFIX = "layer1.1_baseline_comparison"

POSITIVE_DECISIONS = {"REVIEW_REQUIRED", "BLOCK", "INSUFFICIENT_INFORMATION"}


def read_rows(path: Path) -> list[dict[str, str]]:
    """Read Layer 1.1 CSV rows."""
    if not path.exists():
        raise FileNotFoundError(f"Layer 1.1 results not found: {path}")
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def to_int(value: str | int | None) -> int:
    """Parse an int-like value, treating missing values as zero."""
    if value in (None, ""):
        return 0
    return int(value)


def is_human_positive(row: dict[str, str]) -> bool:
    """Human proxy positive means maintainer closed without merge."""
    return row.get("human_label") != "ACCEPTABLE"


def metric_summary(
    rows: list[dict[str, str]],
    predict_positive: Callable[[dict[str, str]], bool],
) -> dict[str, Any]:
    """Compute precision/recall/F1/accuracy for a binary needs-review predictor."""
    counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    for row in rows:
        human = is_human_positive(row)
        pred = predict_positive(row)
        if human and pred:
            counts["tp"] += 1
        elif not human and pred:
            counts["fp"] += 1
        elif not human and not pred:
            counts["tn"] += 1
        else:
            counts["fn"] += 1

    tp = counts["tp"]
    fp = counts["fp"]
    tn = counts["tn"]
    fn = counts["fn"]
    precision = safe_divide(tp, tp + fp)
    recall = safe_divide(tp, tp + fn)
    return {
        "n": len(rows),
        "accuracy_proxy": safe_divide(tp + tn, len(rows)),
        "precision_needs_review_or_block": precision,
        "recall_needs_review_or_block": recall,
        "f1_needs_review_or_block": f1(precision, recall),
        "positive_predictions": tp + fp,
        "confusion_matrix_needs_review_or_block": counts,
    }


def safe_divide(numerator: int, denominator: int) -> float | None:
    """Divide with None for undefined metrics."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def f1(precision: float | None, recall: float | None) -> float | None:
    """Compute F1 when both precision and recall are defined."""
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 4)


def build_comparison(rows: list[dict[str, str]]) -> dict[str, Any]:
    """Build all baseline summaries."""
    predictors: dict[str, Callable[[dict[str, str]], bool]] = {
        "harnessci_layer1.1": lambda row: row.get("harnessci_decision") in POSITIVE_DECISIONS,
        "accept_all": lambda _row: False,
        "files_only_gt_5": lambda row: to_int(row.get("manifest_changed_files")) > 5,
        "churn_only_gt_250": lambda row: (
            to_int(row.get("manifest_additions")) + to_int(row.get("manifest_deletions"))
        ) > 250,
        "files_or_churn": lambda row: (
            to_int(row.get("manifest_changed_files")) > 5
            or to_int(row.get("manifest_additions")) + to_int(row.get("manifest_deletions")) > 250
        ),
    }
    return {
        "data_source": str(DEFAULT_RESULTS.relative_to(ROOT)),
        "label_note": (
            "Human positive means human_label != ACCEPTABLE; labels are "
            "maintainer-decision proxies."
        ),
        "baseline_note": (
            "Churn baselines use fixed thresholds selected before metric computation, "
            "not tuned on this slice."
        ),
        "baselines": {
            name: metric_summary(rows, predictor) for name, predictor in predictors.items()
        },
    }


def write_json(path: Path, comparison: dict[str, Any]) -> None:
    """Write comparison JSON."""
    path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, comparison: dict[str, Any]) -> None:
    """Write comparison table CSV."""
    fields = [
        "baseline",
        "n",
        "accuracy_proxy",
        "precision_needs_review_or_block",
        "recall_needs_review_or_block",
        "f1_needs_review_or_block",
        "positive_predictions",
        "tp",
        "fp",
        "tn",
        "fn",
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for name, summary in comparison["baselines"].items():
            confusion = summary["confusion_matrix_needs_review_or_block"]
            writer.writerow(
                {
                    "baseline": name,
                    "n": summary["n"],
                    "accuracy_proxy": summary["accuracy_proxy"],
                    "precision_needs_review_or_block": summary[
                        "precision_needs_review_or_block"
                    ],
                    "recall_needs_review_or_block": summary["recall_needs_review_or_block"],
                    "f1_needs_review_or_block": summary["f1_needs_review_or_block"],
                    "positive_predictions": summary["positive_predictions"],
                    "tp": confusion["tp"],
                    "fp": confusion["fp"],
                    "tn": confusion["tn"],
                    "fn": confusion["fn"],
                }
            )


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Compare Layer 1.1 against simple baselines")
    parser.add_argument("--results", type=Path, default=DEFAULT_RESULTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    args = parser.parse_args()

    rows = read_rows(args.results)
    comparison = build_comparison(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / f"{args.output_prefix}.json", comparison)
    write_csv(args.output_dir / f"{args.output_prefix}.csv", comparison)

    harness = comparison["baselines"]["harnessci_layer1.1"]
    print(f"Compared {len(rows)} PRs")
    print(f"harnessci_f1={harness['f1_needs_review_or_block']}")
    print(f"output_dir={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
