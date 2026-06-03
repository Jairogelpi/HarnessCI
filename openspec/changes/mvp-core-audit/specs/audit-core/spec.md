# Audit Core Specification

## Purpose

The audit core provides the first deterministic HarnessCI product slice: a local CLI audit flow that compares a markdown task specification with a git diff, computes reproducible risk scores and decisions, and emits JSON and Markdown reports without depending on Gentle AI or an LLM judge.

## Requirements

### Requirement: Local Audit Command

The system MUST provide a local `harnessci audit` command that accepts a base revision, head revision, task specification path, JSON output path, and optional Markdown output path.

#### Scenario: Audit command writes requested reports

- GIVEN a repository with a readable markdown task specification
- AND a valid git base and head revision
- WHEN the user runs `harnessci audit --base <base> --head <head> --spec <path> --output <report.json> --markdown-output <report.md>`
- THEN the system MUST parse the specification
- AND the system MUST extract diff features for the requested revisions
- AND the system MUST compute deterministic scores and a decision
- AND the system MUST write a JSON report to the requested JSON output path
- AND the system MUST write a Markdown report to the requested Markdown output path.

#### Scenario: Audit command rejects missing required inputs

- GIVEN the user omits the base revision, head revision, specification path, or JSON output path
- WHEN the user runs `harnessci audit`
- THEN the system MUST fail with a clear CLI error
- AND the system MUST NOT emit a successful audit report.

### Requirement: Markdown Specification Parsing and Normalization

The system MUST parse a markdown task specification into a normalized model containing goal, acceptance criteria, out-of-scope items, risk areas, and expected scope when those sections are present.

#### Scenario: Documented task specification is normalized

- GIVEN a markdown specification with `Goal`, `Acceptance Criteria`, `Out of Scope`, and `Risk Areas` sections
- WHEN the specification parser processes the file
- THEN the normalized specification MUST include the goal text
- AND the normalized specification MUST include each acceptance criterion as a separate item
- AND the normalized specification MUST include each out-of-scope item as a separate item
- AND the normalized specification MUST include each risk area as a separate item.

#### Scenario: Missing optional sections remain explicit

- GIVEN a markdown specification that contains a goal but no risk areas or expected scope
- WHEN the specification parser processes the file
- THEN the normalized specification MUST preserve the goal
- AND the normalized specification MUST represent missing optional sections as empty or unknown values rather than invented content.

### Requirement: Git Diff Feature Extraction

The system MUST extract deterministic diff features from the requested git base and head revisions.

#### Scenario: Diff features summarize changed files and churn

- GIVEN a git diff between a base revision and a head revision
- WHEN the diff parser processes the diff
- THEN the diff model MUST report files changed
- AND the diff model MUST report lines added, lines deleted, and total churn
- AND the diff model MUST report test files changed
- AND the diff model MUST report config files changed
- AND the diff model MUST report dependency changes
- AND the diff model MUST report sensitive files touched when changed paths match sensitive areas.

#### Scenario: Diff parser classifies simple change types

- GIVEN a diff that only changes tests, documentation, dependencies, database migrations, or security-sensitive paths
- WHEN the diff parser processes the diff
- THEN the diff model SHOULD classify the change as test-only, docs-only, dependency-update, database-change, security-sensitive, or unknown according to deterministic evidence.

### Requirement: Deterministic Scoring and Decisions

The system MUST compute risk scores and audit decisions using deterministic rules and the MVP scoring model documented for HarnessCI.

#### Scenario: Overall risk follows weighted formula

- GIVEN normalized spec signals, diff features, test adequacy signals, security risk signals, architecture drift signals, and harness efficiency availability
- WHEN the scoring engine computes an audit result
- THEN the system MUST compute `overall_agentic_risk` from the documented weighted formula
- AND the system MUST clamp score dimensions to 0-100
- AND the system MUST round reported score dimensions to integers.

#### Scenario: Decision bands select the base decision

- GIVEN an overall risk score from 0 to 30 with no blocking rule
- WHEN the decision engine evaluates the audit
- THEN the decision MUST be `PASS`.

- GIVEN an overall risk score from 31 to 60 with no blocking rule
- WHEN the decision engine evaluates the audit
- THEN the decision MUST be `REVIEW_REQUIRED`.

- GIVEN an overall risk score from 61 to 100
- WHEN the decision engine evaluates the audit
- THEN the decision MUST be `BLOCK`.

#### Scenario: Missing usable specification is not an optimistic pass

- GIVEN no usable task specification or intent can be parsed
- WHEN the scoring engine evaluates the audit
- THEN the decision MUST be `INSUFFICIENT_INFORMATION` or `REVIEW_REQUIRED`
- AND the decision MUST NOT be `PASS`.

#### Scenario: Deterministic blocking and escalation rules apply

- GIVEN deterministic evidence that tests failed, a critical security rule fired, sensitive files changed without relevant tests, explicitly out-of-scope files changed, or low minimality combines with high risk
- WHEN the decision engine evaluates the audit
- THEN the system MUST apply the documented blocking or escalation rule before returning the final decision
- AND the report MUST include findings explaining the rule evidence.

### Requirement: JSON Audit Report

The system MUST emit a machine-readable JSON report containing the audit decision, overall risk, score dimensions, normalized inputs or summaries, findings, and recommendation.

#### Scenario: JSON report contains required audit fields

- GIVEN a completed local audit
- WHEN the system writes the JSON report
- THEN the JSON MUST include `decision`
- AND the JSON MUST include `overall_agentic_risk`
- AND the JSON MUST include score dimensions for spec compliance, diff minimality, test adequacy, security risk, architecture drift, and harness efficiency
- AND the JSON MUST include findings
- AND the JSON MUST include a recommendation.

### Requirement: Markdown Audit Report

The system MUST render a human-readable Markdown audit report suitable for later use as a Pull Request comment.

#### Scenario: Markdown report presents decision and findings

- GIVEN a completed local audit
- WHEN the system renders the Markdown report
- THEN the report MUST include a `HarnessCI Audit` heading
- AND the report MUST include the decision
- AND the report MUST include the overall agentic risk
- AND the report MUST include a score table or equivalent structured score summary
- AND the report MUST include main findings
- AND the report MUST include a recommendation.

### Requirement: No Gentle AI Runtime Dependency

The audit core MUST run without Gentle AI, agent workflows, agent skills, or agent memory as runtime dependencies.

#### Scenario: Audit runs in deterministic-only environment

- GIVEN a Python environment with HarnessCI installed
- AND no Gentle AI runtime is installed or configured
- WHEN the user runs a valid local audit command
- THEN the system MUST complete the deterministic audit flow
- AND the system MUST NOT require agent orchestration, agent skills, or Engram memory to produce the report.

### Requirement: No LLM Judge in MVP Core Slice

The MVP core audit slice MUST NOT call or require any LLM judge or LLM provider.

#### Scenario: Audit does not invoke LLM provider

- GIVEN a valid local audit command
- AND no LLM provider credentials are configured
- WHEN the audit runs
- THEN the system MUST complete without requesting LLM credentials
- AND the report MUST be based on deterministic parser, diff, scoring, and reporting behavior only.

#### Scenario: LLM judge configuration is ignored or rejected for this slice

- GIVEN a user attempts to enable an LLM judge for the MVP core audit slice
- WHEN the audit runs
- THEN the system MUST NOT use the LLM judge as an audit signal
- AND the system SHOULD report that LLM judge support is outside the current slice when such configuration is visible to the audit flow.
