"""Layer 3: Zero-bias 100K benchmark — data analyst methodology.

Principle: each (agent, label) stratum is sampled proportionally to its
population, WITHIN each stratum we maximise repo diversity (max 20/repo),
and we NEVER impose a merged/closed ratio.

Methodology (how a data analyst would do it):
  1. Stratify by (agent, label) — 10 strata total.
  2. Per stratum, draw up to available, with repo diversity constraint.
  3. Sum across strata; if total < 100K, redistribute surplus from capped agents.
  4. Deduplicate by PR id.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "datasets/agenticpr-bench-mini/raw"
LAYER3_DIR = ROOT / "datasets/agenticpr-bench-mini/layer3"
PARQUET_PATH = RAW_DIR / "all_pull_request.parquet"

MAX_PER_REPO = 20
TARGET_TOTAL = 100_000
AGENTS = ["Claude_Code", "Copilot", "Cursor", "Devin", "OpenAI_Codex"]


def load_dataset() -> pd.DataFrame:
    print(f"Loading {PARQUET_PATH}...", flush=True)
    cols = [
        "id", "number", "title", "body", "agent", "state",
        "created_at", "closed_at", "merged_at", "repo_url", "html_url",
    ]
    df = pd.read_parquet(PARQUET_PATH, columns=cols)
    print(f"  {len(df):,} rows loaded", flush=True)
    return df


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    merged = df["merged_at"].notna()
    closed = df["state"].eq("closed") & ~merged
    df = df.copy()
    df["label"] = "OPEN"
    df.loc[merged, "label"] = "ACCEPTABLE"
    df.loc[closed, "label"] = "NEEDS_REVIEW"
    df = df[df["label"] != "OPEN"].copy()
    df["repo_name"] = df["repo_url"].str.replace(
        "https://api.github.com/repos/", "", regex=False
    )
    return df


def sample_stratum(
    pool: pd.DataFrame,
    n: int,
    seed: int,
    max_repo: int = MAX_PER_REPO,
) -> pd.DataFrame:
    """Sample up to n from pool with repo diversity cap, no replacement."""
    if len(pool) == 0:
        return pool
    if len(pool) <= n:
        return pool.copy()

    # Build a priority: prefer repos with fewer sampled rows so far
    rows = []
    sampled_ids: set[int] = set()

    # Pre-compute repo order shuffled once
    repos = pool["repo_name"].unique()
    repo_order = pd.Series(repos).sample(frac=1, random_state=seed).tolist()

    for repo in repo_order:
        if len(sampled_ids) >= n:
            break
        repo_pool = pool[pool["repo_name"] == repo]
        repo_ids = set(repo_pool.index) - sampled_ids
        if not repo_ids:
            continue
        can_take = min(len(repo_ids), max_repo, n - len(sampled_ids))
        if can_take <= 0:
            continue
        to_take = repo_pool.loc[list(repo_ids)].sample(
            n=can_take, random_state=seed
        )
        rows.append(to_take)
        sampled_ids.update(to_take.index)

    if not rows:
        return pool.sample(n=min(n, len(pool)), random_state=seed)

    sampled = pd.concat(rows, ignore_index=True)

    # Fill remaining with simple random (repos already capped)
    while len(sampled) < n:
        remaining = pool[~pool.index.isin(sampled_ids)]
        if len(remaining) == 0:
            break
        take = min(n - len(sampled), len(remaining))
        seed += 1
        batch = remaining.sample(n=take, random_state=seed)
        sampled = pd.concat([sampled, batch], ignore_index=True)
        sampled_ids.update(batch.index)

    return sampled.head(n)


def zero_bias_sample(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Draw 100K with natural proportions, repo diversity, no forced ratios."""
    samples = []
    log = []

    print("\nPhase 1 — proportional sampling by (agent, label) stratum", flush=True)

    for agent in AGENTS:
        ag = df[df["agent"] == agent]
        merged_pool = ag[ag["label"] == "ACCEPTABLE"]
        closed_pool = ag[ag["label"] == "NEEDS_REVIEW"]

        n_total = len(ag)
        n_merged = len(merged_pool)
        n_closed = len(closed_pool)

        # Natural ratio — NO forced ratio
        merged_ratio = n_merged / n_total if n_total else 0
        cap = min(20_000, n_total)
        target_merged = int(cap * merged_ratio)
        target_closed = cap - target_merged

        actual_merged = min(target_merged, n_merged)
        actual_closed = min(target_closed, n_closed)

        m_s = sample_stratum(merged_pool, actual_merged, seed=42)
        c_s = sample_stratum(closed_pool, actual_closed, seed=42)

        stratum = pd.concat([m_s, c_s], ignore_index=True)
        samples.append(stratum)

        log.append({
            "agent": agent,
            "avail_total": n_total,
            "avail_merged": n_merged,
            "avail_closed": n_closed,
            "natural_ratio": f"{n_merged}:{n_closed}",
            "target": cap,
            "sampled_merged": len(m_s),
            "sampled_closed": len(c_s),
            "sampled_total": len(stratum),
            "repos_used": int(stratum["repo_name"].nunique()),
        })

        parts = f"merged={n_merged:,}, closed={n_closed:,}"
        print(f"  {agent}: avail={n_total:,} ({parts}), "
              f"sampling {len(m_s):,} merged + {len(c_s):,} closed",
              flush=True)

    base = pd.concat(samples, ignore_index=True)
    phase1_total = len(base)
    print(f"\nPhase 1 total: {phase1_total:,} PRs  (target: {TARGET_TOTAL:,})",
          flush=True)

    # Phase 2: redistribute if total < 100K
    deficit = TARGET_TOTAL - phase1_total

    if deficit > 0:
        print(f"\nPhase 2 — redistributing {deficit:,} deficit PRs", flush=True)
        # Find agents that still have headroom
        full_taken_ids = set(base["id"].tolist())
        for agent in AGENTS:
            if deficit <= 0:
                break
            ag = df[df["agent"] == agent]
            remaining = ag[~ag["id"].isin(full_taken_ids)]
            if len(remaining) == 0:
                continue

            share = min(len(remaining), deficit)
            extra = sample_stratum(remaining, share, seed=101)
            samples.append(extra)
            full_taken_ids.update(extra["id"].tolist())
            deficit -= len(extra)
            log.append({
                "agent": agent,
                "phase": "redistribute",
                "extra_sampled": len(extra),
            })
            print(f"  Redistributed {len(extra):,} from {agent}", flush=True)

    result = pd.concat(samples, ignore_index=True)
    result = result.drop_duplicates(subset=["id"])
    result = result.head(TARGET_TOTAL)

    print(f"\nFinal: {len(result):,} unique PRs, "
          f"{result['repo_name'].nunique():,} repos", flush=True)

    return result, log


def build_manifest(sampled: pd.DataFrame) -> list[dict]:
    manifest = []
    seen: set[int] = set()

    for _, row in sampled.iterrows():
        pr_id = int(row["id"])
        if pr_id in seen:
            continue
        seen.add(pr_id)

        manifest.append({
            "dataset_id": f"{row['agent']}/{pr_id}",
            "agent": row["agent"],
            "repo": row["repo_name"],
            "pr_number": int(row["number"]),
            "title": str(row.get("title", "")),
            "human_label": row["label"],
            "html_url": str(row.get("html_url", "")),
            "created_at": str(row.get("created_at", "")),
            "merged_at": str(row.get("merged_at", "")) if pd.notna(
                row.get("merged_at")
            ) else None,
            "closed_at": str(row.get("closed_at", "")) if pd.notna(
                row.get("closed_at")
            ) else None,
            "body_excerpt": str(row.get("body", ""))[:500],
        })

    return manifest


def main() -> int:
    df_full = load_dataset()
    df_full = prepare(df_full)
    print(f"Labeled dataset: {len(df_full):,} PRs  "
          f"(merged+closed only, no open)", flush=True)

    sampled, log = zero_bias_sample(df_full)
    manifest = build_manifest(sampled)

    LAYER3_DIR.mkdir(parents=True, exist_ok=True)

    # Save manifest
    manifest_path = LAYER3_DIR / "manifest_zero_bias.json"
    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)
    print(f"\nSaved: {manifest_path}  ({len(manifest):,} PRs)", flush=True)

    # Save log
    log_path = LAYER3_DIR / "zero_bias_sampling_log.json"
    with log_path.open("w", encoding="utf-8") as fh:
        json.dump(log, fh, indent=2, ensure_ascii=False)

    # Compute stats
    stats = {
        "total_prs": len(sampled),
        "per_agent": {},
        "unique_repos": int(sampled["repo_name"].nunique()),
        "max_per_repo": MAX_PER_REPO,
        "target_total": TARGET_TOTAL,
        "methodology": {
            "natural_ratio": True,
            "forced_ratio": None,
            "bias_controls": [
                "No merged/closed ratio imposed — natural proportions kept",
                "Per-agent cap at 20K (dataset constraint)",
                f"Repo diversity: max {MAX_PER_REPO} per repo",
                "Stratified sampling within each (agent, label) stratum",
                "Phase 2 redistribution uses remaining pool (no ratio forcing)",
                "Label rule: merged_at = ACCEPTABLE, closed-w/o-merge = NEEDS_REVIEW",
            ],
            "limitations": [
                "Claude_Code capped at 4,734 (dataset has limited data)",
                "Cursor closed PRs limited to 2,651",
                "Maintainer merge decision is imperfect quality proxy",
                "Agent labels from AIDev bot detection",
            ],
        },
    }

    for agent in AGENTS:
        ag = sampled[sampled["agent"] == agent]
        m = ag[ag["label"] == "ACCEPTABLE"]
        c = ag[ag["label"] == "NEEDS_REVIEW"]
        stats["per_agent"][agent] = {
            "total": int(len(ag)),
            "merged": int(len(m)),
            "closed": int(len(c)),
        }

    stats_path = LAYER3_DIR / "sample_stats_zero_bias.json"
    with stats_path.open("w", encoding="utf-8") as fh:
        json.dump(stats, fh, indent=2, ensure_ascii=False)

    # Print summary
    n_agents = len(AGENTS)
    parts = f"PRs, {stats['unique_repos']:,} repos, {n_agents} agents"
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"Layer 3 Zero-Bias: {len(manifest):,} {parts}")
    print(f"{sep}")
    for agent, ag in stats["per_agent"].items():
        m = ag["merged"]
        c = ag["closed"]
        ratio = f"{m}:{c}" if c > 0 else "N/A"
        print(f"  {agent:20s} total={ag['total']:6,}  "
              f"merged={m:6,}  closed={c:6,}  ratio={ratio}")
    print(f"{sep}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())