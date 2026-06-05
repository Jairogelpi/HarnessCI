"""Fetch Layer 3 pull-request diffs from the GitHub API.

Usage examples:

    GITHUB_TOKEN_1=... py scripts/fetch_layer3_diffs.py --shard 0 --total 3
    GITHUB_TOKEN_2=... py scripts/fetch_layer3_diffs.py --shard 1 --total 3
    GITHUB_TOKEN_3=... py scripts/fetch_layer3_diffs.py --shard 2 --total 3

The script is resumable: existing diff files are reused when --resume is on.
By default it fetches the first 500 sampled PRs, split evenly across shards.
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
MANIFEST_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/manifest.json"
OUTPUT_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3/diffs"
INDEX_PATH = ROOT / "datasets/agenticpr-bench-mini/layer3/diffs_index.jsonl"
DEFAULT_LIMIT = 500
DEFAULT_SLEEP_SECONDS = 0.1
USER_AGENT = "HarnessCI-Layer3-DiffFetcher/1.0"


def load_manifest(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def select_cases(
    cases: list[dict[str, Any]],
    shard: int,
    total: int,
    limit: int | None,
    start: int | None,
    end: int | None,
) -> list[dict[str, Any]]:
    sliced = cases[slice(start, end)]
    selected = sliced[:limit] if limit is not None else list(sliced)
    return [case for idx, case in enumerate(selected) if idx % total == shard]


def resolve_token(shard: int) -> tuple[str, str]:
    candidates = ["GITHUB_TOKEN", f"GITHUB_TOKEN_{shard + 1}", f"GITHUB_TOKEN_{shard}"]
    for name in candidates:
        token = os.environ.get(name, "").strip()
        if token:
            return token, name
    raise SystemExit("No GitHub token found. Set GITHUB_TOKEN or GITHUB_TOKEN_<shard+1>.")


def _api_url(repo: str, pr_number: int) -> str:
    return f"https://api.github.com/repos/{repo}/pulls/{pr_number}"


def _diff_download_url(repo: str, pr_number: int) -> str:
    return f"https://github.com/{repo}/pull/{pr_number}.diff"


def _download(url: str, headers: dict[str, str], timeout: int) -> str:
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def fetch_diff(repo: str, pr_number: int, token: str, timeout: int = 60) -> str:
    api_url = _api_url(repo, pr_number)
    api_headers = {
        "Accept": "application/vnd.github.v3.diff",
        "Authorization": f"Bearer {token}",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    fallback_headers = {
        "Accept": "text/plain, */*",
        "User-Agent": USER_AGENT,
    }

    backoff = 2.0
    last_exc: Exception | None = None
    for attempt in range(1, 6):
        try:
            return _download(api_url, api_headers, timeout)
        except HTTPError as exc:
            last_exc = exc
            if exc.code in {403, 429}:
                reset = exc.headers.get("X-RateLimit-Reset")
                remaining = exc.headers.get("X-RateLimit-Remaining")
                if reset and remaining == "0":
                    sleep_for = max(0, int(reset) - int(time.time()) + 5)
                    print(f"  Rate limit hit for {repo}#{pr_number}; sleeping {sleep_for}s")
                    time.sleep(sleep_for)
                    continue

                if attempt < 5:
                    print(f"  HTTP {exc.code} for {repo}#{pr_number}; retrying in {backoff:.0f}s")
                    time.sleep(backoff)
                    backoff *= 2
                    continue

            if exc.code in {404, 406}:
                try:
                    return _download(_diff_download_url(repo, pr_number), fallback_headers, timeout)
                except HTTPError as fallback_exc:
                    if fallback_exc.code == 404:
                        raise FileNotFoundError(
                            f"PR not found: {repo}#{pr_number}"
                        ) from fallback_exc
                    raise
            raise
        except URLError as exc:
            last_exc = exc
            if attempt < 5:
                print(f"  Network error for {repo}#{pr_number}; retrying in {backoff:.0f}s")
                time.sleep(backoff)
                backoff *= 2
                continue
            break

    raise RuntimeError(f"Failed to fetch diff after retries: {repo}#{pr_number}") from last_exc


def safe_name(value: str) -> str:
    return value.replace("/", "__").replace("\\", "__")


def diff_path_for(case: dict[str, Any]) -> Path:
    agent = safe_name(str(case.get("agent", "unknown")))
    dataset_id = safe_name(str(case.get("dataset_id", "unknown")))
    pr_number = case.get("pr_number", "unknown")
    return OUTPUT_DIR / agent / dataset_id / f"pr_{pr_number}.diff"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--index-path", type=Path, default=INDEX_PATH)
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--total", type=int, default=1)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS)
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    if args.total < 1:
        raise SystemExit("--total must be >= 1")
    if not 0 <= args.shard < args.total:
        raise SystemExit("--shard must be within [0, total)")

    resume = not args.no_resume
    cases = load_manifest(args.manifest)
    selected = select_cases(
        cases,
        args.shard,
        args.total,
        args.limit,
        args.start,
        args.end,
    )
    token, token_name = resolve_token(args.shard)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    args.index_path.parent.mkdir(parents=True, exist_ok=True)

    print(
        f"Loaded {len(cases)} Layer 3 cases; fetching {len(selected)} "
        f"on shard {args.shard}/{args.total - 1} using {token_name}"
    )

    records: list[dict[str, Any]] = []
    fetched = 0
    cached = 0
    failed = 0

    for idx, case in enumerate(selected, start=1):
        repo = str(case["repo"])
        pr_number = int(case["pr_number"])
        path = diff_path_for(case)
        path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "dataset_id": case.get("dataset_id"),
            "agent": case.get("agent"),
            "repo": repo,
            "pr_number": pr_number,
            "human_label": case.get("human_label"),
            "html_url": case.get("html_url"),
            "diff_path": str(path.relative_to(ROOT)),
            "source_url": _api_url(repo, pr_number),
        }

        if resume and path.exists():
            cached += 1
            record.update({"status": "cached", "bytes": path.stat().st_size})
            records.append(record)
            print(f"[{idx}/{len(selected)}] cached {repo}#{pr_number}")
            continue

        try:
            diff_text = fetch_diff(repo, pr_number, token, timeout=args.timeout)
            path.write_text(diff_text, encoding="utf-8")
            fetched += 1
            record.update({"status": "fetched", "bytes": len(diff_text.encode("utf-8"))})
            print(f"[{idx}/{len(selected)}] fetched {repo}#{pr_number}")
        except Exception as exc:  # pragma: no cover - network failure path
            failed += 1
            record.update({"status": "failed", "error": str(exc)})
            print(f"[{idx}/{len(selected)}] FAILED {repo}#{pr_number}: {exc}")
        records.append(record)

        if args.sleep > 0:
            time.sleep(args.sleep)

    with args.index_path.open("w", encoding="utf-8") as fh:
        for row in records:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    summary = {
        "selected": len(selected),
        "fetched": fetched,
        "cached": cached,
        "failed": failed,
        "output_dir": str(args.output_dir.relative_to(ROOT)),
        "index_path": str(args.index_path.relative_to(ROOT)),
        "shard": args.shard,
        "total_shards": args.total,
        "limit": args.limit,
    }
    (args.output_dir / f"summary_shard_{args.shard}.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\nSummary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
