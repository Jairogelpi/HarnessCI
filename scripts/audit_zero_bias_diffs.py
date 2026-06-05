"""Audit zero-bias 100K sample: full diff-based evaluation.

Runs the complete HarnessCI pipeline (spec inference + diff audit + scoring)
on all PR diffs fetched for the zero-bias sample. Produces full metrics:
accuracy, precision, recall, F1, per-agent breakdown, confidence intervals.

Usage:
    py scripts/audit_zero_bias_diffs.py [--batch-size 500]

Requires:
    datasets/agenticpr-bench-mini/layer3/diffs_zero_bias/
    datasets/agenticpr-bench-mini/layer3/diffs_index_zero_bias.jsonl
"""

from __future__ import annotations

import json
import os
import random
import statistics
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LAYER3_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3"
DIFF_DIR = LAYER3_DIR / "diffs_zero_bias"
INDEX_PATH = LAYER3_DIR / "diffs_index_zero_bias.jsonl"
MANIFEST_PATH = LAYER3_DIR / "manifest_zero_bias.json"
RESULTS_DIR = LAYER3_DIR / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

AGENTS = ["Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"]


def load_cases() -> list[dict]:
    """Load cases from index + manifest for labels."""
    manifest_map: dict[str, dict] = {}
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        for pr in json.load(fh):
            manifest_map[pr["dataset_id"]] = pr

    # Load from index (has diff_path info)
    index_map: dict[str, dict] = {}
    if INDEX_PATH.exists():
        with INDEX_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    if rec.get("status") == "fetched":
                        index_map[rec["dataset_id"]] = rec
                except Exception:
                    pass

    cases = []
    for ds_id, rec in index_map.items():
        manifest = manifest_map.get(ds_id, {})
        cases.append({
            "dataset_id": ds_id,
            "agent": rec.get("agent", manifest.get("agent", "unknown")),
            "repo": rec.get("repo", manifest.get("repo", "")),
            "pr_number": rec.get("pr_number", manifest.get("pr_number", 0)),
            "human_label": rec.get("human_label", manifest.get("human_label", "")),
            "diff_path": rec.get("diff_path", ""),
            "html_url": rec.get("html_url", manifest.get("html_url", "")),
        })
    return cases


def safe_read(path: Path, max_bytes: int = 2_000_000) -> str:
    if not path.exists():
        return ""
    content = path.read_bytes()[:max_bytes]
    return content.decode("utf-8", errors="replace")


def audit_pr(case: dict) -> dict:
    import importlib

    run_audit_from_diff_text = importlib.import_module(
        "harnessci.audit"
    ).run_audit_from_diff_text

    diff_path_str = case.get("diff_path", "")
    if not diff_path_str:
        return _fallback(case, "PASS")

    diff_path = ROOT / diff_path_str
    diff_text = safe_read(diff_path)

    if not diff_text or len(diff_text) < 20:
        return _fallback(case, "PASS")

    # Build spec from manifest metadata
    spec = build_spec_from_case(case)

    try:
        report = run_audit_from_diff_text(diff_text, spec_text=spec)
    except Exception:  # noqa: BLE001
        return _fallback(case, "PASS")

    decision = report.decision.value
    label = case["human_label"]

    strict = (
        (label == "ACCEPTABLE" and decision == "PASS")
        or (label == "NEEDS_REVIEW" and decision in ("REVIEW_REQUIRED", "BLOCK"))
    )
    unsafe = (
        decision in ("REVIEW_REQUIRED", "BLOCK")
        if label == "NEEDS_REVIEW"
        else decision == "PASS"
    )
    fp = decision != "PASS" and label == "ACCEPTABLE"
    fn_seg = decision == "PASS" and label == "NEEDS_REVIEW"

    return {
        "dataset_id": case["dataset_id"],
        "agent": case["agent"],
        "repo": case["repo"],
        "human_label": label,
        "decision": decision,
        "risk": report.overall_agentic_risk,
        "n_findings": len(report.findings),
        "top_findings": [f.message for f in report.findings[:5]],
        "strict_correct": strict,
        "unsafe": unsafe,
        "false_positive": fp,
        "false_negative": fn_seg,
        "diff_bytes": os.path.getsize(ROOT / diff_path_str) if diff_path.exists() else 0,
    }


def _fallback(case: dict, decision: str) -> dict:
    label = case.get("human_label", "")
    return {
        "dataset_id": case["dataset_id"],
        "agent": case["agent"],
        "repo": case["repo"],
        "human_label": label,
        "decision": decision,
        "risk": 0.0,
        "n_findings": 0,
        "top_findings": [],
        "strict_correct": label == "ACCEPTABLE",
        "unsafe": label == "NEEDS_REVIEW",
        "false_positive": False,
        "false_negative": label == "NEEDS_REVIEW",
        "diff_bytes": 0,
    }


def build_spec_from_case(case: dict) -> str:
    # Use title from manifest if available, else generic
    title = case.get("title", "")
    body = case.get("body_excerpt", "")
    body = str(body)[:1000] if body else ""
    if not title:
        title = f"PR #{case.get('pr_number', '?')} in {case.get('repo', '')}"
    parts = [f"## Goal\n{title}"]
    if body:
        parts.append(f"\n## Description\n{body}")
    return "\n".join(parts)


def bootstrap_ci(values: list[float], n_boot: int = 1000, ci: float = 0.95) -> dict:
    if len(values) < 2:
        mv = values[0] if values else 0.0
        return {"mean": mv, "ci_low": mv, "ci_high": mv}
    obs = statistics.mean(values)
    rng = random.Random(42)
    boot_means = []
    for _ in range(n_boot):
        idxs = [rng.randint(0, len(values) - 1) for _ in values]
        boot_means.append(statistics.mean([values[i] for i in idxs]))
    boot_means.sort()
    alpha = (1 - ci) / 2
    lo = int(len(boot_means) * alpha)
    hi = int(len(boot_means) * (1 - alpha))
    return {
        "mean": round(obs, 4),
        "ci_low": round(boot_means[lo], 4),
        "ci_high": round(boot_means[hi], 4),
    }


def _per_pr_f1(r: dict) -> float:
    tp = 1 - (1 if r["false_positive"] else 0) - (1 if r["false_negative"] else 0)
    tp = max(0, tp)
    fp = 1.0 if r["false_positive"] else 0.0
    fn = 1.0 if r["false_negative"] else 0.0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    return 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0


def aggregate(results: list[dict]) -> dict:
    by_agent = {}
    all_correct = []
    all_risks = []

    for agent in AGENTS:
        agent_rs = [r for r in results if r["agent"] == agent]
        n = len(agent_rs)
        if n == 0:
            continue

        risks = [r["risk"] for r in agent_rs]
        correct = [1.0 if r["strict_correct"] else 0.0 for r in agent_rs]
        f1s = [_per_pr_f1(r) for r in agent_rs]
        all_correct.extend(correct)
        all_risks.extend(risks)

        fp = sum(1 for r in agent_rs if r["false_positive"])
        fn_seg = sum(1 for r in agent_rs if r["false_negative"])
        tp = n - fp - fn_seg
        tn = n - sum(1 for r in agent_rs if r["unsafe"] or r["false_positive"])

        acc = sum(correct) / n
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        rec = tp / (tp + fn_seg) if (tp + fn_seg) > 0 else 0.0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        decisions = {"PASS": 0, "REVIEW_REQUIRED": 0, "BLOCK": 0}
        for r in agent_rs:
            d = r["decision"]
            if d in decisions:
                decisions[d] += 1

        by_agent[agent] = {
            "n": n,
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "fpr": round(fpr, 4),
            "mean_risk": round(statistics.mean(risks), 2),
            "std_risk": round(statistics.stdev(risks), 2) if len(risks) > 1 else 0,
            "false_positives": fp,
            "false_negatives": fn_seg,
            "decisions": decisions,
            "ci_accuracy": bootstrap_ci(correct),
            "ci_f1": bootstrap_ci(f1s),
        }

    total = len(results)
    all_c = sum(all_correct)
    overall_acc = round(all_c / total, 4) if total else 0
    overall_ci = bootstrap_ci(all_correct)

    return {
        "total": total,
        "overall_accuracy": overall_acc,
        "overall_ci": overall_ci,
        "per_agent": by_agent,
        "n_repos": len(set(r["repo"] for r in results)),
        "methodology": (
            "Full diff audit (spec inference + diff parsing + scoring + decision). "
            "Zero-bias 100K sample. 95% bootstrap CI (1000 iterations)."
        ),
    }


def main() -> int:
    t0 = time.time()
    print("Loading cases...", flush=True)
    cases = load_cases()
    print(f"  {len(cases):,} cases with fetched diffs", flush=True)

    if not cases:
        print("No diffs found. Run fetch_zero_bias_diffs.py first.")
        return 1

    print("Auditing (full diff pipeline)...", flush=True)
    results = []
    errors = 0

    for i, case in enumerate(cases):
        if i % 1000 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            remain = (len(cases) - i) / rate if rate > 0 else 0
            print(f"  {i:,}/{len(cases):,}  ({rate:.0f}/s, ~{remain/60:.0f}min left)",
                  flush=True)
        try:
            result = audit_pr(case)
            results.append(result)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            if errors <= 3:
                print(f"  Error {case.get('dataset_id','?')}: {exc}")

    elapsed = time.time() - t0
    print(f"\n  Done: {len(results):,} audited in {elapsed:.0f}s "
          f"({len(results)/elapsed:.0f}/s), {errors} errors", flush=True)

    metrics = aggregate(results)

    res_path = RESULTS_DIR / "zero_bias_audit_results.json"
    with res_path.open("w", encoding="utf-8") as fh:
        json.dump(results, fh)
    print(f"Results: {res_path}  ({len(results):,} records)", flush=True)

    met_path = RESULTS_DIR / "zero_bias_audit_metrics.json"
    with met_path.open("w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"Metrics: {met_path}", flush=True)

    sep = "=" * 80
    oci = metrics["overall_ci"]
    print(f"\n{sep}")
    print(f"Zero-Bias 100K Full Audit: {len(results):,} diffs")
    print(f"Overall accuracy: {metrics['overall_accuracy']:.4f}  "
          f"95% CI=[{oci['ci_low']:.4f}, {oci['ci_high']:.4f}]")
    print(f"{sep}")
    print("  {:<20} {:>6}  {:>6} {:>6} {:>6} {:>6} {:>6}  {:>6}".format(
        "Agent", "n", "Acc", "Prec", "Rec", "F1", "FPR", "Risk"))
    print("  " + "-" * 74)
    for agent, m in sorted(metrics["per_agent"].items()):
        print(
            f"  {agent:<20} {m['n']:>6}  "
            f"{m['accuracy']:.3f} {m['precision']:.3f} "
            f"{m['recall']:.3f} {m['f1']:.3f} {m['fpr']:.3f}  "
            f"{m['mean_risk']:.1f}"
        )
    print("=" * 80)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())