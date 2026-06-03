# HarnessCI Scoring Model

## MVP dimensions

HarnessCI computes seven MVP scores on a 0-100 scale:

| Score | Meaning |
| --- | --- |
| `spec_compliance_score` | How well the PR satisfies the declared task and acceptance criteria. |
| `diff_minimality_score` | How proportional and focused the diff is for the task. |
| `test_adequacy_score` | Whether tests pass and meaningfully cover the changed behavior. |
| `security_risk_score` | Risk from sensitive files, APIs, dependencies, secrets, unsafe constructs, and critical flows. Higher means riskier. |
| `architecture_drift_score` | Risk of unrequested structural, API, or design changes. Higher means riskier. |
| `harness_efficiency_score` | Whether the agent/harness converged cleanly. Higher means better efficiency. |
| `overall_agentic_risk` | Combined risk used for decision. Higher means riskier. |

## Initial weighted formula

```text
overall_risk =
  0.25 * (100 - spec_compliance)
+ 0.20 * (100 - diff_minimality)
+ 0.20 * (100 - test_adequacy)
+ 0.20 * security_risk
+ 0.10 * architecture_drift
+ 0.05 * harness_instability
```

Where:

```text
harness_instability = 100 - harness_efficiency
```

All scores are clamped to 0-100 and rounded to integers for reporting.

## Decision bands

| Overall risk | Decision |
| ---: | --- |
| 0-30 | `PASS` |
| 31-60 | `REVIEW_REQUIRED` |
| 61-100 | `BLOCK` |

`INSUFFICIENT_INFORMATION` is used when required evidence is missing and policy says no reliable decision can be made, especially when no spec or PR intent exists.

## Blocking and escalation rules

Initial deterministic rules:

- If configured tests fail and `block_on_failed_tests` is true: `BLOCK`.
- If a critical security rule fires and `block_on_security_critical` is true: `BLOCK`.
- If auth, payment, permission, crypto, dependency, or database-sensitive files are touched with no relevant new/changed tests: at least `REVIEW_REQUIRED`; may be `BLOCK` under high strictness.
- If the PR modifies files explicitly listed as out of scope: at least `REVIEW_REQUIRED`.
- If no usable spec or task intent is available: `INSUFFICIENT_INFORMATION` or `REVIEW_REQUIRED` depending on policy.
- If diff minimality is below 40 and security or architecture risk is above 70: `BLOCK`.
- If spec compliance is above 85, tests pass, security risk is low, and diff minimality is above 70: eligible for `PASS` unless another blocking rule fires.

## MVP heuristics

### Spec compliance

Inputs: goal match, acceptance criteria coverage, out-of-scope violations, PR title/body alignment, and tests that encode acceptance criteria.

### Diff minimality

Inputs: files changed, total churn, unrelated file ratio, critical unmentioned files, churn per acceptance criterion, and test-to-code ratio.

### Test adequacy

Inputs: test command result, new tests added, changed tests, coverage delta when available, critical path coverage, and acceptance criteria covered by tests.

### Security risk

Inputs: auth/payment/permission changes, migrations and dependency changes, environment variables and secrets, eval/exec or shell command usage, network calls, serialization/deserialization, crypto changes, and public API changes.

### Harness efficiency

Inputs from telemetry: tool calls, edit attempts, retries, test runs, failed test runs, tool errors, tokens, latency, and cost estimates.

If telemetry is unavailable, HarnessCI reports `Harness telemetry: unavailable` and uses a neutral harness instability default unless policy says otherwise.

## Change control

Scoring weights are product and research decisions. Any change to weights, bands, or blocking rules must update this document and be saved to Engram.
