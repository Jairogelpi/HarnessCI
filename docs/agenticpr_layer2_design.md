# AgenticPR-Bench-mini Layer 2 Design

## Status

Approved direction: **controlled curated benchmark**.

Layer 2 is designed to fix the central weakness found in Layer 1 / 1.1: public
maintainer merge decisions are useful but noisy proxy labels, and weak PR-title
specs are not equivalent to real requirements.

## Goal

Build a controlled benchmark slice where each case has:

- an explicit task specification;
- expected touched files;
- out-of-scope areas;
- a prepared diff/patch;
- independent gold labels;
- enough metadata to compare HarnessCI against trivial baselines.

The purpose is not to produce a huge benchmark. The purpose is to create a small,
auditable layer with stronger internal validity than Layer 1.

## Scope

Layer 2 initial target:

```text
10 tasks × 3 patch variants = 30 cases
```

Each task contributes three variants:

| Variant | Primary label | Meaning |
| --- | --- | --- |
| `acceptable` | `ACCEPTABLE` | Implements the task with focused scope and adequate tests. |
| `needs_review` | `NEEDS_REVIEW` | Mostly useful but has missing tests, edge-case gaps, or moderate scope/risk issues. |
| `unacceptable` | `UNACCEPTABLE` | Violates spec, touches out-of-scope code, introduces security/correctness risk, or removes important behavior. |

This gives a balanced 30-case dataset with known labels. The sample is small but
sufficient for a TFM MVP comparison if reported honestly.

## Non-goals

Layer 2 does **not** initially require:

- live agent execution;
- GitHub PR creation;
- telemetry from real agent runs;
- multiple repositories cloned from the internet;
- large statistical claims.

Those belong to a later Layer 3 / extension once the controlled benchmark is in
place.

## Task families

Use toy-but-realistic repository slices aligned with the research protocol:

1. simple bugfix;
2. bugfix with edge case;
3. small feature;
4. controlled refactor;
5. test generation;
6. security-sensitive change;
7. API behavior change;
8. database/config migration;
9. frontend/input validation;
10. documentation or developer-experience update.

For the first implementation, cases can be represented as specs + unified diffs
without requiring full runnable demo repos. If tests-only baselines need real test
commands later, add minimal fixture repos in a separate work unit.

## Dataset layout

Recommended files:

```text
datasets/agenticpr-bench-mini/layer2/
  README.md
  tasks/
    task_001.yaml
    task_002.yaml
    ...
  patches/
    task_001_acceptable.diff
    task_001_needs_review.diff
    task_001_unacceptable.diff
    ...
  manifest.jsonl
  results/
    layer2_results.csv
    layer2_results.json
    layer2_metrics.json
    layer2_baseline_comparison.csv
    layer2_baseline_comparison.json
```

Generated outputs should live under `results/`. Curated task specs and patches are
source artifacts and should be committed.

## Task schema

Each `tasks/task_NNN.yaml` should contain:

```yaml
id: task_001
title: "Fix expired-session redirect"
repository_slice: "fastapi-auth-demo"
change_type: "bugfix"
expected_scope: "small_bugfix"

spec:
  goal: "Expired sessions redirect users to login and preserve the original destination."
  acceptance_criteria:
    - "Expired sessions return HTTP 302 to /login."
    - "The redirect includes a next query parameter with the original path."
    - "Authenticated sessions continue to access the protected route."
  out_of_scope:
    - "Changing password reset behavior."
    - "Replacing the authentication middleware."
  risk_areas:
    - "authentication"
    - "session handling"

expected_touched_files:
  - "app/auth/middleware.py"
  - "tests/test_auth_redirect.py"

variants:
  acceptable:
    patch: "patches/task_001_acceptable.diff"
    primary_label: "ACCEPTABLE"
    gold:
      spec_violation: false
      unrelated_changes: false
      missing_tests: false
      security_sensitive: true
      overengineering: false
      architecture_drift: false
  needs_review:
    patch: "patches/task_001_needs_review.diff"
    primary_label: "NEEDS_REVIEW"
    gold:
      spec_violation: true
      unrelated_changes: false
      missing_tests: true
      security_sensitive: true
      overengineering: false
      architecture_drift: false
  unacceptable:
    patch: "patches/task_001_unacceptable.diff"
    primary_label: "UNACCEPTABLE"
    gold:
      spec_violation: true
      unrelated_changes: true
      missing_tests: true
      security_sensitive: true
      overengineering: false
      architecture_drift: true
```

## Gold labels

Primary label:

- `ACCEPTABLE`
- `NEEDS_REVIEW`
- `UNACCEPTABLE`

Binary attributes:

- `spec_violation`
- `unrelated_changes`
- `missing_tests`
- `security_sensitive`
- `overengineering`
- `architecture_drift`

Rules:

- Gold labels must be assigned from the spec and patch content, not from HarnessCI
  output.
- HarnessCI results must not be used to edit labels after evaluation.
- If a label changes during dataset construction, record why in the task YAML or
  dataset README.

## Manifest schema

`manifest.jsonl` should flatten tasks and variants for evaluation:

```json
{
  "case_id": "task_001__acceptable",
  "task_id": "task_001",
  "variant": "acceptable",
  "title": "Fix expired-session redirect",
  "repository_slice": "fastapi-auth-demo",
  "change_type": "bugfix",
  "spec_path": "tasks/task_001.yaml",
  "patch_path": "patches/task_001_acceptable.diff",
  "expected_touched_files": ["app/auth/middleware.py", "tests/test_auth_redirect.py"],
  "primary_label": "ACCEPTABLE",
  "gold": {
    "spec_violation": false,
    "unrelated_changes": false,
    "missing_tests": false,
    "security_sensitive": true,
    "overengineering": false,
    "architecture_drift": false
  }
}
```

## Evaluation plan

For each case:

1. Load task spec from YAML.
2. Convert task spec to HarnessCI spec text using supported headings:
   - `## Goal`
   - `## Acceptance Criteria`
   - `## Out of Scope`
   - `## Risk Areas`
   - `## Expected Scope`
3. Load patch diff text.
4. Run `run_audit_from_diff_text(diff_text, spec_text=...)`.
5. Record HarnessCI decision, risk score, findings, and score breakdown.
6. Compare against gold primary label and binary attributes.

Positive prediction mapping:

| Gold | Expected audit stance |
| --- | --- |
| `ACCEPTABLE` | `PASS` preferred; `REVIEW_REQUIRED` counts as false positive for auto-merge, but may be analyzed as cautious. |
| `NEEDS_REVIEW` | `REVIEW_REQUIRED` preferred; `BLOCK` acceptable for high-risk variants. |
| `UNACCEPTABLE` | `BLOCK` preferred; `REVIEW_REQUIRED` partially correct for risk detection; `PASS` is unsafe. |

Report both strict and risk-detection metrics:

- strict three-class accuracy;
- binary unsafe-pass recall (`NEEDS_REVIEW`/`UNACCEPTABLE` vs `ACCEPTABLE`);
- unacceptable-block recall;
- false positive review rate on acceptable patches;
- per-attribute detection where possible.

## Baselines

Compare against:

1. `accept_all`: always predicts acceptable.
2. `tests_only`: if fixture test signal exists; otherwise mark unavailable.
3. `files_only`: changed files threshold.
4. `churn_only`: added+deleted lines threshold.
5. `scope_only`: patch touches files outside `expected_touched_files`.
6. `static_sensitive_rules`: auth/payment/db/dependency/public API heuristics.
7. `HarnessCI`: deterministic audit score and decision.

Do not tune thresholds on Layer 2 unless explicitly marked as exploratory. Fixed
thresholds should be documented before metrics are reported.

## Expected TFM contribution

Layer 2 lets the thesis say:

- Layer 1 showed public maintainer decisions are a noisy proxy.
- Layer 1.1 showed weak metadata specs are not enough for robust claims.
- Layer 2 introduces controlled task specs and gold labels to test whether
  HarnessCI detects concrete risks better than trivial baselines.

This progression is stronger than pretending Layer 1 was definitive.

## Implementation work units

1. Create Layer 2 schema/docs and 2 pilot tasks.
2. Add manifest builder from task YAML files.
3. Add Layer 2 evaluator and metrics.
4. Add baseline comparison.
5. Expand from 2 pilot tasks to 10 tasks after the pipeline works.

## Acceptance criteria for Layer 2 MVP

- At least 2 pilot tasks with 3 variants each are committed.
- Manifest builder produces valid `manifest.jsonl`.
- Evaluator produces results and metrics for 6 cases.
- Baseline comparison runs without external services.
- Full test suite passes.
- Dataset README states limitations and label methodology.

## Review risks

The full 10-task dataset may exceed a comfortable review size if added in one
commit. Keep commits split:

1. schema + pilot tasks + evaluator;
2. additional task batches;
3. final metrics and findings doc.
