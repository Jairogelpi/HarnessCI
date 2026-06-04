# AgenticPR-Bench-mini Layer 1 / 1.1 Findings

## Purpose

This note records the first empirical slice for the TFM evaluation of HarnessCI.
It is deliberately modest: Layer 1 uses real public PRs and maintainer decisions
as proxy labels; Layer 1.1 adds weak PR-intent specs reconstructed from safe PR
metadata.

The goal is not to claim that HarnessCI can perfectly judge PR correctness. The
goal is to measure whether a transparent hybrid audit adds useful review-priority
signals beyond trivial baselines.

## Data source

- Dataset: `datasets/agenticpr-bench-mini/raw/layer1_real_github_prs.jsonl`
- Weak specs: `datasets/agenticpr-bench-mini/raw/layer1.1_specs.jsonl`
- Results: `datasets/agenticpr-bench-mini/results/layer1.1_results.csv`
- Baselines: `datasets/agenticpr-bench-mini/results/layer1.1_baseline_comparison.csv`

Sample:

- 80 public AI-agent PRs.
- 5 agents: OpenAI Codex, Copilot, Devin, Cursor, Claude Code.
- Balanced per agent: 8 merged PRs and 8 closed-without-merge PRs.

Proxy label rule:

| Label | Rule |
| --- | --- |
| `ACCEPTABLE` | PR was merged by repository maintainers. |
| `NEEDS_REVIEW` | PR was closed without merge. |

This label is independent from HarnessCI, but it is not a ground-truth correctness
label.

## Layer definitions

### Layer 1 — diff-only baseline

HarnessCI receives only the PR diff. Without task intent, a cautious audit should
avoid pretending confidence. This layer documents a product limitation: public PR
diffs alone are often insufficient for reliable pass/fail decisions.

### Layer 1.1 — weak-spec evaluation

HarnessCI receives the same PR diffs plus weak specs reconstructed from PR title
and bounded body excerpt. These specs are transparent and reproducible, but not
authoritative hidden requirements.

Layer 1.1 is therefore an intermediate layer: better than diff-only, weaker than a
controlled benchmark with real task specs and gold labels.

## Baseline comparison

Positive prediction means “needs review or block”.

| Predictor | Accuracy proxy | Precision | Recall | F1 | Positive predictions |
| --- | ---: | ---: | ---: | ---: | ---: |
| HarnessCI Layer 1.1 | 0.4875 | 0.4839 | 0.3750 | 0.4225 | 31 |
| Accept all | 0.5000 | — | 0.0000 | — | 0 |
| Files only (`changed_files > 5`) | 0.4875 | 0.4857 | 0.4250 | 0.4533 | 35 |
| Churn only (`additions + deletions > 250`) | 0.4750 | 0.4773 | 0.5250 | 0.5000 | 44 |
| Files or churn | 0.5000 | 0.5000 | 0.5750 | 0.5349 | 46 |

## Interpretation

The first result is intentionally uncomfortable: on this maintainer-decision proxy
slice, simple churn heuristics are competitive with or stronger than HarnessCI
Layer 1.1.

This should not be hidden. It suggests three things:

1. **The proxy label is weak.** Maintainers may close PRs for reasons unrelated to
   code correctness: duplicates, abandoned branches, stale context, style, project
   priorities, or superseded work.
2. **Public metadata loses intent.** Weak specs based on titles/body excerpts are
   not equivalent to real task specifications, acceptance criteria, or issue
   context.
3. **HarnessCI needs controlled layers.** The next benchmark layer should include
   known task specs, expected scope, and gold labels so risk dimensions can be
   evaluated against correctness attributes rather than maintainer outcome alone.

## Useful signal despite weak proxy

Layer 1.1 still provides value for the TFM because it establishes an honest lower
bound:

- It proves the pipeline can evaluate 80 real PR diffs reproducibly.
- It separates diff-only insufficiency from weak-spec evaluation.
- It records that HarnessCI does not automatically beat trivial heuristics under
  a noisy maintainer-decision label.
- It motivates Layer 2: controlled PRs with task specs and gold labels.

## Threats to validity

- `merged_at` is not a correctness label.
- Closed PRs can be technically correct but unwanted, duplicated, or obsolete.
- Weak specs may include generic acceptance criteria that are too broad.
- Raw diffs may lack linked issue context, review comments, or test results.
- The sample is small and stratified for balance, not representativeness.
- Fixed churn thresholds were not tuned on this slice, but churn may still correlate
  with maintainer behavior rather than quality.

## Next experiment

Build Layer 2: controlled synthetic/curated PRs with:

- explicit task specs;
- expected touched files and out-of-scope areas;
- gold labels for `spec_violation`, `unrelated_changes`, `missing_tests`,
  `security_sensitive`, `overengineering`, and `architecture_drift`;
- comparisons against tests-only, churn-only, static rules, and HarnessCI.
