"""Compare Layer 1.1 HarnessCI with and without simulated telemetry traces.

Evaluates two scenarios on 80 Layer 1.1 cases:
1. Diff-only: HarnessCI uses only spec+diff (no telemetry).
2. Diff+traces: adds synthetic telemetry signals.

Synthetic traces encode: larger patches -> more edit attempts, findings -> retries/failures.
This is a controlled experiment to measure theoretical telemetry impact.
Real agent traces are needed for actual improvement evidence.
"""

from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRACES_PATH = ROOT / "datasets/agenticpr-bench-mini/results/layer1.1_traces.json"
SPECS_PATH = ROOT / "datasets/agenticpr-bench-mini/raw/layer1.1_specs.jsonl"
DIFFS_DIR = ROOT / "datasets/agenticpr-bench-mini/raw/diffs"
RESULTS_PATH = ROOT / "datasets/agenticpr-bench-mini/results/layer1.1_results.json"
OUTPUT_PATH = ROOT / "datasets/agenticpr-bench-mini/results/layer1_telemetry_comparison.json"


def load_specs() -> dict[str, str]:
    specs: dict[str, str] = {}
    with SPECS_PATH.open(encoding="utf-8") as fh:
        for line in fh:
            rec = json.loads(line.strip())
            specs[rec["dataset_id"]] = rec.get("spec_text", "")
    return specs


def load_traces() -> dict[str, dict[str, int]]:
    traces: dict[str, dict[str, int]] = {}
    with TRACES_PATH.open(encoding="utf-8") as fh:
        for rec in json.load(fh):
            tid = rec["dataset_id"]
            traces[tid] = {
                "edit_attempts": rec.get("edit_attempts", 0),
                "retries": rec.get("retries", 0),
                "test_runs": rec.get("test_runs", 0),
                "failed_test_runs": rec.get("failed_test_runs", 0),
                "error_count": rec.get("error_count", 0),
            }
    return traces


def diff_path_for(dataset_id: str) -> Path:
    safe = dataset_id.replace("/", "__")
    return DIFFS_DIR / f"{safe}.diff"


def _load_spec(spec_text: str):
    audit = importlib.import_module("harnessci.audit")
    return audit._load_spec(None, spec_text)


def _make_telemetry(signals: dict[str, int]):
    models = importlib.import_module("harnessci.models")
    return models.TelemetrySummary(
        available=True,
        edit_attempts=signals.get("edit_attempts"),
        retries=signals.get("retries"),
        test_runs=signals.get("test_runs"),
        failed_test_runs=signals.get("failed_test_runs"),
        error_count=signals.get("error_count"),
    )


def _parse_diff_features(diff_text: str):
    diff_mod = importlib.import_module("harnessci.diff")
    raw = diff_mod.parse_diff_text(diff_text)
    classified = diff_mod.classify_files(raw)
    return diff_mod.build_diff_features(classified)


def evaluate_with_telemetry(
    results: list[dict[str, object]],
    specs: dict[str, str],
    traces: dict[str, dict[str, int]],
) -> list[dict[str, object]]:
    audit = importlib.import_module("harnessci.audit")
    scoring = importlib.import_module("harnessci.scoring")
    outputs = []
    for rec in results:
        dataset_id = str(rec.get("dataset_id", ""))
        dpath = diff_path_for(dataset_id)
        if not dpath.exists():
            continue
        diff_text = dpath.read_text(encoding="utf-8", errors="replace")
        spec_text = specs.get(dataset_id, "")
        telemetry_signals = traces.get(dataset_id, {})
        telemetry = _make_telemetry(telemetry_signals)
        diff_features = _parse_diff_features(diff_text)
        spec_model = _load_spec(spec_text)
        test_signals = audit._derive_test_signals(diff_features)
        scores = scoring.compute_scores(spec_model, diff_features, test_signals, telemetry)
        findings = scoring.build_findings(spec_model, diff_features, test_signals, telemetry)
        decision = scoring.decide(
            scores=scores,
            test_signals=test_signals,
            findings=findings,
            block_on_failed_tests=True,
            block_on_security_critical=True,
            no_spec=not spec_model.usable,
            insufficient_on_missing_spec=True,
        )
        before_risk = int(rec.get("overall_agentic_risk", 0))
        outputs.append(
            {
                "dataset_id": dataset_id,
                "human_label": rec.get("human_label"),
                "diff_only_decision": rec.get("harnessci_decision"),
                "telemetry_decision": decision.value,
                "decision_changed": decision.value != rec.get("harnessci_decision"),
                "diff_only_risk": before_risk,
                "telemetry_risk": int(scores.overall_agentic_risk),
                "risk_delta": int(scores.overall_agentic_risk) - before_risk,
                "diff_only_findings": int(rec.get("finding_count", 0)),
                "telemetry_findings": len(findings),
                "telemetry_signals": telemetry_signals,
            }
        )
    return outputs


def compute_comparison_metrics(
    before: list[dict[str, object]],
    after: list[dict[str, object]],
) -> dict[str, object]:
    changed = sum(1 for r in after if r["decision_changed"])
    risk_deltas = [r["risk_delta"] for r in after if r["risk_delta"] != 0]
    escalation = sum(
        1
        for r in after
        if r["decision_changed"]
        and r.get("human_label") != "ACCEPTABLE"
        and r["telemetry_decision"] in ("REVIEW_REQUIRED", "BLOCK")
    )
    deescalation = sum(
        1
        for r in after
        if r["decision_changed"]
        and r.get("human_label") == "ACCEPTABLE"
        and r["telemetry_decision"] == "PASS"
    )
    notes = [
        "Synthetic telemetry: edit_attempts, retries, test_runs, failed_test_runs.",
        "Traces generated from diff metadata via seeded RNG.",
        "Real agent traces would show actual improvement potential.",
    ]
    return {
        "total_cases": len(after),
        "decisions_changed": changed,
        "escalations": escalation,
        "de-escalations": deescalation,
        "mean_risk_delta": round(sum(risk_deltas) / len(risk_deltas), 2) if risk_deltas else 0.0,
        "notes": notes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare Layer 1.1 with and without telemetry")
    parser.add_argument("--output", type=Path, default=OUTPUT_PATH)
    _args = parser.parse_args()

    specs = load_specs()
    traces = load_traces()
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))

    comparison = evaluate_with_telemetry(results, specs, traces)
    metrics = compute_comparison_metrics(results, comparison)

    output_data = {"metrics": metrics, "cases": comparison}
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Compared {metrics['total_cases']} cases")
    print(f"  decisions_changed: {metrics['decisions_changed']}")
    print(f"  escalations (unsafe cases): {metrics['escalations']}")
    print(f"  de-escalations (acceptable cases): {metrics['de-escalations']}")
    print(f"  mean_risk_delta: {metrics['mean_risk_delta']}")
    print(f"  output: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
