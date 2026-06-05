#!/usr/bin/env python
"""Fetch PR diffs for the zero-bias 100K sample from GitHub API.

Usage:
    GITHUB_TOKEN=...  py scripts/fetch_zero_bias_diffs.py --shard 0 --total 8
    GITHUB_TOKEN_1=... GITHUB_TOKEN_2=... py scripts/fetch_zero_bias_diffs.py --parallel

Architecture:
  - 8 shards by default (each ~12,500 PRs)
  - Resumable: existing diff files are skipped
  - Rate-limit aware: reads X-RateLimit-Reset header and sleeps
  - Index: appends to diffs_index_zero_bias.jsonl

Output:
  layer3/diffs_zero_bias/<agent>/<pr_id>/pr_<number>.diff
  layer3/diffs_index_zero_bias.jsonl
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
LAYER3_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3"
MANIFEST_PATH = LAYER3_DIR / "manifest_zero_bias.json"
OUTPUT_DIR = LAYER3_DIR / "diffs_zero_bias"
INDEX_PATH = LAYER3_DIR / "diffs_index_zero_bias.jsonl"
DEFAULT_SLEEP = 0.05  # 50ms between requests
USER_AGENT = "HarnessCI-ZeroBias-DiffFetcher/1.0"


def load_manifest() -> list[dict[str, Any]]:
    with MANIFEST_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def select_shard(
    cases: list[dict[str, Any]],
    shard: int,
    total: int,
) -> list[dict[str, Any]]:
    return [c for i, c in enumerate(cases) if i % total == shard]


def resolve_token(shard: int) -> tuple[str, str]:
    for name in [f"GITHUB_TOKEN_{shard}", "GITHUB_TOKEN"]:
        tok = os.environ.get(name, "").strip()
        if tok:
            return tok, name
    raise SystemExit(f"No GitHub token found for shard {shard}. Set GITHUB_TOKEN.")


def fetch_diff(
    repo: str,
    pr_number: int,
    token: str,
    timeout: int = 30,
) -> str:
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
    headers = {
        "Accept": "application/vnd.github.v3.diff",
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    backoff = 2.0
    last: Exception | None = None

    for attempt in range(1, 6):
        try:
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as resp:
                return resp.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            last = exc
            if exc.code in (403, 429):
                reset = exc.headers.get("X-RateLimit-Reset", "")
                rem = exc.headers.get("X-RateLimit-Remaining", "0")
                if rem == "0" and reset:
                    wait = max(1, int(reset) - int(time.time()) + 5)
                    print(f"  [RATELIMIT] sleeping {wait}s...", flush=True)
                    time.sleep(wait)
                    continue
                if attempt < 5:
                    print(f"  HTTP {exc.code}, retry in {backoff:.0f}s", flush=True)
                    time.sleep(backoff)
                    backoff *= 2
                    continue
            if exc.code in (404, 410):
                raise FileNotFoundError(f"PR not found: {repo}#{pr_number}") from exc
            raise
        except URLError as exc:
            last = exc
            if attempt < 5:
                print(f"  Network error, retry in {backoff:.0f}s", flush=True)
                time.sleep(backoff)
                backoff *= 2
                continue
            break
    raise RuntimeError(f"Failed after 5 retries: {repo}#{pr_number}") from last


def safe_name(v: str) -> str:
    return v.replace("/", "__").replace("\\", "__")


def diff_path(case: dict[str, Any]) -> Path:
    agent = safe_name(str(case.get("agent", "unknown")))
    ds_id = safe_name(str(case.get("dataset_id", "unknown")))
    prn = case.get("pr_number", "unknown")
    return OUTPUT_DIR / agent / ds_id / f"pr_{prn}.diff"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--total", type=int, default=8)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP)
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    if not 0 <= args.shard < args.total:
        raise SystemExit(f"--shard {args.shard} must be in [0, {args.total})")

    manifest = load_manifest()
    selected = select_shard(manifest, args.shard, args.total)
    token, token_name = resolve_token(args.shard)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Manifest: {len(manifest):,} PRs | Shard {args.shard}/{args.total-1} = "
          f"{len(selected):,} PRs | Token: {token_name}", flush=True)

    # Resume: build existing set from index
    cached: set[str] = set()
    if not args.no_resume and INDEX_PATH.exists():
        with INDEX_PATH.open(encoding="utf-8") as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                    if rec.get("shard") == args.shard:
                        cached.add(rec.get("dataset_id", ""))
                except Exception:
                    pass

    records: list[dict[str, Any]] = []
    fetched = cached_cnt = 0
    failed = 0
    resume = not args.no_resume

    for idx, case in enumerate(selected, 1):
        ds_id = str(case["dataset_id"])
        repo = str(case["repo"])
        prn = int(case["pr_number"])
        path = diff_path(case)
        path.parent.mkdir(parents=True, exist_ok=True)

        rec: dict[str, Any] = {
            "dataset_id": ds_id,
            "agent": case.get("agent"),
            "repo": repo,
            "pr_number": prn,
            "human_label": case.get("human_label"),
            "html_url": case.get("html_url"),
            "diff_path": str(path.relative_to(ROOT)),
            "source_url": f"https://api.github.com/repos/{repo}/pulls/{prn}",
            "shard": args.shard,
        }

        if resume and path.exists():
            cached_cnt += 1
            rec.update({"status": "cached", "bytes": path.stat().st_size})
            records.append(rec)
            if idx % 1000 == 0:
                print(f"  [{idx:,}/{len(selected):,}] cached {ds_id}", flush=True)
            continue

        try:
            diff = fetch_diff(repo, prn, token, timeout=args.timeout)
            path.write_text(diff, encoding="utf-8")
            fetched += 1
            rec.update({"status": "fetched", "bytes": len(diff.encode("utf-8"))})
        except Exception as exc:
            failed += 1
            rec.update({"status": "failed", "error": str(exc)})

        records.append(rec)

        if idx % 1000 == 0:
            pct = idx / len(selected) * 100
            print(f"  [{idx:,}/{len(selected):,}] {pct:.0f}%  "
                  f"fetched={fetched}  cached={cached_cnt}  failed={failed}",
                  flush=True)

        if args.sleep > 0:
            time.sleep(args.sleep)

    # Append to index
    with INDEX_PATH.open("a", encoding="utf-8") as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "shard": args.shard,
        "total_shards": args.total,
        "selected": len(selected),
        "fetched": fetched,
        "cached": cached_cnt,
        "failed": failed,
    }

    out = OUTPUT_DIR / f"summary_shard_{args.shard}.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\nShard {args.shard} done: {fetched} fetched, {cached_cnt} cached, "
          f"{failed} failed  → {out}", flush=True)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())