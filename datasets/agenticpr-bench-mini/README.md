# AgenticPR-Bench-mini

AgenticPR-Bench-mini is a small, reproducible benchmark for evaluating CI checks on AI-generated pull requests.

This dataset is intentionally built in layers to avoid circular evaluation: HarnessCI does **not** create the ground-truth label for layer 1.

## Layer 1 — Real GitHub bot PRs

Source: public AIDev pull request table (`hao-li/AIDev/all_pull_request.parquet`) plus live GitHub API metadata/diffs.

Label rule:

| Label | Rule |
| --- | --- |
| `ACCEPTABLE` | `merged_at` is present in AIDev |
| `NEEDS_REVIEW` | PR was closed without merge |

This makes the label independent from HarnessCI: it comes from the repository maintainer's merge decision.

## Current layer 1 sample

The first slice contains 80 PRs, balanced by agent and label:

| Agent | ACCEPTABLE | NEEDS_REVIEW |
| --- | ---: | ---: |
| OpenAI_Codex | 8 | 8 |
| Copilot | 8 | 8 |
| Devin | 8 | 8 |
| Cursor | 8 | 8 |
| Claude_Code | 8 | 8 |

Generated files:

- `raw/layer1_real_github_prs.jsonl` — safe manifest with PR metadata, labels, diff hash, and diff path.
- `raw/layer1_summary.json` — counts, label rule, failures, and limitations.
- `raw/diffs/*.diff` — rebuildable raw diffs; ignored by git because they contain third-party code.
- `raw/sample_candidates.csv` — rebuildable candidate pool; ignored by git.
- `results/layer1_results.csv` — per-PR HarnessCI decision and risk output for the diff-only baseline.
- `results/layer1_results.json` — JSON equivalent of the per-PR diff-only baseline results.
- `results/layer1_metrics.json` — diff-only proxy metrics against maintainer merge/close labels.
- `raw/layer1.1_specs.jsonl` — weak specs reconstructed from safe PR metadata.
- `results/layer1.1_results.csv` — per-PR HarnessCI decision and risk output using weak specs.
- `results/layer1.1_results.json` — JSON equivalent of the layer-1.1 results.
- `results/layer1.1_metrics.json` — layer-1.1 proxy metrics against maintainer merge/close labels.
- `results/layer1.1_baseline_comparison.csv` — HarnessCI vs simple non-circular baselines.
- `results/layer1.1_baseline_comparison.json` — JSON equivalent of the baseline comparison.

## Evaluation

Layer 1.1 first reconstructs weak specs from safe PR metadata, then evaluates the
same diffs with those specs:

```bash
py scripts/build_agenticpr_layer1_specs.py
py scripts/evaluate_agenticpr_layer1.py
py scripts/compare_agenticpr_layer1_baselines.py
```

The evaluator reads the safe manifest and local raw diffs, then audits each diff with
`run_audit_from_diff_text(spec_text=...)`. Metrics use `accuracy_proxy` terminology
because maintainer merge/close decisions are useful but imperfect labels.

The weak specs are not hidden gold requirements. They are a transparent attempt to
provide minimal PR intent from title/body excerpt only. The comparison script also
runs fixed, non-circular baselines (`accept_all`, files-only, churn-only, and
files-or-churn) so HarnessCI is not evaluated in isolation.

This separates two findings:

1. **Layer 1 diff-only baseline:** without task intent, HarnessCI should avoid
   pretending confidence and may report `INSUFFICIENT_INFORMATION`.
2. **Layer 1.1 weak-spec evaluation:** with imperfect reconstructed intent,
   HarnessCI can produce `PASS` / `REVIEW_REQUIRED` / `BLOCK` proxy decisions while
   still documenting that labels are maintainer-decision proxies.
3. **Baseline comparison:** simple churn rules can be competitive or stronger on
   maintainer-decision proxies; this is evidence about the weakness of this proxy
   layer, not a claim that churn is better at judging correctness.

## Bias controls

- Stratified sampling across five agents.
- Balanced labels per agent: 8 merged and 8 closed-without-merge PRs.
- Missing/deleted PRs are excluded, not relabeled.
- Full PR bodies are not preserved in the public manifest; only a bounded excerpt, length, and SHA-256 hash are stored.
- Diffs are stored locally for analysis but are not intended to be committed as project-authored code.

## Known limitations

- Maintainer merge decision is an imperfect proxy for code correctness.
- Some closed-without-merge PRs may be duplicates, superseded, or rejected for non-technical reasons.
- Layer 1 generally lacks agent telemetry and explicit task specs.
- Layer 1.1 specs are weak reconstructions from PR title/body excerpts, not authoritative requirements.
- Fixed churn baselines may exploit maintainer/repository review patterns rather than code quality.
- Live GitHub metadata may drift if repositories are deleted or rewritten.
- This layer evaluates whether HarnessCI correlates with maintainer decisions, not whether it perfectly judges code quality.

## Rebuild

Install dataset extras:

```bash
py -m pip install -e ".[dataset]"
```

Run:

```bash
GITHUB_TOKEN=<token> py scripts/build_agenticpr_layer1.py
```

A token is recommended because unauthenticated GitHub API access is limited to 60 requests/hour.
