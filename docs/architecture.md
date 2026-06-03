# HarnessCI Architecture

## Architectural thesis

HarnessCI audits agent-generated Pull Requests as a new object:

```text
spec -> agent/harness -> diff -> tests -> telemetry -> risk -> decision
```

The product must remain reproducible and defensible: deterministic code produces the base audit; optional LLM signals can enrich the report but cannot replace rules, metrics, or evidence.

## Boundary 1: Deterministic HarnessCI core

The deterministic core is the product runtime. It must work without Gentle AI and without an LLM provider.

Responsibilities:

- collect specs from files, PR metadata, issue text, and configured paths;
- normalize specs into goal, acceptance criteria, out-of-scope items, risk areas, and expected scope;
- parse git diffs and extract changed-file/churn/critical-area features;
- detect sensitive changes such as auth, payment, permission, migrations, dependencies, secrets, unsafe shell/eval usage, crypto, serialization, public API changes;
- run configured tests/lint/coverage/security commands;
- collect optional telemetry JSON files;
- compute scores and decisions using documented rules;
- generate JSON, Markdown, and later HTML reports;
- comment on GitHub PRs and optionally fail checks according to policy.

## Boundary 2: Optional LLM judge

The LLM judge is optional and must be explicitly enabled. It compares a bounded evidence packet: normalized spec, PR description, diff summary, test results, and risk signals.

Rules:

- The LLM returns strict JSON.
- The LLM is one signal among several.
- The deterministic rules still own blocking conditions such as failing tests or critical security rules.
- Reports must state when the judge was unavailable, disabled, or used.
- Core scoring must remain reproducible when the judge is disabled.

## Boundary 3: Gentle AI dogfooding

Gentle AI is not a runtime dependency of HarnessCI. It is a controlled development and experiment harness.

Gentle AI roles:

- build HarnessCI through SDD/OpenSpec artifacts;
- generate dogfooding PRs against HarnessCI and toy repos;
- create task specs and acceptance criteria;
- emit `.harnessci/telemetry.json` traces;
- help produce documentation and research artifacts;
- propose scoring improvements after deterministic evaluation.

Gentle AI must not:

- become required to run HarnessCI;
- silently change scoring weights without updating `docs/scoring_model.md`;
- introduce hidden LLM calls into core scoring;
- blur the boundary between evaluated agent and evaluating product.

## High-level data flow

```text
GitHub PR / local branch
  -> Spec Collector
  -> Diff Parser
  -> CI Collector
  -> Telemetry Collector (optional)
  -> Risk Scoring Engine
  -> Report Generator
  -> GitHub Comment / JSON / HTML
```

## Initial module map

- `spec`: collect, parse, and normalize task intent.
- `diff`: parse git changes, classify change type, compute minimality signals.
- `ci`: execute configured validation commands and collect coverage/lint/security results.
- `telemetry`: load Agentic Pull Request Telemetry Schema v0.1 files and compute harness instability.
- `scoring`: apply deterministic weights, blocking rules, and optional judge signal.
- `report`: render Markdown, JSON, and later HTML.
- `github`: read PR context and post comments/checks.
- `dataset` and `analysis`: support TFM experiments and dashboard.

## Governance rules

- Use OpenSpec docs and Engram for significant decisions and discoveries.
- Keep strict TDD disabled until the product test command exists, then enable it.
- Protect reviewer workload: forecast splitting when expected changes exceed 400 changed lines.
- Prefer small, auditable PRs with clear acceptance criteria and evidence.
