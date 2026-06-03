"""Build AgenticPR-Bench-mini layer 1 from real GitHub bot PRs.

Layer 1 uses the public AIDev dataset as the candidate source and GitHub's
maintainer decision as independent ground truth:

- merged_at present      -> ACCEPTABLE
- closed without merge   -> NEEDS_REVIEW

The script fetches live PR metadata and diffs from GitHub. Diffs are stored
locally under datasets/agenticpr-bench-mini/raw/diffs/ and should be treated as
rebuildable raw material, not hand-authored project code.

Usage:
    GITHUB_TOKEN=... py scripts/build_agenticpr_layer1.py

The token is optional but strongly recommended because unauthenticated GitHub API
calls are limited to 60 requests/hour.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "datasets" / "agenticpr-bench-mini"
RAW_DIR = DATASET_DIR / "raw"
DIFF_DIR = RAW_DIR / "diffs"
CANDIDATES_CSV = RAW_DIR / "sample_candidates.csv"
MANIFEST_JSONL = RAW_DIR / "layer1_real_github_prs.jsonl"
SUMMARY_JSON = RAW_DIR / "layer1_summary.json"

AGENTS = ["OpenAI_Codex", "Copilot", "Devin", "Cursor", "Claude_Code"]
TARGET_PER_AGENT_PER_LABEL = 8
REQUEST_SLEEP_SECONDS = 0.2
MAX_CANDIDATE_ATTEMPTS = 400


@dataclass
class Layer1Record:
    dataset_id: str
    source: str
    agent: str
    owner: str
    repo: str
    number: int
    title: str
    body_excerpt: str
    body_sha256: str | None
    body_chars: int
    html_url: str
    api_url: str
    human_label: str
    label_source: str
    merged_at: str | None
    closed_at: str | None
    created_at: str | None
    live_state: str
    live_merged: bool
    changed_files: int | None
    additions: int | None
    deletions: int | None
    commits: int | None
    diff_path: str
    diff_sha256: str
    diff_bytes: int
    fetch_status: str


def main() -> int:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    DIFF_DIR.mkdir(parents=True, exist_ok=True)

    print("[layer1] Loading AIDev all_pull_request.parquet from Hugging Face...")
    all_prs = pd.read_parquet("hf://datasets/hao-li/AIDev/all_pull_request.parquet")

    candidates = build_candidates(all_prs)
    candidates.to_csv(CANDIDATES_CSV, index=False)
    print(f"[layer1] Candidate pool saved: {CANDIDATES_CSV} ({len(candidates)} rows)")

    records: list[Layer1Record] = []
    failures: list[dict[str, str]] = []
    counts = {(agent, label): 0 for agent in AGENTS for label in ["ACCEPTABLE", "NEEDS_REVIEW"]}

    for _, row in candidates.iterrows():
        label = str(row["human_label"])
        agent = str(row["agent"])
        if counts.get((agent, label), 0) >= TARGET_PER_AGENT_PER_LABEL:
            continue
        if len(records) >= TARGET_PER_AGENT_PER_LABEL * 2 * len(AGENTS):
            break

        try:
            record = fetch_record(row, token=token)
        except Exception as exc:  # noqa: BLE001 - dataset builder should continue
            failures.append({"html_url": str(row.get("html_url", "")), "error": str(exc)})
            continue

        records.append(record)
        counts[(agent, label)] += 1
        print(
            f"[layer1] OK {len(records):02d}: {agent:12s} {label:12s} "
            f"{record.owner}/{record.repo}#{record.number} files={record.changed_files}"
        )
        time.sleep(REQUEST_SLEEP_SECONDS)

    write_jsonl(MANIFEST_JSONL, records)
    write_summary(records, failures, counts)

    print()
    print(f"[layer1] Manifest: {MANIFEST_JSONL}")
    print(f"[layer1] Diffs:    {DIFF_DIR}")
    print(f"[layer1] Summary:  {SUMMARY_JSON}")
    print(f"[layer1] Records:  {len(records)}")
    print(f"[layer1] Failures: {len(failures)}")

    if len(records) < TARGET_PER_AGENT_PER_LABEL * 2 * len(AGENTS):
        print("[layer1] WARNING: target sample size not reached; inspect summary failures.")
        return 1
    return 0


def build_candidates(all_prs: pd.DataFrame) -> pd.DataFrame:
    """Build a shuffled, stratified candidate pool from AIDev."""
    merged = all_prs[all_prs["merged_at"].notna()].copy()
    closed_no_merge = all_prs[(all_prs["state"] == "closed") & (all_prs["merged_at"].isna())].copy()

    frames: list[pd.DataFrame] = []
    rng = random.Random(42)
    for agent in AGENTS:
        for source_df, label in [(merged, "ACCEPTABLE"), (closed_no_merge, "NEEDS_REVIEW")]:
            agent_df = source_df[source_df["agent"] == agent].copy()
            # Oversample because many AIDev repos disappeared after collection.
            n = min(MAX_CANDIDATE_ATTEMPTS, len(agent_df))
            sample = agent_df.sample(n=n, random_state=rng.randint(1, 10_000_000)).copy()
            sample["human_label"] = label
            frames.append(sample)

    candidates = pd.concat(frames, ignore_index=True)
    candidates = candidates.sample(frac=1.0, random_state=42).reset_index(drop=True)
    return candidates[
        [
            "id",
            "number",
            "title",
            "agent",
            "repo_url",
            "html_url",
            "state",
            "merged_at",
            "created_at",
            "closed_at",
            "human_label",
        ]
    ]


def fetch_record(row: pd.Series, token: str | None) -> Layer1Record:
    owner, repo, number = parse_pr_url(str(row["html_url"]))
    api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    metadata = github_json(api_url, token=token)

    diff_url = metadata.get("diff_url") or f"https://github.com/{owner}/{repo}/pull/{number}.diff"
    diff_text = github_text(diff_url, token=token, accept="application/vnd.github.diff")
    if not diff_text.strip().startswith("diff --git"):
        raise RuntimeError("Fetched diff does not look like a git diff")

    dataset_id = stable_id(owner, repo, number)
    diff_path = DIFF_DIR / f"{dataset_id}.diff"
    diff_path.write_text(diff_text, encoding="utf-8", newline="\n")

    diff_bytes = diff_path.stat().st_size
    diff_sha256 = hashlib.sha256(diff_path.read_bytes()).hexdigest()

    return Layer1Record(
        dataset_id=dataset_id,
        source="AIDev + GitHub API",
        agent=str(row["agent"]),
        owner=owner,
        repo=repo,
        number=int(number),
        title=str(row.get("title") or metadata.get("title") or ""),
        body_excerpt=body_excerpt(metadata.get("body") or row.get("body") or ""),
        body_sha256=text_sha256(metadata.get("body") or row.get("body") or ""),
        body_chars=len(str(metadata.get("body") or row.get("body") or "")),
        html_url=str(row["html_url"]),
        api_url=api_url,
        human_label=str(row["human_label"]),
        label_source="GitHub maintainer merge decision: merged_at present vs closed without merge",
        merged_at=none_if_nan(row.get("merged_at")),
        closed_at=none_if_nan(row.get("closed_at")),
        created_at=none_if_nan(row.get("created_at")),
        live_state=str(metadata.get("state", "")),
        live_merged=bool(metadata.get("merged", False)),
        changed_files=metadata.get("changed_files"),
        additions=metadata.get("additions"),
        deletions=metadata.get("deletions"),
        commits=metadata.get("commits"),
        diff_path=str(diff_path.relative_to(ROOT)).replace("\\", "/"),
        diff_sha256=diff_sha256,
        diff_bytes=diff_bytes,
        fetch_status="ok",
    )


def github_json(url: str, token: str | None) -> dict[str, Any]:
    body = github_bytes(url, token=token, accept="application/vnd.github+json")
    return json.loads(body.decode("utf-8"))


def github_text(url: str, token: str | None, accept: str) -> str:
    return github_bytes(url, token=token, accept=accept).decode("utf-8", errors="replace")


def github_bytes(url: str, token: str | None, accept: str) -> bytes:
    headers = {
        "Accept": accept,
        "User-Agent": "HarnessCI-AgenticPR-Bench-mini",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"GitHub HTTP {exc.code} for {url}: {detail}") from exc


def parse_pr_url(url: str) -> tuple[str, str, int]:
    match = re.match(r"https://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    if not match:
        raise ValueError(f"Invalid PR URL: {url}")
    owner, repo, number = match.groups()
    return owner, repo, int(number)


def body_excerpt(text: Any, limit: int = 500) -> str:
    """Return a bounded, lightly redacted PR body excerpt."""
    value = str(text or "").strip()
    value = re.sub(r"gh[pousr]_[A-Za-z0-9_]{20,}", "<redacted-github-token>", value)
    value = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]{16,}", "Bearer <redacted-token>", value)
    return value[:limit]


def text_sha256(text: Any) -> str | None:
    value = str(text or "")
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def stable_id(owner: str, repo: str, number: int) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", f"{owner}__{repo}__pull_{number}")
    return safe[:180]


def none_if_nan(value: Any) -> str | None:
    if value is None:
        return None
    if pd.isna(value):
        return None
    return str(value)


def write_jsonl(path: Path, records: list[Layer1Record]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for record in records:
            fh.write(json.dumps(asdict(record), ensure_ascii=False, sort_keys=True) + "\n")


def write_summary(
    records: list[Layer1Record],
    failures: list[dict[str, str]],
    counts: dict[tuple[str, str], int],
) -> None:
    summary = {
        "dataset": "AgenticPR-Bench-mini",
        "layer": "layer1_real_github_bot_prs",
        "records": len(records),
        "label_rule": {
            "ACCEPTABLE": "merged_at present in AIDev",
            "NEEDS_REVIEW": "closed without merge in AIDev",
        },
        "counts_by_agent_label": {
            f"{agent}:{label}": count for (agent, label), count in counts.items()
        },
        "failures": failures,
        "limitations": [
            "Maintainer merge decision is an imperfect proxy for code correctness.",
            "Public PRs may disappear after AIDev collection; missing PRs are excluded, "
            "not relabeled.",
            "Layer 1 has no agent telemetry and often no explicit task spec.",
            "Diffs are fetched from live GitHub and may change if repositories are rewritten.",
        ],
    }
    SUMMARY_JSON.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
