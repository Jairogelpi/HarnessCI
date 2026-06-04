# AgenticPR-Bench-mini Layer 2: Pilot Findings

> **Status:** Pilot (2 tasks × 3 variants = 6 cases). Metrics are directional; do not overfit to n=6.

## Context

Layer 1 evaluation uses noisy proxy labels from real public PRs (maintainer decisions, `files_or_churn` heuristics). Layer 2 replaces those with curated gold labels assigned by the research team before HarnessCI evaluation — no circular tuning.

Each task has three variants: **acceptable**, **needs_review**, **unacceptable**. Gold labels encode which specific quality attributes are violated:

| Attribute | Meaning |
|---|---|
| `spec_violation` | Changes diverge from the defined goal/scope |
| `unrelated_changes` | Files or logic outside the expected scope |
| `missing_tests` | No new tests for sensitive or non-trivial changes |
| `security_sensitive` | Auth, billing, permissions, or similar domain touched |
| `architecture_drift` | Architectural patterns broken or replaced |
| `overengineering` | Excessive scope beyond what the task requires |

Gold labels are frozen — they are not revised based on HarnessCI output.

## Improvement trajectory

| Version | Strict accuracy | Unsafe recall | Unacceptable block recall |
|---|---|---|---|
| Baseline (PASS-all) | 0.3333 | 0.0000 | 0.0000 |
| + Findings escalation (high security/spec → REVIEW) | 0.6667 | 1.0000 | 0.0000 |
| + Auth removal detection + count-based escalation | 0.8333 | 1.0000 | 1.0000 |

### What each fix addressed

**v1 findings escalation:** Before this change, `decide()` only escalated CRITICAL findings. HIGH security and SPEC findings were silently ignored when overall risk was below threshold (31). Adding `has_security_finding or has_spec_finding → REVIEW_REQUIRED` lifted NEEDS_REVIEW cases from PASS to REVIEW_REQUIRED. Acceptable cases remained clean because they had test coverage for sensitive changes.

**v2 auth removal detection:** Added a finding for security-sensitive files modified with deletions and no test safety net. This fires on both needs_review and unacceptable variants (they modify auth files with deletions) but not on acceptable variants (which include tests). This doubled the security_high_count for unsafe cases from 2 to 3.

**v3 count-based escalation:** Before this change, the escalation rules were in two separate `if block_on_security_critical:` blocks. Python's early-return on the first matching condition meant that `security_high_count >= 1 or has_spec_finding → REVIEW_REQUIRED` fired before `security_high_count >= 3 → BLOCK`, causing unacceptable cases (3 findings) to return REVIEW_REQUIRED instead of BLOCK. Consolidating to a single if-elif chain with descending thresholds fixed the priority.

## Current results

| Case | Label | Decision | Strict correct | Finding count |
|---|---|---|---|---|
| task_001__acceptable | ACCEPTABLE | PASS | ✅ | 0 |
| task_002__acceptable | ACCEPTABLE | PASS | ✅ | 0 |
| task_001__needs_review | NEEDS_REVIEW | BLOCK | ⚠️ | 3 |
| task_002__needs_review | NEEDS_REVIEW | REVIEW_REQUIRED | ✅ | 1 |
| task_001__unacceptable | UNACCEPTABLE | BLOCK | ✅ | 3 |
| task_002__unacceptable | UNACCEPTABLE | BLOCK | ✅ | 3 |

**Decision distribution:** PASS=2, BLOCK=3, REVIEW_REQUIRED=1

## Remaining gap

**`task_001__needs_review` → BLOCK (should be REVIEW_REQUIRED).**

Root cause: the case triggers 3 HIGH security findings (auth removal detection, sensitive files without tests, security-sensitive change type). The escalation rule `security_high_count >= 3 → BLOCK` correctly identifies compound security risk, but the gold label encodes `NEEDS_REVIEW` rather than `UNACCEPTABLE` — implying the human reviewer expected manual escalation, not hard block.

**Options:**

1. **Keep BLOCK.** The three independent security findings justify escalation regardless of the intended label. The human label may underestimate the actual risk when auth logic is modified with no tests.

2. **Raise the BLOCK threshold to 4+ findings.** This would keep NEEDS_REVIEW at REVIEW_REQUIRED while unacceptable cases (which also have 3 findings) would need a separate signal to reach BLOCK.

3. **Add a SPEC finding for task_001 needs_review.** The spec defines out-of-scope items ("Disabling authentication checks") that the patch touches. If the out-of-scope matching fired, `security_high_count=2, has_spec_finding=True` would trigger `2 security + spec → BLOCK` instead of `3 security → BLOCK`. The current out-of-scope strings ("Disabling authentication checks") don't match the modified file paths ("app/auth/middleware.py"), so no SPEC finding is generated. Making out-of-scope patterns more file-path-aware would fix this.

**Recommendation:** Document the gap and expand to 10 tasks. With n=6 the confidence interval on strict accuracy is wide (approx. 50%–100% at 95% CI). Adding 8 more cases will reveal whether this gap is an isolated edge case or a pattern requiring targeted refinement. Do not tune escalation thresholds to improve task_001__needs_review without evidence from additional cases.

## Baseline comparison

The static `scope_or_static` baseline (files outside expected scope OR sensitive changes without tests) achieves `f1_unsafe=1.0` on the same 6 cases. HarnessCI's current results (`strict_accuracy=0.8333`) are competitive with this lightweight heuristic while operating on richer audit signals. The gap on task_001__needs_review reflects the difference between deterministic file matching (baseline) and accumulated audit evidence (HarnessCI).

## Next steps

1. Expand to 10 tasks × 3 variants. Generate additional tasks covering dependency updates, refactoring, test-only changes, and API changes.
2. Re-run evaluation and baselines to get a stable estimate of strict accuracy and unsafe recall.
3. If the gap on task_001__needs_review persists or new gaps appear, evaluate options 2 and 3 above with the larger dataset.
4. Measure false positive review rate — cases where ACCEPTABLE triggers REVIEW_REQUIRED or BLOCK despite correct behavior.

## Files

- `datasets/agenticpr-bench-mini/layer2/` — task YAML, patches, manifest
- `datasets/agenticpr-bench-mini/layer2/results/layer2_results.json` — per-case results
- `datasets/agenticpr-bench-mini/layer2/results/layer2_metrics.json` — aggregate metrics
- `datasets/agenticpr-bench-mini/layer2/results/layer2_baseline_comparison.csv` — static baselines
- `scripts/evaluate_agenticpr_layer2.py` — evaluator
- `scripts/compare_agenticpr_layer2_baselines.py` — baseline comparison