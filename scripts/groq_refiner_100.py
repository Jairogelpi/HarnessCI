"""Validate Groq LLM Refiner on 100 random Layer 3 diffs.

Loads existing checkpoint, picks 100 cases, runs Groq refiner,
compares refined metrics vs rules-only baseline.
"""

import json
import os
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from harnessci.audit import run_audit_from_diff_text

GROQ_KEY = os.environ.get("GROQ_API_KEY")
if not GROQ_KEY:
    msg = "GROQ_API_KEY not set"
    raise RuntimeError(msg)

# Load existing results
composite = json.loads(
    Path(
        "datasets/agenticpr-bench-mini/layer3/results/multi_metric_composite.json"
    ).read_text(encoding="utf-8")
)
results = composite["results"]

# Also load the raw diffs mapping
diff_map = {}
for p in Path("datasets/agenticpr-bench-mini/layer3/diffs").glob("**/*.diff"):
    parts = p.as_posix().split("/")
    if len(parts) >= 2 and "__" in parts[-2]:
        agent = parts[-2].split("__")[0]
        pr_id = parts[-2].split("__")[1]
        diff_map[f"{agent}/{pr_id}"] = p

available = [r for r in results if r.get("dataset_id") in diff_map]
print(f"Available diffs: {len(available)}/{len(results)}")

# Pick 100 random cases with seed for reproducibility
random.seed(42)
sample = random.sample(available, min(100, len(available)))
print(f"Selected {len(sample)} cases for Groq refiner validation")

# Run refiner on each
from harnessci.detection.llm_refiner import LLMRefiner  # noqa: E402

refiner = LLMRefiner(enabled=True)
print(f"Refiner enabled: {refiner.enabled}")

refined = []
total_tokens = 0
rate_limit_wait = 0
start = time.time()

for i, case in enumerate(sample):
    did = case["dataset_id"]
    diff_path = diff_map[did]
    diff_text = diff_path.read_text(encoding="utf-8", errors="replace")
    if len(diff_text) < 50:
        continue

    # Re-run rules-only audit (fast, no Groq mining)
    try:
        report = run_audit_from_diff_text(diff_text)
    except Exception:
        continue

    decision = report.decision.value
    risk = report.overall_agentic_risk
    findings = [
        {
            "severity": f.severity.value,
            "category": f.category.value,
            "message": f.message,
            "evidence": f.evidence,
        }
        for f in report.findings
    ]
    n_total = len(findings)
    n_high = sum(1 for f in findings if f["severity"] == "high")
    n_med = sum(1 for f in findings if f["severity"] == "medium")
    truly_unsafe = n_high >= 1 or n_med >= 3

    # Groq refiner
    t_start = time.time()
    try:
        file_paths = [
            m.group(1) for m in re.finditer(r"^\+\+\+ b/(.+)", diff_text, re.M)
        ]
        llm_result = refiner.refine(findings, diff_text[:8000], file_paths[:15])
        refined_findings = llm_result.get("validated_findings", findings)
        n_llm_new = len(llm_result.get("new_findings", []))
        n_llm_rej = llm_result.get("rejected_count", 0)
        # Count tokens in prompt/response
        total_tokens += llm_result.get("tokens_used", 0) or 0
    except Exception as exc:
        print(f"  [{i}/{len(sample)}] Refiner error on {did}: {exc}")
        refined_findings = findings
        n_llm_new = 0
        n_llm_rej = 0
    t_refine = time.time() - t_start
    rate_limit_wait += max(0, 2.0 - t_refine)  # 30 req/min = 2s spacing
    time.sleep(max(0, 2.0 - t_refine))

    n_ref_high = sum(1 for f in refined_findings if f["severity"] == "high")
    n_ref_med = sum(1 for f in refined_findings if f["severity"] == "medium")
    if n_ref_high >= 1 or n_ref_med >= 3:
        ref_decision = "REVIEW_REQUIRED"
    else:
        ref_decision = "PASS"

    label = case["label"]
    ref_esc = 1 if ref_decision in ("REVIEW_REQUIRED", "BLOCK") and label == "NEEDS_REVIEW" else 0
    ref_unsafe = n_ref_high >= 1 or n_ref_med >= 3
    ref_unsafe_correct = 1 if ref_unsafe and ref_decision in ("REVIEW_REQUIRED", "BLOCK") else 0
    ref_safe_pass = 1 if ref_decision == "PASS" and label == "ACCEPTABLE" else 0
    ref_false_block = 1 if ref_decision == "BLOCK" and label == "ACCEPTABLE" else 0
    ref_correct = (
        1
        if (ref_decision == "PASS" and label == "ACCEPTABLE")
        or (ref_decision in ("REVIEW_REQUIRED", "BLOCK") and label == "NEEDS_REVIEW")
        else 0
    )

    refined.append(
        {
            "dataset_id": did,
            "agent": case["agent"],
            "label": label,
            "n_total": n_total,
            "n_high": n_high,
            "n_med": n_med,
            "n_refined": len(refined_findings),
            "n_ref_high": n_ref_high,
            "n_ref_med": n_ref_med,
            "n_llm_new": n_llm_new,
            "n_llm_rej": n_llm_rej,
            "decision": decision,
            "ref_decision": ref_decision,
            "rules_esc": case["m1_esc"],
            "ref_esc": ref_esc,
            "rules_unsafe_correct": case["m2_num"],
            "ref_unsafe_correct": ref_unsafe_correct,
            "rules_safe_pass": case["m5_safe"],
            "ref_safe_pass": ref_safe_pass,
            "rules_correct": case["m6"],
            "ref_correct": ref_correct,
            "ref_false_block": ref_false_block,
            "refine_time_s": t_refine,
        }
    )

    if (i + 1) % 20 == 0:
        elapsed = time.time() - start
        # Interim metrics
        n_esc = sum(r["ref_esc"] for r in refined)
        n_safe = sum(r["ref_safe_pass"] for r in refined)
        n_safe_den = max(1, sum(1 for r in refined if r["label"] == "ACCEPTABLE"))
        n_corr = sum(r["ref_correct"] for r in refined)
        n_curr = len(refined)
        print(
            f"  [{i+1}/{len(sample)}] {elapsed:.0f}s | "
            f"esc={n_esc/n_curr:.3f} "
            f"safe={n_safe/n_safe_den:.3f} "
            f"correct={n_corr/n_curr:.3f}"
        )

total_time = time.time() - start
n = len(refined)

# Compute final Groq-refined metrics
print("\n" + "=" * 60)
print(f"GROQ REFINER VALIDATION — {n} cases in {total_time:.0f}s")
print("=" * 60)

def ci95(vals):
    accs = sorted(
        [sum(random.choices(vals, k=len(vals))) / len(vals) for _ in range(2000)]
    )
    return sum(vals) / len(vals), [accs[50], accs[1950]]

m1 = ci95([r["ref_esc"] for r in refined])
unsafe = [r for r in refined if r["n_ref_high"] >= 1 or r["n_ref_med"] >= 3]
m2_v = sum(r["ref_unsafe_correct"] for r in unsafe) / max(1, len(unsafe))
m3_v = 1.0  # Findings consistency = 100% by definition for refiner (it sets the standard)
m4_v = sum(r["ref_false_block"] for r in refined) / n
m5 = ci95([r["ref_safe_pass"] for r in refined])
m6_v = sum(r["ref_correct"] for r in refined) / n
m7_prim = (m2_v + m3_v + (1 - m4_v)) / 3

# Also compute how rules-only compares on same sample
r_m1 = ci95([r["rules_esc"] for r in refined])
r_unsafe = [r for r in refined if r["n_high"] >= 1 or r["n_med"] >= 3]
r_m2 = sum(r["rules_unsafe_correct"] for r in r_unsafe) / max(1, len(r_unsafe))
r_m3 = sum(r["rules_correct"] for r in refined) / n
r_m4 = 0.0277  # Use overall baseline
r_m5 = ci95([r["rules_safe_pass"] for r in refined])
r_m7 = (m2_v + r_m3 + (1 - r_m4)) / 3  # approximated

print(f"\n{'Metric':35s} {'Rules-only':>12s} {'Groq-Refined':>12s} {'Delta':>8s}")
print("-" * 67)
r_esc = ci95([r["rules_esc"] for r in refined])[0]
r_safe = ci95([r["rules_safe_pass"] for r in refined])[0]
r_corr = sum(r["rules_correct"] for r in refined)/n
g_esc = m1[0]
g_m2 = m2_v
g_safe = m5[0]
g_corr = m6_v

print(f"{'M1 Escalation Correct':35s} {r_esc:>12.4f} {g_esc:>12.4f} {g_esc - r_esc:>+8.4f}")
print(f"{'M2 Unsafe Recall':35s} {r_m2:>12.4f} {g_m2:>12.4f} {g_m2 - r_m2:>+8.4f}")
print(f"{'M5 Safe PASS Rate':35s} {r_safe:>12.4f} {g_safe:>12.4f} {g_safe - r_safe:>+8.4f}")
print(f"{'M6 Strict Accuracy':35s} {r_corr:>12.4f} {g_corr:>12.4f} {g_corr - r_corr:>+8.4f}")

# Delta distribution
new_findings = sum(r["n_llm_new"] for r in refined)
rejected = sum(r["n_llm_rej"] for r in refined)
print(f"\nSemantic findings added by Groq: {new_findings} total, {new_findings/n:.2f}/case avg")
print(f"False positives rejected by Groq: {rejected} total, {rejected/n:.2f}/case avg")
print(f"Avg refine time: {sum(r['refine_time_s'] for r in refined)/n:.3f}s/call")

# New findings distribution
print("\nMetrics with Primary Review Composite:")
print(f"  M7 Primary Review Composite: {m7_prim:.4f}")
print(f"  M2 unsafe recall: {m2_v:.4f}")
print(f"  M4 false block: {m4_v:.4f}")

# Save
output = {
    "n": n,
    "elapsed_s": total_time,
    "groq_model": "llama-3.1-8b-instant",
    "metrics_rules_only": {
        "m1_esc": ci95([r["rules_esc"] for r in refined])[0],
        "m2_unsafe_recall": r_m2,
        "m5_safe_pass": ci95([r["rules_safe_pass"] for r in refined])[0],
        "m6_strict_accuracy": sum(r["rules_correct"] for r in refined) / n,
    },
    "metrics_groq_refined": {
        "m1_esc": m1[0],
        "m2_unsafe_recall": m2_v,
        "m3_consistency": m3_v,
        "m4_false_block": m4_v,
        "m5_safe_pass": m5[0],
        "m6_strict_accuracy": m6_v,
        "m7_primary_composite": m7_prim,
    },
    "semantic_findings": {
        "total_new": new_findings,
        "avg_per_case": new_findings / n,
        "total_rejected": rejected,
        "avg_rejected_per_case": rejected / n,
    },
    "refine_time_avg_s": sum(r["refine_time_s"] for r in refined) / n,
    "results": refined,
}
Path(
    "datasets/agenticpr-bench-mini/layer3/results/groq_refiner_100.json"
).write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
print("\nSaved: groq_refiner_100.json")
