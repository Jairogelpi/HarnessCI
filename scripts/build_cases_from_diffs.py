"""Build cases list from fetched diffs."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(".")
LAYER3_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3"
DIFF_DIR = LAYER3_DIR / "diffs_zero_bias"
MANIFEST_PATH = LAYER3_DIR / "manifest_zero_bias.json"

# Build manifest lookup (UTF-8)
manifest: dict[str, dict] = {}
with MANIFEST_PATH.open(encoding="utf-8") as fh:
    for pr in json.load(fh):
        manifest[pr["dataset_id"]] = pr

# Reverse map: safe_name(dataset_id) -> dataset_id
def safe(s: str) -> str:
    return s.replace("/", "__").replace("\\", "__")

safe_to_orig: dict[str, str] = {}
for ds_id in manifest:
    safe_to_orig[safe(ds_id)] = ds_id

print(f"Manifest: {len(manifest)} entries")
print(f"Safe map: {len(safe_to_orig)} entries")

# List dirs
agent_dirs = list(DIFF_DIR.iterdir())
print(f"Agent dirs: {[d.name for d in agent_dirs]}")

# Find diff files
cases = []
unmatched = []
for diff_file in DIFF_DIR.rglob("*.diff"):
    rel = str(diff_file.relative_to(ROOT))
    parts = rel.split("/")
    # path: .../diffs_zero_bias/<safe_agent>/<safe_ds_id>/pr_N.diff
    if len(parts) < 4:
        continue
    safe_ds = parts[-3]
    orig_ds = safe_to_orig.get(safe_ds, "")
    if not orig_ds or orig_ds not in manifest:
        unmatched.append((safe_ds, rel))
        continue

    rec = manifest[orig_ds]
    if diff_file.stat().st_size < 50:
        continue

    cases.append({
        "dataset_id": orig_ds,
        "agent": rec["agent"],
        "repo": rec["repo"],
        "pr_number": rec["pr_number"],
        "human_label": rec["human_label"],
        "diff_path": rel,
        "diff_bytes": diff_file.stat().st_size,
    })

print(f"\nMatched: {len(cases)}, Unmatched: {len(unmatched)}")
if unmatched[:3]:
    print(f"Unmatched examples: {unmatched[:3]}")

for agent in ["Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"]:
    cnt = sum(1 for c in cases if c["agent"] == agent)
    print(f"  {agent}: {cnt}")

with (LAYER3_DIR / "cases_with_diffs.json").open("w", encoding="utf-8") as fh:
    json.dump(cases, fh)
print("Saved cases_with_diffs.json")