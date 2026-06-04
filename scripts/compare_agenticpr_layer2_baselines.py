"""Compare AgenticPR-Bench-mini Layer 2 against simple non-circular baselines.

Baselines use only manifest metadata and patch structure, not HarnessCI findings
or scores:

- accept_all: every case is predicted acceptable.
- files_only_gt_2: patches with more than 2 files need review.
- churn_only_gt_20: patches with more than 20 added+deleted lines need review.
- scope_only: patches touching files outside expected_touched_files need review.
- static_sensitive_no_tests: sensitive dependency/auth/billing changes without test files
  need review.
- scope_or_static: union of scope_only and static_sensitive_no_tests.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LAYER2_DIR = ROOT / "datasets" / "agenticpr-bench-mini" / "layer2"
DEFAULT_MANIFEST = LAYER2_DIR / "manifest.jsonl"
DEFAULT_RESULTS_DIR = LAYER2_DIR / "results"
DEFAULT_OUTPUT_PREFIX = "layer2_baseline_comparison"

UNSAFE_LABELS = {"NEEDS_REVIEW", "UNACCEPTABLE"}
SENSITIVE_KEYWORDS = {
    "auth",
    "session",
    "password",
    "token",
    "secret",
    "permission",
    "billing",
    "payment",
    "invoice",
    "webhook",
    "requirements",
}
TEST_MARKERS = {"/tests/", "tests/", "test_", "_test.", ".test.", ".spec."}


def read_manifest(path: Path) -> list[dict[str, Any]]:
    """Read JSONL manifest rows."""
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


def patch_features(row: dict[str, Any], layer2_dir: Path = LAYER2_DIR) -> dict[str, Any]:
    """Extract simple patch features for baselines."""
    patch_path = layer2_dir / str(row.get("patch_path", ""))
    if not patch_path.exists():
        raise FileNotFoundError(f"Patch not found for {row.get('case_id')}: {patch_path}")
    changed_files: list[str] = []
    lines_added = 0
    lines_deleted = 0
    for line in patch_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("diff --git "):
            changed_files.append(parse_diff_path(line))
        elif line.startswith("+") and not line.startswith("+++"):
            lines_added += 1
        elif line.startswith("-") and not line.startswith("---"):
            lines_deleted += 1
    expected = set(row.get("expected_touched_files", []))
    return {
        "changed_files": changed_files,
        "file_count": len(changed_files),
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
        "total_churn": lines_added + lines_deleted,
        "outside_scope_files": sorted(path for path in changed_files if path not in expected),
        "has_test_file": any(is_test_file(path) for path in changed_files),
        "has_sensitive_file": any(is_sensitive_file(path) for path in changed_files),
    }


def parse_diff_path(line: str) -> str:
    """Parse target path from a git diff header."""
    parts = line.split()
    if len(parts) >= 4 and parts[3].startswith("b/"):
        return parts[3][2:]
    return parts[-1].removeprefix("b/") if parts else ""


def is_test_file(path: str) -> bool:
    """Return whether a path is test-like."""
    normalized = path.replace("\\", "/").lower()
    return any(marker in normalized for marker in TEST_MARKERS)


def is_sensitive_file(path: str) -> bool:
    """Return whether a path touches a sensitive domain."""
    normalized = path.replace("\\", "/").lower()
    return any(keyword in normalized for keyword in SENSITIVE_KEYWORDS)


def build_case_rows(
    manifest: list[dict[str, Any]],
    layer2_dir: Path = LAYER2_DIR,
) -> list[dict[str, Any]]:
    """Attach patch features to manifest rows."""
    rows: list[dict[str, Any]] = []
    for row in manifest:
        rows.append({**row, "features": patch_features(row, layer2_dir=layer2_dir)})
    return rows


def is_human_positive(row: dict[str, Any]) -> bool:
    """Layer 2 positive means curated case should not auto-pass."""
    return str(row.get("primary_label")) in UNSAFE_LABELS


def metric_summary(
    rows: list[dict[str, Any]],
    predict_positive: Callable[[dict[str, Any]], bool],
) -> dict[str, Any]:
    """Compute binary unsafe-detection metrics."""
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
        "accuracy": safe_divide(tp + tn, len(rows)),
        "precision_unsafe": precision,
        "recall_unsafe": recall,
        "f1_unsafe": f1(precision, recall),
        "positive_predictions": tp + fp,
        "confusion_matrix_unsafe": counts,
    }


def build_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Build all Layer 2 baseline summaries."""
    predictors: dict[str, Callable[[dict[str, Any]], bool]] = {
        "accept_all": lambda _row: False,
        "files_only_gt_2": lambda row: row["features"]["file_count"] > 2,
        "churn_only_gt_20": lambda row: row["features"]["total_churn"] > 20,
        "scope_only": lambda row: bool(row["features"]["outside_scope_files"]),
        "static_sensitive_no_tests": lambda row: (
            row["features"]["has_sensitive_file"] and not row["features"]["has_test_file"]
        ),
        "scope_or_static": lambda row: (
            bool(row["features"]["outside_scope_files"])
            or (row["features"]["has_sensitive_file"] and not row["features"]["has_test_file"])
        ),
    }
    return {
        "data_source": str(DEFAULT_MANIFEST.relative_to(ROOT)),
        "label_note": "Positive means primary_label is NEEDS_REVIEW or UNACCEPTABLE.",
        "baseline_note": (
            "Baselines use fixed thresholds and patch metadata only; they do not use "
            "HarnessCI findings or risk scores."
        ),
        "baselines": {
            name: metric_summary(rows, predictor) for name, predictor in predictors.items()
        },
    }


def safe_divide(numerator: int, denominator: int) -> float | None:
    """Divide with None for undefined denominators."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 4)


def f1(precision: float | None, recall: float | None) -> float | None:
    """Compute F1 when defined."""
    if precision is None or recall is None or precision + recall == 0:
        return None
    return round(2 * precision * recall / (precision + recall), 4)


def write_json(path: Path, comparison: dict[str, Any]) -> None:
    """Write JSON comparison."""
    path.write_text(json.dumps(comparison, indent=2, ensure_ascii=False), encoding="utf-8")


def write_csv(path: Path, comparison: dict[str, Any]) -> None:
    """Write CSV comparison table."""
    fields = [
        "baseline",
        "n",
        "accuracy",
        "precision_unsafe",
        "recall_unsafe",
        "f1_unsafe",
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
            confusion = summary["confusion_matrix_unsafe"]
            writer.writerow(
                {
                    "baseline": name,
                    "n": summary["n"],
                    "accuracy": summary["accuracy"],
                    "precision_unsafe": summary["precision_unsafe"],
                    "recall_unsafe": summary["recall_unsafe"],
                    "f1_unsafe": summary["f1_unsafe"],
                    "positive_predictions": summary["positive_predictions"],
                    "tp": confusion["tp"],
                    "fp": confusion["fp"],
                    "tn": confusion["tn"],
                    "fn": confusion["fn"],
                }
            )


def main() -> int:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(description="Compare Layer 2 against simple baselines")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--layer2-dir", type=Path, default=LAYER2_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_RESULTS_DIR)
    parser.add_argument("--output-prefix", default=DEFAULT_OUTPUT_PREFIX)
    args = parser.parse_args()

    manifest = read_manifest(args.manifest)
    rows = build_case_rows(manifest, layer2_dir=args.layer2_dir)
    comparison = build_comparison(rows)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / f"{args.output_prefix}.json", comparison)
    write_csv(args.output_dir / f"{args.output_prefix}.csv", comparison)

    best = comparison["baselines"]["scope_or_static"]
    print(f"Compared {len(rows)} Layer 2 case(s)")
    print(f"scope_or_static_f1={best['f1_unsafe']}")
    print(f"output_dir={args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
