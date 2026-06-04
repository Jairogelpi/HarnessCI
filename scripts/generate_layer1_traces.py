"""Generate simulated harness traces for Layer 1 real PRs.

This module creates synthetic telemetry data (edit_attempts, retries, tokens,
test_runs, failed_test_runs, error_count) for AgenticPR-Bench-mini Layer 1 cases.
The generation is based on deterministic heuristics from diff metadata:

- larger patches (files, lines) → more edit attempts and retries
- security-sensitive or multi-finding cases → higher instability (retries, errors)
- findings indicate code quality issues → more test failures

Synthetic traces are derived from observable diff signals only — no external
API calls or real agent data. They encode plausible difficulty patterns that
a real harness would exhibit during agent runs.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INPUT_RESULTS = ROOT / "datasets" / "agenticpr-bench-mini" / "results" / "layer1.1_results.json"
OUTPUT_TRACES = ROOT / "datasets" / "agenticpr-bench-mini" / "results" / "layer1.1_traces.json"
SEED = 42

# Seeded RNG for reproducible synthetic traces
rng = random.Random(SEED)


def _estimate_tokens(files_changed: int, lines_added: int, lines_deleted: int) -> int:
    """Estimate token count from diff size (rough heuristic)."""
    total_lines = files_changed + (lines_added + lines_deleted) // 5
    return int(total_lines * 150 * (1 + files_changed * 0.1))


def _estimate_edit_attempts(
    files_changed: int,
    lines_added: int,
    finding_count: int,
    security_files: bool,
) -> int:
    """Estimate edit attempts from diff complexity."""
    base = 2
    base += min(5, files_changed // 3)
    base += min(3, finding_count)
    if security_files:
        base += 1
    if lines_added > 500:
        base += 1
    if lines_added > 2000:
        base += 1
    return int(base + rng.gauss(0, 1))


def _estimate_retries(
    files_changed: int,
    finding_count: int,
    security_files: bool,
) -> int:
    """Estimate retries from instability signals."""
    base = 0
    if files_changed > 10:
        base += 1
    if finding_count > 1:
        base += 1
    if security_files:
        base += rng.randint(0, 1)
    return min(base, 3)


def _estimate_test_runs(
    files_changed: int,
    lines_added: int,
    finding_count: int,
    new_tests: bool,
) -> tuple[int, int]:
    """Estimate test run count and failures."""
    runs = 3 + files_changed // 5
    if lines_added > 500:
        runs += 1
    if new_tests:
        runs += 1
    failures = 0
    if finding_count >= 2:
        failures = rng.randint(0, min(2, runs // 2))
    elif finding_count >= 1:
        failures = rng.randint(0, 1)
    return int(runs), int(failures)


def _estimate_error_count(files_changed: int, finding_count: int) -> int:
    """Estimate non-test errors (type errors, lint errors) from complexity."""
    base = 0
    if files_changed > 10:
        base += 1
    base += min(2, finding_count)
    return int(base + rng.randint(0, 1))


def _guess_security_files(finding_count: int, finding_text: str) -> bool:
    """Heuristic: does the finding text mention security-sensitive changes?"""
    if finding_count == 0:
        return False
    security_keywords = ["security", "sensitive", "auth", "permission", "billing"]
    return any(kw in finding_text.lower() for kw in security_keywords)


def generate_telemetry(record: dict[str, Any], seed: int | None = None) -> dict[str, Any]:
    """Generate synthetic telemetry for a Layer 1 case from its diff metadata."""
    files_changed = record.get("files_changed", 0)
    lines_added = record.get("lines_added", 0)
    lines_deleted = record.get("lines_deleted", 0)
    finding_count = record.get("finding_count", 0)
    finding_text = record.get("top_findings", "")
    new_tests = "new tests" in finding_text.lower()

    security_files = _guess_security_files(finding_count, finding_text)

    edit_attempts = _estimate_edit_attempts(
        files_changed, lines_added, finding_count, security_files
    )
    retries = _estimate_retries(files_changed, finding_count, security_files)
    test_runs, failed_runs = _estimate_test_runs(
        files_changed, lines_added, finding_count, new_tests
    )
    error_count = _estimate_error_count(files_changed, finding_count)
    tokens = _estimate_tokens(files_changed, lines_added, lines_deleted)

    return {
        "edit_attempts": edit_attempts,
        "retries": retries,
        "test_runs": test_runs,
        "failed_test_runs": failed_runs,
        "error_count": error_count,
        "tokens_estimate": tokens,
        "source": "synthetic_from_diff_metadata",
    }


def add_traces_to_results(results_path: Path, output_path: Path) -> None:
    """Read Layer 1.1 results, generate traces, write enriched results."""
    results = json.loads(results_path.read_text(encoding="utf-8"))
    enriched = []
    for record in results:
        telemetry = generate_telemetry(record)
        enriched_record = {**record, **telemetry}
        enriched.append(enriched_record)
    output_path.write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    results_list = list(results)
    total_edit = sum(generate_telemetry(r)["edit_attempts"] for r in results_list)
    total_fail = sum(generate_telemetry(r)["failed_test_runs"] for r in results_list)
    n = len(results_list)
    print(f"Generated telemetry for {n} cases")
    print(f"  edit_attempts avg: {total_edit / n:.1f}")
    print(f"  failed_runs avg: {total_fail / n:.1f}")
    print(f"  output: {output_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate synthetic traces for Layer 1 cases")
    parser.add_argument("--input", type=Path, default=INPUT_RESULTS)
    parser.add_argument("--output", type=Path, default=OUTPUT_TRACES)
    args = parser.parse_args()
    add_traces_to_results(args.input, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())