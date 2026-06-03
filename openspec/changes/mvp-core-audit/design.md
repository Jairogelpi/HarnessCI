# Technical Design: mvp-core-audit

## Status

`design` phase complete. This document describes the first executable HarnessCI core slice and intentionally does not implement product code.

## Design Goals

This change creates a deterministic local audit pipeline:

```text
markdown spec + git diff -> normalized models -> deterministic scores -> JSON/Markdown report
```

The core must run without Gentle AI, Engram, agent skills, or LLM credentials. Gentle AI/OpenSpec/Engram remain development governance tools only.

## Package Structure

Target package layout for this slice:

```text
pyproject.toml
src/harnessci/
  __init__.py
  cli.py
  config.py
  errors.py
  models.py
  audit.py
  spec/
    __init__.py
    parser.py
  diff/
    __init__.py
    parser.py
    features.py
  scoring/
    __init__.py
    risk.py
    decision.py
  report/
    __init__.py
    json_report.py
    markdown.py
tests/
  test_cli.py
  test_spec_parser.py
  test_diff_parser.py
  test_scoring.py
  test_report.py
```

### Dependency posture

Use a small Python stack:

- Python `>=3.11`.
- `pydantic` for public/domain models.
- `pyyaml` for `harnessci.yaml`.
- `pytest` and `ruff` as development/test tools.
- Standard-library `argparse`, `json`, `subprocess`, and `pathlib` for CLI, git, and file IO.

Avoid Typer/Click in this slice to keep the scaffold small and reduce review burden.

## Public Models and Contracts

Keep model definitions centralized in `src/harnessci/models.py` for the first slice. Subpackages consume these models but should not define incompatible duplicates.

### Enums / literals

- `Decision`: `PASS`, `REVIEW_REQUIRED`, `BLOCK`, `INSUFFICIENT_INFORMATION`.
- `ChangeType`: `bugfix`, `feature`, `refactor`, `test-only`, `docs-only`, `security-sensitive`, `dependency-update`, `database-change`, `unknown`.
- `FindingSeverity`: `critical`, `high`, `medium`, `low`, `info`.
- `FindingCategory`: `spec`, `diff`, `tests`, `security`, `architecture`, `telemetry`, `config`, `report`.

### Core models

- `SpecModel`
  - `source_path: str | None`
  - `goal: str`
  - `acceptance_criteria: list[str]`
  - `out_of_scope: list[str]`
  - `risk_areas: list[str]`
  - `expected_scope: str | None`
  - `usable: bool`

- `DiffFileChange`
  - `path: str`
  - `old_path: str | None`
  - `status: str`
  - `lines_added: int`
  - `lines_deleted: int`
  - derived booleans: `is_test`, `is_docs`, `is_config`, `is_dependency`, `is_database`, `is_sensitive`

- `DiffFeatures`
  - `files_changed: int`
  - `lines_added: int`
  - `lines_deleted: int`
  - `total_churn: int`
  - `test_files_changed: int`
  - `config_files_changed: int`
  - `dependency_changes: int`
  - `database_migration_added: bool`
  - `public_api_changed: bool`
  - `sensitive_files_touched: list[str]`
  - `change_type: ChangeType`
  - `files: list[DiffFileChange]`

- `ScoreBreakdown`
  - `spec_compliance_score: int`
  - `diff_minimality_score: int`
  - `test_adequacy_score: int`
  - `security_risk_score: int`
  - `architecture_drift_score: int`
  - `harness_efficiency_score: int`
  - `overall_agentic_risk: int`

- `AuditFinding`
  - `severity: FindingSeverity`
  - `category: FindingCategory`
  - `message: str`
  - `evidence: str | None`

- `AuditReport`
  - `decision: Decision`
  - `overall_agentic_risk: int`
  - `scores: ScoreBreakdown`
  - `spec: SpecModel`
  - `diff: DiffFeatures`
  - `findings: list[AuditFinding]`
  - `recommendation: str`
  - `metadata: dict[str, str | int | float | bool | None]`

These models are the initial public API. Report rendering and CLI integration should serialize via Pydantic model methods, not ad-hoc dictionaries.

## Module Boundaries

### `config.py`

Loads optional repository config. CLI arguments override config values.

Design decisions:

- Default config path: `harnessci.yaml` in current working directory.
- Missing config is allowed for `harnessci audit` when required CLI args are present.
- Parse only fields needed in this slice:
  - `project.name`, `project.language`
  - `risk.strictness`
  - `risk.block_on_failed_tests`
  - `risk.block_on_security_critical`
  - `risk.require_tests_for_sensitive_changes`
  - `judge.enabled`
  - `report.fail_check_on_block` ignored locally
- If `judge.enabled: true`, the audit does not call an LLM. It adds an informational finding that LLM judge support is outside this slice.

### `spec/parser.py`

Responsibilities:

- Read markdown from a path.
- Extract sections by normalized heading names:
  - `Goal`
  - `Acceptance Criteria`
  - `Out of Scope`
  - `Risk Areas`
  - `Expected Scope`
- Support bullet lists and paragraph text.
- Preserve missing optional sections as empty lists or `None`.
- Mark `usable = false` when no meaningful goal and no acceptance criteria exist.

Non-goals:

- No LLM summarization.
- No issue/PR body collection.
- No OpenAPI/README inference.

### `diff/parser.py` and `diff/features.py`

Responsibilities:

- Run local git diff for `base..head` with clear errors if git is unavailable or revisions are invalid.
- Expose a pure parser for unified diff text so tests can use fixtures without shelling out.
- Count additions/deletions excluding diff metadata lines.
- Track changed paths from `diff --git`, `+++`, and `---` markers.
- Classify paths using deterministic filename/path rules.

Sensitive path/category heuristics for the MVP:

- Auth/session/permission: `auth`, `session`, `login`, `password`, `permission`, `role`, `acl`, `middleware`.
- Payment/billing: `billing`, `payment`, `invoice`, `subscription`, `checkout`, `stripe`, `paypal`.
- Database: `migration`, `migrations`, `schema`, `models`, `database`, `db`.
- Dependency/config: lockfiles, manifests, `.env`, `pyproject.toml`, `package.json`, `requirements*.txt`, `Dockerfile`, CI config.
- Public API: paths containing `api`, `routes`, `controllers`, `openapi`, or exported interface files.

Change classification order:

1. `dependency-update` if dependency files changed and no code files changed.
2. `database-change` if migration/database files changed.
3. `security-sensitive` if sensitive files changed.
4. `test-only` if all changed files are tests.
5. `docs-only` if all changed files are docs.
6. `unknown` otherwise.

The initial diff parser does not need AST-level function/class extraction.

### `scoring/risk.py` and `scoring/decision.py`

Responsibilities:

- Compute each score dimension deterministically.
- Apply the documented weighted formula from `docs/scoring_model.md`.
- Clamp and round scores to integers.
- Apply blocking/escalation rules after base risk-band decision.
- Emit findings for every major penalty/escalation.

MVP heuristic defaults:

- `harness_efficiency_score = 50` with a telemetry-unavailable finding. This produces neutral harness instability until telemetry exists.
- Test adequacy is based on diff evidence only in this slice:
  - test-only change: high adequacy;
  - code change with test files changed: medium/high;
  - code change without test files changed: low/medium;
  - sensitive code change without test files: low and escalation finding.
- Missing usable spec cannot produce `PASS`.
- Explicit out-of-scope path/text matches escalate to at least `REVIEW_REQUIRED`.
- Critical security evidence or low minimality plus high security/architecture risk can force `BLOCK`.

The scoring engine should expose one main function:

```text
score_audit(spec: SpecModel, diff: DiffFeatures, config: HarnessCIConfig) -> tuple[ScoreBreakdown, Decision, list[AuditFinding], str]
```

### `report/json_report.py` and `report/markdown.py`

Responsibilities:

- JSON report: serialize `AuditReport` to stable, indented JSON.
- Markdown report: render a PR-comment-ready summary with:
  - `## HarnessCI Audit`
  - decision
  - overall agentic risk
  - score table
  - main findings
  - recommendation

Report code must not recompute scores. It renders the `AuditReport` model only.

### `audit.py`

Coordinates the deterministic pipeline:

1. Load config.
2. Parse spec.
3. Extract diff features.
4. Score audit.
5. Build `AuditReport`.
6. Write JSON and optional Markdown outputs.

This isolates CLI parsing from audit behavior and makes the pipeline unit-testable.

### `cli.py`

Expose:

```bash
harnessci audit \
  --base <rev> \
  --head <rev> \
  --spec <path> \
  --output <report.json> \
  [--markdown-output <report.md>] \
  [--config harnessci.yaml]
```

CLI behavior:

- Missing required options fail with argparse usage and non-zero exit.
- Runtime errors are displayed as concise user-facing messages.
- No successful report is written on invalid required inputs.
- Parent directories for requested report paths may be created, but report writes should be atomic where practical.

## Data Flow

```text
CLI args
  -> config.load_config(args.config)
  -> spec.parser.parse_spec_file(args.spec)
  -> diff.parser.extract_git_diff(args.base, args.head)
  -> diff.parser.parse_diff_text(diff_text)
  -> scoring.risk.score_audit(spec, diff, config)
  -> AuditReport
  -> report.json_report.write_json(report, args.output)
  -> report.markdown.write_markdown(report, args.markdown_output?)
```

The same pipeline can later be reused by `audit-pr`, GitHub Action handling, and dataset evaluation without changing parser/scoring contracts.

## Error Handling

Define `errors.py` with user-facing exception types:

- `HarnessCIError` base class.
- `ConfigError` for invalid YAML or unsupported config values.
- `SpecParseError` for unreadable spec paths or malformed parser input.
- `GitDiffError` for missing git, invalid revisions, or non-repository cwd.
- `ScoringError` for impossible model states.
- `ReportWriteError` for output path/write failures.

CLI exit strategy:

- argparse validation errors: argparse default non-zero exit.
- `HarnessCIError`: print `HarnessCI error: ...`, exit `1`.
- Unexpected exceptions: in normal mode, print concise message and exit `1`; future debug mode may expose traceback.

No module should silently invent missing evidence. Unknown or unavailable evidence should be represented explicitly in models/findings.

## Config Handling

Config is optional in this slice, but the implementation should be future-compatible with the existing `harnessci.yaml`.

Merge order:

```text
hardcoded defaults < harnessci.yaml < CLI args
```

Initial defaults:

- `strictness = medium`
- `block_on_failed_tests = true`
- `block_on_security_critical = true`
- `require_tests_for_sensitive_changes = true`
- `judge_enabled = false`

If config parsing fails, fail the audit before diff/scoring. If config is missing and not explicitly provided, continue with defaults.

## Test Strategy

### Test runner bootstrap

First implementation step creates:

- `pyproject.toml`
- `src/harnessci/__init__.py`
- minimal package import test
- pytest/ruff configuration

After `pytest` and `ruff check .` exist and pass, update `openspec/config.yaml` to enable strict TDD:

```yaml
strict_tdd:
  enabled: true
  test_command: "pytest"
```

### RED/GREEN flow after scaffold

Once the test runner exists, each module should be implemented through RED/GREEN:

1. Write failing tests for the required behavior.
2. Implement the smallest deterministic code to pass.
3. Run `pytest`.
4. Run `ruff check .`.
5. Refactor only after tests are green.

### Required test coverage by module

- `test_spec_parser.py`
  - documented markdown spec extracts goal, acceptance criteria, out-of-scope, risk areas;
  - missing optional sections become empty/unknown;
  - unusable spec is marked unusable.

- `test_diff_parser.py`
  - unified diff counts changed files and churn;
  - test/config/dependency/database/sensitive paths are detected;
  - simple change classifications work;
  - parser can operate from diff fixture text.

- `test_scoring.py`
  - weighted formula clamps/rounds correctly;
  - risk bands map to PASS/REVIEW_REQUIRED/BLOCK;
  - missing spec does not pass;
  - sensitive change without tests escalates;
  - out-of-scope evidence escalates;
  - low minimality plus high risk blocks.

- `test_report.py`
  - JSON contains required fields;
  - Markdown contains heading, decision, score table/findings, recommendation.

- `test_cli.py`
  - missing required args fail;
  - happy path can run against a temporary git repo or monkeypatched audit pipeline;
  - output files are written on success.

## Rollout / Delivery Sequence

Use chained apply tasks to stay below the 400 changed-line review budget.

1. **Scaffold + tooling**
   - `pyproject.toml`, package skeleton, pytest/ruff config, smoke test, strict TDD config update after green.
   - Forecast: 120-180 changed lines.

2. **Models + spec parser**
   - `models.py`, `errors.py`, `spec/parser.py`, parser tests.
   - Forecast: 250-350 changed lines.

3. **Diff parser + features**
   - `diff/parser.py`, `diff/features.py`, diff tests.
   - Forecast: 250-350 changed lines.

4. **Scoring + decisions**
   - `scoring/risk.py`, `scoring/decision.py`, scoring tests.
   - Forecast: 250-350 changed lines.

5. **Audit orchestration + reports + CLI integration**
   - `audit.py`, `cli.py`, report renderers, CLI/report tests, minimal README update.
   - Forecast: 300-380 changed lines.

Total implementation is likely 1,100-1,500 changed lines, so a single apply would exceed the review budget. The design recommends chained PR-sized tasks rather than one large diff.

## Review Workload Forecast

The approved budget is 400 changed lines per review unit. This design forecasts five implementation units, each under 400 changed lines. If a unit exceeds forecast during apply, pause before continuing and split the unit further.

Risk hotspots for review:

- scoring rules must match `docs/scoring_model.md`;
- diff parser must not overcount metadata lines;
- missing evidence must not become optimistic `PASS`;
- no LLM/Gentle AI runtime dependency may be introduced;
- CLI errors must avoid writing misleading successful reports.

## Acceptance Mapping

- Local audit command: handled by `cli.py` + `audit.py`.
- Markdown spec parsing: handled by `spec/parser.py` and `SpecModel`.
- Git diff feature extraction: handled by `diff/parser.py` + `DiffFeatures`.
- Deterministic scoring/decisions: handled by `scoring/*` and `ScoreBreakdown`.
- JSON/Markdown reports: handled by `report/*`.
- No Gentle AI or LLM dependency: enforced by dependency list, module boundaries, and tests/config behavior.

## Non-Implementation Notes

This design intentionally avoids product code changes. The next SDD phase should convert this design into implementation tasks with RED/GREEN checkpoints and review-budget gates.

## skill_resolution

paths-injected
