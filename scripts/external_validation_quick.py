"""Quick external validation: 10 diffs, 6s delays, proper retry."""

import json
import os
import pathlib
import random
import sys
import time

import requests

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from harnessci.audit import run_audit_from_diff_text

KEY = os.environ.get("GROQ_API_KEY", "")
if not KEY:
    KEY = ""  # must set via env
URL = "https://api.groq.com/openai/v1/chat/completions"


def classify(text):
    for _ in range(3):
        try:
            r = requests.post(
                URL,
                headers={"Authorization": f"Bearer {KEY}"},
                json={
                    "model": "llama-3.1-8b-instant",
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Classify this diff: ACCEPTABLE or NEEDS_REVIEW. Say ONLY the word.\n\n```diff\n{text}\n```",
                        }
                    ],
                    "temperature": 0.1,
                    "max_tokens": 30,
                },
                timeout=60,
            )
            if r.status_code == 200:
                t = r.json()["choices"][0]["message"]["content"].strip().upper()
                if "ACCEPTABLE" in t:
                    return "ACCEPTABLE"
                if "NEEDS_REVIEW" in t:
                    return "NEEDS_REVIEW"
                return None
            if r.status_code == 429:
                time.sleep(5)
                continue
            return None
        except Exception as e:
            print(f"  err: {e}")
            time.sleep(5)
    return None


# Load 10 diffs
diff_map = {}
for p in pathlib.Path("datasets/agenticpr-bench-mini/layer3/diffs").glob("**/*.diff"):
    parts = p.as_posix().split("/")
    if len(parts) >= 2 and "__" in parts[-2]:
        diff_map[f"{parts[-2].split('__')[0]}/{parts[-2].split('__')[1]}"] = p

random.seed(42)
sample = random.sample(list(diff_map.keys()), 10)
baseline = {
    r["dataset_id"]: r
    for r in json.loads(
        pathlib.Path(
            "datasets/agenticpr-bench-mini/layer3/results/multi_metric_composite.json"
        ).read_text()
    )["results"]
}

results = []
for i, did in enumerate(sample):
    dt = diff_map[did].read_text(encoding="utf-8", errors="replace")
    if len(dt) < 50:
        continue
    try:
        hc = run_audit_from_diff_text(dt).decision.value
    except:
        hc = "ERROR"
    hc_bin = "ACCEPTABLE" if hc == "PASS" else "NEEDS_REVIEW"
    label = baseline.get(did, {}).get("label", "UNKNOWN")
    print(f"[{i + 1}/10] {did[:25]:25s} hc={hc_bin}", end="")
    sys.stdout.flush()
    sim = classify(dt[:4000])
    print(f" sim={sim}", end="")
    sys.stdout.flush()
    time.sleep(6)
    judge = classify(dt[:4000])
    print(f" judge={judge} label={label}")
    time.sleep(6)
    results.append({"id": did, "label": label, "hc": hc_bin, "judge": judge, "sim": sim})

# Print results
print("\nResults:")
print(f"{'ID':25s} {'label':15s} {'HC':15s} {'Judge':15s} {'Sim':15s}")
print("-" * 85)
for r in results:
    print(
        f"{r['id'][:25]:25s} {r['label']:15s} {r['hc']:15s} {str(r['judge']):15s} {str(r['sim']):15s}"
    )
print(f"\nValid judge: {sum(1 for r in results if r['judge'])}/{len(results)}")
print(f"Valid sim: {sum(1 for r in results if r['sim'])}/{len(results)}")
