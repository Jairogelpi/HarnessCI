# Change Proposal: mvp-core-audit

## Intent

Create the first deterministic HarnessCI product slice: a local Python CLI that can audit a branch/diff against a markdown task specification and emit reproducible JSON and Markdown reports.

This change turns the current governance scaffold into an executable MVP core without adding runtime agent dependency. HarnessCI must remain usable without Gentle AI and without any LLM provider.

## Problem

The repository currently contains product, architecture, scoring, research, and skill scaffolding, but no Python package, test runner, CLI, parsers, scoring engine, or report renderer. The next step is to establish a small, tested core that demonstrates the central thesis:

```text
spec -> diff -> deterministic signals -> risk scores -> decision -> report
```

## Scope

In scope for this change:

- Python project scaffold and test runner.
- Typed/domain models for specs, diff features, scores, decisions, findings, and reports.
- CLI base for local auditing.
- Markdown task-spec parser for goal, acceptance criteria, out-of-scope items, risk areas, and expected scope when present.
- Git diff feature parser using local git output or provided diff text.
- Deterministic scoring engine using the weights and blocking rules documented in `docs/scoring_model.md`.
- JSON report output.
- Markdown report output suitable for later PR comments.
- Tests for the core behavior introduced in this slice.
- Documentation updates only where needed to keep commands and scoring behavior accurate.

## Explicit Non-Goals

Out of scope for this change:

- GitHub Action packaging or marketplace behavior.
- GitHub API client, PR comment posting, or check-run failure behavior.
- Dashboard implementation.
- Dataset generation or AgenticPR-Bench-mini production.
- LLM judge calls or provider integration.
- Harness telemetry scoring beyond neutral/unavailable placeholders unless the implementation needs a simple model field.
- Full AST analysis of functions/classes.
- Running arbitrary project test/lint/coverage/security commands beyond creating HarnessCI's own test runner.
- Deep multi-language support.

## Affected Areas

Expected files/modules to be introduced or changed:

- `pyproject.toml` — package metadata, dependencies, CLI entry point, pytest/ruff config.
- `src/harnessci/` — Python package.
- `src/harnessci/cli.py` — CLI commands.
- `src/harnessci/spec/` — markdown spec parsing and models.
- `src/harnessci/diff/` — git diff parsing and feature extraction.
- `src/harnessci/scoring/` — deterministic rules, score calculation, and decision selection.
- `src/harnessci/report/` — JSON and Markdown rendering.
- `tests/` — pytest coverage for parser/scoring/report behavior.
- `docs/` and `README.md` — only minimal command/status updates if implementation changes user-facing usage.
- `openspec/config.yaml` — enable strict TDD only after the test command exists and is verified.

## Proposed Behavior

A user should be able to run a local command similar to:

```bash
harnessci audit --base main --head HEAD --spec .agent/spec.md --output report.json
```

The command should:

1. Load and normalize the markdown spec.
2. Extract diff features from git for the requested base/head, or from an internal/test fixture path if provided by implementation design.
3. Compute deterministic score dimensions and an overall decision.
4. Write a JSON report.
5. Optionally print or write a Markdown summary report.

The initial implementation may be intentionally conservative. If required evidence is missing, it should prefer `INSUFFICIENT_INFORMATION` or `REVIEW_REQUIRED` over optimistic `PASS`.

## Success Criteria

This change is successful when:

- The repository has a working Python package scaffold.
- `pytest` runs successfully for HarnessCI's own tests.
- A CLI entry point exists and can be invoked locally.
- The spec parser extracts goal, acceptance criteria, out-of-scope items, and risk areas from the documented markdown format.
- The diff parser reports at least files changed, lines added/deleted, total churn, test files changed, config files changed, dependency changes, sensitive files touched, and simple change classification.
- The scoring engine implements the documented MVP weighted formula and deterministic blocking/escalation rules.
- JSON and Markdown reports include decision, overall risk, score dimensions, findings, and recommendation.
- The core works without Gentle AI and without LLM calls.
- Strict TDD is enabled in OpenSpec after the test command exists and passes.
- The implementation can be reviewed within the 400 changed-line budget or is split into forecasted follow-up tasks before apply.

## Risks

- **Scope creep:** The full product includes GitHub Action, CI collection, telemetry, dashboard, and dataset work. This slice must stay local and deterministic.
- **Review budget risk:** A complete scaffold plus parsers, scoring, reporting, and tests may exceed 400 changed lines. Implementation should be forecasted into smaller apply tasks if needed.
- **False confidence risk:** Early scoring heuristics will be coarse. Reports should expose evidence and uncertainty rather than pretending to be a perfect reviewer.
- **Git portability risk:** Diff parsing must be robust enough for local repos, but Windows path handling and git availability need tests or clear errors.
- **Testing bootstrap risk:** Strict TDD is currently disabled because no test command exists. The first implementation step must establish and verify the test runner before enabling it.
- **Boundary risk:** Optional LLM judge and Gentle AI dogfooding must not leak into the deterministic runtime core.

## Rollback Plan

Because this change is additive, rollback is straightforward:

1. Revert the files introduced for the Python package, tests, and CLI scaffold.
2. Restore `openspec/config.yaml` if strict TDD was enabled during implementation.
3. Keep existing product/governance docs unless they were changed incorrectly.
4. Remove generated local outputs such as `report.json`, coverage files, or cache directories.

No database migrations, external services, or GitHub integrations are introduced in this change.

## Open Questions For Later Phases

These should not block this proposal:

- Exact CLI option names for future GitHub PR mode.
- Whether dashboard uses Streamlit or Next.js.
- How telemetry instability is weighted once real traces exist.
- How to calibrate scoring weights empirically after the dataset exists.
- Which GitHub Action packaging strategy to use.

## Delivery Forecast

Recommended chained apply sequence after spec/design/tasks approval:

1. Python scaffold, package metadata, CLI skeleton, and test runner.
2. Domain models and spec parser.
3. Diff parser and feature extraction.
4. Deterministic scoring and decisions.
5. JSON/Markdown report rendering and README/docs updates.

This sequence keeps each reviewable unit closer to the 400 changed-line budget and preserves strict TDD once the initial test runner exists.
