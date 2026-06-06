"""External validation + head-to-head with retry logic for Groq rate limits."""

import json
import os
import pathlib
import random
import sys
import time

import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from harnessci.audit import run_audit_from_diff_text

KEY = os.environ.get("GROQ_API_KEY", "")
if not KEY:
    KEY = ""  # must set via env
URL = "https://api.groq.com/openai/v1/chat/completions"


def groq_call(prompt, retries=3):
    for attempt in range(retries):
        try:
            resp = requests.post(
                URL,
                headers={"Authorization": f"Bearer {KEY}"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.1,
                    "max_tokens": 30,
                },
                timeout=60,
            )
            if resp.status_code == 200:
                text = resp.json()["choices"][0]["message"]["content"].strip().upper()
                if "ACCEPTABLE" in text:
                    return "ACCEPTABLE"
                if "NEEDS_REVIEW" in text:
                    return "NEEDS_REVIEW"
                return None  # couldn't parse
            if resp.status_code == 429:
                print(f"  429, retry {attempt + 1}/{retries}")
                time.sleep(5)
                continue
            return None
        except Exception as e:
            print(f"  Error: {e}")
            if attempt < retries - 1:
                time.sleep(5)
    return None


# Load diffs
diff_map = {}
for p in pathlib.Path("datasets/agenticpr-bench-mini/layer3/diffs").glob("**/*.diff"):
    parts = p.as_posix().split("/")
    if len(parts) >= 2 and "__" in parts[-2]:
        a, pid = parts[-2].split("__")[0], parts[-2].split("__")[1]
        diff_map[f"{a}/{pid}"] = p

keys = list(diff_map.keys())
random.seed(42)
sample = random.sample(keys, min(30, len(keys)))
print(f"Sample: {len(sample)} diffs")

# Load baseline
baseline = {
    r["dataset_id"]: r
    for r in json.loads(
        pathlib.Path(
            "datasets/agenticpr-bench-mini/layer3/results/multi_metric_composite.json"
        ).read_text()
    )["results"]
}

results = []
start = time.time()
for i, did in enumerate(sample):
    diff_text = diff_map[did].read_text(encoding="utf-8", errors="replace")
    if len(diff_text) < 50:
        continue
    # HarnessCI
    try:
        hc_raw = run_audit_from_diff_text(diff_text).decision.value
    except Exception:
        hc_raw = "ERROR"
    hc_bin = "ACCEPTABLE" if hc_raw == "PASS" else "NEEDS_REVIEW"
    # LLM judge
    judge_prompt = f"Classify this PR diff as ACCEPTABLE or NEEDS_REVIEW. Say ONLY the word.\n\n```diff\n{diff_text[:4000]}\n```"
    judge = groq_call(judge_prompt)
    time.sleep(3.3)
    # Simulated CodeRabbit
    sim_prompt = f"Review this PR diff. Output ACCEPTABLE or NEEDS_REVIEW only.\n\n```diff\n{diff_text[:4000]}\n```"
    sim = groq_call(sim_prompt)
    time.sleep(3.3)
    # Label
    label = baseline.get(did, {}).get("label", "UNKNOWN")
    results.append({"id": did, "label": label, "hc": hc_bin, "judge": judge, "sim": sim})
    if (i + 1) % 10 == 0:
        print(
            f"  [{i + 1}/{len(sample)}] {time.time() - start:.0f}s, valid_judge={sum(1 for r in results if r['judge'])}"
        )


# Compute
def agree(arr1, arr2):
    pairs = [(a, b) for a, b in zip(arr1, arr2) if a and b]
    if not pairs:
        return 0, 0
    return sum(1 for a, b in pairs if a == b) / len(pairs), len(pairs)


hc = [r["hc"] for r in results]
judge = [r["judge"] for r in results]
sim = [r["sim"] for r in results]
lab = [r["label"] for r in results]

hcl, nh = agree(hc, lab)
jl, nj = agree(judge, lab)
sl, ns = agree(sim, lab)
hcj, n_hcj = agree(hc, judge)
hcsim, n_hcs = agree(hc, sim)
simj, n_simj = agree(sim, judge)

print("\n" + "=" * 60)
print("RESULTS")
print("=" * 60)
print(f"{'Comparison':35s} {'Agree':>8s} {'n':>4s}")
print("-" * 47)
print(f"{'HarnessCI vs Maintainer label':35s} {hcl:>7.1%} {nh:>4d}")
print(f"{'LLM Judge vs Maintainer label':35s} {jl:>7.1%} {nj:>4d}")
print(f"{'Sim CodeRabbit vs Maintainer':35s} {sl:>7.1%} {ns:>4d}")
print(f"{'HarnessCI vs LLM Judge (external)':35s} {hcj:>7.1%} {n_hcj:>4d}")
print(f"{'HarnessCI vs Sim CodeRabbit':35s} {hcsim:>7.1%} {n_hcs:>4d}")

# Precision/recall vs judge
hc_tp = sum(1 for r in results if r["hc"] == "NEEDS_REVIEW" and r["judge"] == "NEEDS_REVIEW")
hc_fp = sum(1 for r in results if r["hc"] == "NEEDS_REVIEW" and r["judge"] == "ACCEPTABLE")
hc_fn = sum(1 for r in results if r["hc"] == "ACCEPTABLE" and r["judge"] == "NEEDS_REVIEW")
hc_tn = sum(1 for r in results if r["hc"] == "ACCEPTABLE" and r["judge"] == "ACCEPTABLE")
hc_p = hc_tp / max(1, hc_tp + hc_fp)
hc_r = hc_tp / max(1, hc_tp + hc_fn)
hc_f = 2 * hc_p * hc_r / max(0.01, hc_p + hc_r)

sim_tp = sum(1 for r in results if r["sim"] == "NEEDS_REVIEW" and r["judge"] == "NEEDS_REVIEW")
sim_fp = sum(1 for r in results if r["sim"] == "NEEDS_REVIEW" and r["judge"] == "ACCEPTABLE")
sim_fn = sum(1 for r in results if r["sim"] == "ACCEPTABLE" and r["judge"] == "NEEDS_REVIEW")
sim_tn = sum(1 for r in results if r["sim"] == "ACCEPTABLE" and r["judge"] == "ACCEPTABLE")
sim_p = sim_tp / max(1, sim_tp + sim_fp)
sim_r = sim_tp / max(1, sim_tp + sim_fn)
sim_f = 2 * sim_p * sim_r / max(0.01, sim_p + sim_r)

print(f"\n{'Metric vs LLM Judge':35s} {'HarnessCI':>10s} {'SimCR':>10s}")
print("-" * 55)
print(f"{'Precision':35s} {hc_p:>9.1%} {sim_p:>9.1%}")
print(f"{'Recall':35s} {hc_r:>9.1%} {sim_r:>9.1%}")
print(f"{'F1 Score':35s} {hc_f:>9.1%} {sim_f:>9.1%}")
print(f"{'TP':35s} {hc_tp:>9d} {sim_tp:>9d}")
print(f"{'FP':35s} {hc_fp:>9d} {sim_fp:>9d}")
print(f"{'FN':35s} {hc_fn:>9d} {sim_fn:>9d}")
print(f"{'TN':35s} {hc_tn:>9d} {sim_tn:>9d}")

total = time.time() - start
print(f"\n{len(results)} cases in {total:.0f}s ({total / len(results):.1f}s/case)")

# Save
output = {
    "n": len(results),
    "elapsed_s": total,
    "comparisons": {
        "hc_vs_label": round(hcl, 4),
        "judge_vs_label": round(jl, 4),
        "sim_vs_label": round(sl, 4),
        "hc_vs_judge": round(hcj, 4),
        "hc_vs_sim": round(hcsim, 4),
        "sim_vs_judge": round(simj, 4),
    },
    "pr_vs_judge": {
        "harnessci": {"p": round(hc_p, 4), "r": round(hc_r, 4), "f1": round(hc_f, 4)},
        "sim_cr": {"p": round(sim_p, 4), "r": round(sim_r, 4), "f1": round(sim_f, 4)},
    },
    "results": results,
}
pathlib.Path(
    "datasets/agenticpr-bench-mini/layer3/results/external_validation_h2h.json"
).write_text(json.dumps(output, indent=2), encoding="utf-8")
print(f"\nSaved to external_validation_h2h.json")
for r in results:
    print(
        f"  {r['id'][:30]:30s} label={r['label']:15s} hc={r['hc']:15s} judge={str(r['judge']):15s} sim={str(r['sim']):15s}"
    )
