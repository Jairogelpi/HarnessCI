"""Stratified diff fetcher for Layer 3 balanced audit.

Fetches 1000 diffs: 5 agents x 2 labels x 100 PRs, for a balanced
sample that avoids the single-agent bias of earlier runs.

Usage:
    set GITHUB_TOKEN=...
    py scripts/fetch_layer3_diffs_stratified.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/manifest.json"
OUTPUT_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3/diffs"
INDEX_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/diffs_index_stratified.jsonl"

# Stratified plan: 5 agents x 2 labels x 100 PRs = 1000 diffs
STRATIFIED_PLAN = [
    # agent, label, start, end (manifest indices, 0-based)
    ("Claude_Code", "ACCEPTABLE", 0, 100),
    ("Claude_Code", "NEEDS_REVIEW", 588, 688),
    ("Copilot", "ACCEPTABLE", 1338, 1438),
    ("Copilot", "NEEDS_REVIEW", 2088, 2188),
    ("Cursor", "ACCEPTABLE", 2838, 2938),
    ("Cursor", "NEEDS_REVIEW", 3588, 3688),
    ("Devin", "ACCEPTABLE", 4338, 4438),
    ("Devin", "NEEDS_REVIEW", 5088, 5188),
    ("OpenAI_Codex", "ACCEPTABLE", 5838, 5938),
    ("OpenAI_Codex", "NEEDS_REVIEW", 6588, 6688),
]

USER_AGENT = "HarnessCI-Layer3-DiffFetcher/1.0"


def get_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise SystemExit("GITHUB_TOKEN environment variable not set.")
    return token


def load_manifest() -> list[dict]:
    with MANIFEST_PATH.open(encoding="utf-8") as f:
        return json.load(f)


def safe_name(value: str) -> str:
    return value.replace("/", "__").replace("\\", "__")


def diff_path_for(agent: str, dataset_id: str, pr_number: int) -> Path:
    return OUTPUT_DIR / safe_name(agent) / safe_name(dataset_id) / f"pr_{pr_number}.diff"


def fetch_diff(repo: str, pr_number: int, token: str, timeout: int = 60) -> str:
    """Fetch diff via GitHub API v3 diff media type."""
    api_url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }

    backoff = 1.0
    for attempt in range(1, 8):
        try:
            req = urllib.request.Request(api_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 429}:
                reset = exc.headers.get("X-RateLimit-Reset")
                remaining = exc.headers.get("X-RateLimit-Remaining")
                if remaining == "0" and reset:
                    sleep_for = max(0, int(reset) - int(time.time()) + 5)
                    print(f"  [!] Rate limited - sleeping {sleep_for}s")
                    time.sleep(sleep_for)
                    continue
                if attempt < 7:
                    print(f"  HTTP {exc.code}, retry in {backoff:.0f}s")
                    time.sleep(backoff)
                    backoff *= 1.5
                    continue
            raise
        except urllib.error.URLError:
            if attempt < 7:
                print(f"  Network error, retry in {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 1.5
                continue
            raise
    msg = f"Failed after retries: {repo}#{pr_number}"
    raise RuntimeError(msg)


def build_fetched_index() -> dict[str, dict]:
    """Scan diff folders and JSONL indexes to find already-fetched diffs."""
    index: dict[str, dict] = {}
    # Load from existing JSONL indexes
    for jl_path in [
        INDEX_PATH,
        ROOT / "datasets/agenticpr-bench-mini/layer3/diffs_index.jsonl",
    ]:
        if jl_path.exists():
            with jl_path.open(encoding="utf-8") as f:
                for line in f:
                    d = json.loads(line)
                    if d.get("status") == "fetched":
                        index[d["dataset_id"]] = d
    # Scan folders for any diffs not yet in index
    if not OUTPUT_DIR.exists():
        return index
    for agent_dir in OUTPUT_DIR.iterdir():
        if not agent_dir.is_dir():
            continue
        for case_dir in agent_dir.iterdir():
            if not case_dir.is_dir():
                continue
            diff_files = list(case_dir.glob("pr_*.diff"))
            if not diff_files:
                continue
            diff_file = diff_files[0]
            pr_number = int(diff_file.stem.split("_", 1)[1])
            agent = agent_dir.name.replace("__", "/")
            dataset_id = case_dir.name.replace("__", "/")
            if dataset_id not in index:
                index[dataset_id] = {
                    "dataset_id": dataset_id,
                    "agent": agent,
                    "pr_number": pr_number,
                    "diff_path": str(diff_file.relative_to(ROOT)),
                    "status": "fetched",
                    "bytes": diff_file.stat().st_size,
                }
    return index


def run() -> int:
    token = get_token()
    manifest = load_manifest()
    existing = build_fetched_index()

    print(f"Loaded {len(existing)} already-fetched diffs from disk.")
    records: list[dict] = []
    total_groups = len(STRATIFIED_PLAN)

    for group_idx, (agent, label, start, end) in enumerate(STRATIFIED_PLAN, start=1):
        cases = manifest[start:end]
        group_label = f"{agent}/{label}"
        idx_range = f"{start}:{end}"
        print(
            f"\n[Group {group_idx}/{total_groups}] {group_label} - "
            f"indices {idx_range} - {len(cases)} PRs"
        )

        group_fetched = 0
        group_cached = 0
        group_failed = 0

        for idx, case in enumerate(cases, start=1):
            dataset_id = case["dataset_id"]
            repo = case["repo"]
            pr_number = int(case["pr_number"])
            path = diff_path_for(agent, dataset_id, pr_number)

            # Resume: skip if already fetched
            if dataset_id in existing and existing[dataset_id].get("status") == "fetched":
                group_cached += 1
                print(f"  [{idx}/{len(cases)}] cached {dataset_id}")
                continue

            record: dict = {
                "dataset_id": dataset_id,
                "agent": agent,
                "repo": repo,
                "pr_number": pr_number,
                "human_label": label,
                "html_url": case.get("html_url"),
                "diff_path": str(path.relative_to(ROOT)),
                "source_url": f"https://api.github.com/repos/{repo}/pulls/{pr_number}",
            }

            try:
                diff_text = fetch_diff(repo, pr_number, token)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(diff_text, encoding="utf-8")
                group_fetched += 1
                record["status"] = "fetched"
                record["bytes"] = len(diff_text.encode("utf-8"))
                print(f"  [{idx}/{len(cases)}] fetched {dataset_id}")
            except Exception as exc:  # pragma: no cover
                group_failed += 1
                record["status"] = "failed"
                record["error"] = str(exc)
                print(f"  [{idx}/{len(cases)}] FAILED {dataset_id}: {exc}")

            records.append(record)
            existing[dataset_id] = record

            if group_fetched > 0:
                time.sleep(0.5)

        print(
            f"  -> Group {group_idx}: fetched={group_fetched}, "
            f"cached={group_cached}, failed={group_failed}"
        )

    # Write combined index
    INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    with INDEX_PATH.open("w", encoding="utf-8") as f:
        for row in records:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    # Summary
    total_fetched = sum(1 for r in records if r.get("status") == "fetched")
    total_cached = sum(1 for r in records if r.get("status") == "cached")
    total_failed = sum(1 for r in records if r.get("status") == "failed")

    summary_path = OUTPUT_DIR.parent / "stratified_fetch_summary.json"
    summary = {
        "total_groups": total_groups,
        "planned": 1000,
        "fetched": total_fetched,
        "cached": total_cached,
        "failed": total_failed,
        "coverage": f"{total_fetched + total_cached}/1000",
    }
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(
        f"\n[OK] Stratified fetch: {total_fetched} fetched, "
        f"{total_cached} cached, {total_failed} failed"
    )
    print(f"   Index: {INDEX_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run())
