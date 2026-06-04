# AgenticPR-Bench-mini Layer 2

Layer 2 is a controlled curated benchmark for HarnessCI evaluation.

Unlike Layer 1 / 1.1, labels here are assigned from explicit task specs and patch
content, not maintainer merge/close outcomes.

## Current pilot

The pilot contains 2 tasks × 3 variants = 6 cases:

| Task | Repository slice | Variants |
| --- | --- | --- |
| `task_001` | `fastapi-auth-demo` | acceptable, needs_review, unacceptable |
| `task_002` | `django-billing-demo` | acceptable, needs_review, unacceptable |

## Files

- `tasks/*.yaml` — task specs, expected scope, labels, and variant metadata.
- `patches/*.diff` — curated unified diff variants.
- `manifest.jsonl` — generated flat evaluation manifest.
- `results/layer2_results.csv` — HarnessCI decisions for pilot cases.
- `results/layer2_metrics.json` — HarnessCI strict and unsafe-detection metrics.
- `docs/agenticpr_layer2_findings.md` — detailed pilot findings, improvement trajectory, and next steps.
- `results/layer2_baseline_comparison.json` — JSON equivalent of baseline metrics.

## Label policy

Primary labels:

- `ACCEPTABLE`
- `NEEDS_REVIEW`
- `UNACCEPTABLE`

Gold attributes:

- `spec_violation`
- `unrelated_changes`
- `missing_tests`
- `security_sensitive`
- `overengineering`
- `architecture_drift`

Labels are assigned before HarnessCI evaluation and must not be edited based on
HarnessCI output.

## Pilot result

Current 6-case pilot:

| Predictor | Strict/unsafe result |
| --- | --- |
| HarnessCI | `strict_accuracy=0.3333`, `unsafe_detection_recall=0.0` |
| `scope_or_static` baseline | `f1_unsafe=1.0`, `recall_unsafe=1.0` |

Interpretation: the controlled pilot exposes a product gap. HarnessCI currently
passes all six cases, while a simple static/scope baseline catches all curated
unsafe cases. The next work unit should improve decision escalation using
spec/out-of-scope and deterministic static risk signals, then re-run the same
baselines without changing gold labels.

## Rebuild manifest

```bash
py scripts/build_agenticpr_layer2_manifest.py
py scripts/evaluate_agenticpr_layer2.py
py scripts/compare_agenticpr_layer2_baselines.py
```
