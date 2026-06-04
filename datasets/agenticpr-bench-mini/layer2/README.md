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
- `results/` — generated evaluation outputs, added by later work units.

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

## Rebuild manifest

```bash
py scripts/build_agenticpr_layer2_manifest.py
```
