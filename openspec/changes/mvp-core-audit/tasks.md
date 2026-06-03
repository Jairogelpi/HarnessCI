# Implementation Tasks: mvp-core-audit

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1,200-1,600 total; 120-380 per work unit |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 scaffold/tooling → PR 2 models/spec parser → PR 3 diff parser/features → PR 4 scoring/decisions → PR 5 reports/audit/CLI |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

## Non-goals for this change

- Do not implement GitHub Action packaging, GitHub API clients, PR comments, or check-run failure behavior.
- Do not implement dashboard, dataset generation, AgenticPR-Bench-mini, or research result analysis.
- Do not call an LLM or make Gentle AI/Engram/skills a runtime dependency.
- Do not implement telemetry scoring beyond neutral/unavailable placeholders.
- Do not run arbitrary audited-project test/lint/coverage/security commands yet.
- Do not add AST-level function/class extraction or deep multi-language support.

## Delivery structure

Implement as five chained, reviewable work units. Each unit has a clear start/finish boundary, verification command, and rollback by reverting that unit's files. If any unit approaches 400 changed lines during apply, pause and split it further before continuing.

## PR 1 — Python scaffold and test runner

**Forecast:** 120-180 changed lines.  
**Start boundary:** repo has docs/governance scaffold only; no Python package/test runner.  
**Finish boundary:** pytest and ruff exist, a minimal package imports, strict TDD is enabled in `openspec/config.yaml`.

### 1.1 Bootstrap package metadata and dev tooling
- Files: `pyproject.toml`, `src/harnessci/__init__.py`, `tests/test_package_import.py`, `openspec/config.yaml`.
- RED: add `tests/test_package_import.py` first and run `python -m pytest`; expected failure before package skeleton exists: `ModuleNotFoundError: No module named 'harnessci'` or equivalent.
- GREEN: create minimal package skeleton and `pyproject.toml` with Python `>=3.11`, dependencies `pydantic`, `pyyaml`, dev tools `pytest`, `ruff`, and CLI entry point placeholder only if needed for packaging.
- TRIANGULATE: verify editable install works from a clean shell.
- REFACTOR: keep package init minimal; no product logic in `__init__.py`.
- Verification:
  - `python -m pip install -e ".[dev]"`
  - `python -m pytest`
  - `python -m ruff check .`
- After GREEN: update `openspec/config.yaml` strict TDD to `enabled: true`, `test_command: "pytest"`.
- Rollback: remove `pyproject.toml`, `src/harnessci/`, `tests/`, and restore strict TDD disabled in `openspec/config.yaml`.

## PR 2 — Public models, errors, and markdown spec parser

**Forecast:** 250-350 changed lines.  
**Depends on:** PR 1 green.  
**Finish boundary:** markdown task specs normalize into `SpecModel`; missing/weak specs are explicit and non-optimistic.

### 2.1 Define core Pydantic model contracts
- Files: `src/harnessci/models.py`, `src/harnessci/errors.py`, `tests/test_models.py` or model assertions inside parser/scoring tests.
- RED: write tests proving required enum/model fields serialize predictably and reject impossible types where Pydantic should validate.
- GREEN: implement `Decision`, `ChangeType`, `FindingSeverity`, `FindingCategory`, `SpecModel`, `DiffFileChange`, `DiffFeatures`, `ScoreBreakdown`, `AuditFinding`, `AuditReport`, and `HarnessCIError` subclasses.
- TRIANGULATE: add serialization checks for `AuditReport.model_dump()` / `model_dump_json()`.
- REFACTOR: keep all first-slice public models centralized in `models.py`; do not duplicate schemas in subpackages.
- Verification: `python -m pytest tests/test_models.py tests/test_spec_parser.py -q` once parser tests exist; `python -m ruff check .`.

### 2.2 Implement markdown spec parsing
- Files: `src/harnessci/spec/__init__.py`, `src/harnessci/spec/parser.py`, `tests/test_spec_parser.py`.
- RED: tests for documented spec format extracting `Goal`, `Acceptance Criteria`, `Out of Scope`, `Risk Areas`, and `Expected Scope`.
- GREEN: implement `parse_spec_file(path)` and pure `parse_spec_text(text, source_path=None)` with normalized heading matching, bullet-list extraction, paragraph goal support, empty optional sections, and `usable=false` when goal and acceptance criteria are absent.
- TRIANGULATE: add tests for missing optional sections, lowercase/variant headings, and unusable spec.
- REFACTOR: keep parser deterministic; no issue/PR collection, README inference, OpenAPI inference, or LLM summarization.
- Verification:
  - `python -m pytest tests/test_spec_parser.py -q`
  - `python -m ruff check src/harnessci/spec tests/test_spec_parser.py`
- Rollback: revert `models.py`, `errors.py`, `spec/`, and related tests.

## PR 3 — Git diff parser and feature extraction

**Forecast:** 250-350 changed lines.  
**Depends on:** PR 2 models.  
**Finish boundary:** unified diff text and local git diffs produce deterministic `DiffFeatures`.

### 3.1 Implement pure unified diff parser
- Files: `src/harnessci/diff/__init__.py`, `src/harnessci/diff/parser.py`, `tests/test_diff_parser.py`.
- RED: fixture-based tests for changed files, additions, deletions, and churn; expected failure before implementation.
- GREEN: implement `parse_diff_text(diff_text)` that tracks `diff --git`, `---`, `+++`, file status, and counts only real added/deleted lines, excluding metadata lines.
- TRIANGULATE: add tests for new files, deleted files, renamed paths if supported, empty diffs, and Windows-safe path handling.
- REFACTOR: split low-level parsing helpers only if it reduces complexity.
- Verification: `python -m pytest tests/test_diff_parser.py -q`; `python -m ruff check src/harnessci/diff tests/test_diff_parser.py`.

### 3.2 Implement path classification and git extraction wrapper
- Files: `src/harnessci/diff/features.py`, `src/harnessci/diff/parser.py`, `tests/test_diff_parser.py`.
- RED: tests for `is_test`, `is_docs`, `is_config`, `is_dependency`, `is_database`, `is_sensitive`, `public_api_changed`, and `change_type` classification order.
- GREEN: implement deterministic rules from `design.md`: dependency-only, database, security-sensitive, test-only, docs-only, unknown.
- TRIANGULATE: add fixture covering auth/session, payment/billing, migrations, dependency files, config files, public API paths, and docs-only changes.
- REFACTOR: keep heuristics transparent constants or small functions in `features.py`.
- Verification:
  - `python -m pytest tests/test_diff_parser.py -q`
  - `python -m ruff check .`
- Rollback: revert `diff/` and `tests/test_diff_parser.py`.

## PR 4 — Deterministic scoring and decision rules

**Forecast:** 250-350 changed lines.  
**Depends on:** PR 2 models and PR 3 diff features.  
**Finish boundary:** scores, findings, recommendation, and decision match `docs/scoring_model.md`.

### 4.1 Implement scoring formula and bands
- Files: `src/harnessci/scoring/__init__.py`, `src/harnessci/scoring/risk.py`, `src/harnessci/scoring/decision.py`, `tests/test_scoring.py`.
- RED: tests for weighted formula, clamping, rounding, and risk bands: `PASS`, `REVIEW_REQUIRED`, `BLOCK`.
- GREEN: implement `score_audit(spec, diff, config) -> tuple[ScoreBreakdown, Decision, list[AuditFinding], str]` using the documented formula and neutral `harness_efficiency_score = 50` when telemetry is unavailable.
- TRIANGULATE: add boundary tests around 30/31 and 60/61 risk bands.
- REFACTOR: keep formula constants readable and aligned with `docs/scoring_model.md`.
- Verification: `python -m pytest tests/test_scoring.py -q`; `python -m ruff check src/harnessci/scoring tests/test_scoring.py`.

### 4.2 Implement escalation/blocking findings
- Files: `src/harnessci/scoring/risk.py`, `src/harnessci/scoring/decision.py`, `tests/test_scoring.py`.
- RED: tests for missing spec not passing, sensitive change without tests escalating, explicit out-of-scope evidence escalating, low minimality plus high risk blocking, and judge-enabled adding info finding without LLM call.
- GREEN: implement deterministic findings for each major penalty/escalation; prefer `INSUFFICIENT_INFORMATION` or `REVIEW_REQUIRED` over optimistic `PASS` when evidence is missing.
- TRIANGULATE: add strictness/config-policy cases once `config.py` exists or use minimal config defaults if config is included in this PR.
- REFACTOR: if scoring weights or bands change, update `docs/scoring_model.md`; otherwise do not edit docs.
- Verification:
  - `python -m pytest tests/test_scoring.py -q`
  - `python -m ruff check .`
- Rollback: revert `scoring/` and `tests/test_scoring.py`.

## PR 5 — Config, audit orchestration, reports, and CLI

**Forecast:** 300-380 changed lines.  
**Depends on:** PRs 1-4 green.  
**Finish boundary:** local CLI writes stable JSON and optional Markdown report for a real local git diff/spec.

### 5.1 Implement config loading and report renderers
- Files: `src/harnessci/config.py`, `src/harnessci/report/__init__.py`, `src/harnessci/report/json_report.py`, `src/harnessci/report/markdown.py`, `tests/test_report.py`.
- RED: tests for missing config using defaults, invalid YAML raising `ConfigError`, JSON required fields, and Markdown containing `## HarnessCI Audit`, decision, score table, findings, and recommendation.
- GREEN: implement default config merge behavior and report renderers that only render `AuditReport` without recomputing scores.
- TRIANGULATE: add test for `judge.enabled: true` staying non-runtime/metadata-only.
- REFACTOR: keep report formatting stable and small.
- Verification: `python -m pytest tests/test_report.py -q`; `python -m ruff check src/harnessci/report src/harnessci/config.py tests/test_report.py`.

### 5.2 Implement audit orchestration and CLI command
- Files: `src/harnessci/audit.py`, `src/harnessci/cli.py`, `tests/test_cli.py`, `README.md` only if command docs need minimal update.
- RED: tests for missing required CLI args failing, invalid spec/diff not writing successful outputs, and happy path writing JSON plus Markdown via monkeypatched pipeline or temporary git repo.
- GREEN: implement `harnessci audit --base <rev> --head <rev> --spec <path> --output <report.json> [--markdown-output <report.md>] [--config harnessci.yaml]` using `argparse`, `audit.py`, and user-facing `HarnessCIError` handling.
- TRIANGULATE: run a smoke audit against a temporary git repo fixture or a controlled local branch diff.
- REFACTOR: keep CLI parsing separate from audit behavior; report writes should be atomic where practical and create parent output directories if safe.
- Verification:
  - `python -m pytest -q`
  - `python -m ruff check .`
  - `python -m harnessci.cli audit --help`
  - Optional after install: `harnessci audit --help`
- Rollback: revert `config.py`, `audit.py`, `cli.py`, `report/`, `tests/test_report.py`, `tests/test_cli.py`, and any README command update.

## Final cross-unit verification

Run after PR 5 and before claiming the MVP core slice complete:

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m harnessci.cli audit --help
```

If a sample spec and temp git fixture are available, also verify:

```bash
harnessci audit --base <base-rev> --head <head-rev> --spec <spec.md> --output tmp/report.json --markdown-output tmp/report.md
```

Expected evidence:

- JSON report includes `decision`, `overall_agentic_risk`, `scores`, `spec`, `diff`, `findings`, `recommendation`, and `metadata`.
- Markdown report starts with `## HarnessCI Audit` and includes decision, overall risk, score table, findings, and recommendation.
- Missing or unusable spec never yields optimistic `PASS`.
- Sensitive changes without tests produce at least `REVIEW_REQUIRED`.
- No code imports Gentle AI, Engram, agent skills, or LLM providers at runtime.

## Documentation and memory tasks

- After each work unit, update only docs that are directly contradicted by implementation evidence.
- If scoring weights, bands, or blocking rules change, update `docs/scoring_model.md` in the same unit.
- Save significant decisions/discoveries to Engram topic keys:
  - `sdd/mvp-core-audit/apply-progress`
  - `sdd/mvp-core-audit/verify-report`
  - `harnessci/scoring-model` when scoring semantics change
- This subagent could not save the tasks artifact to Engram because memory tools were not available in its tool namespace; parent/orchestrator should persist `sdd/mvp-core-audit/tasks` if Engram is available.
