---
name: harnessci-product-engineer
description: Use when designing, implementing, or reviewing HarnessCI product features. Keeps the deterministic audit core separate from optional LLM judging and Gentle AI dogfooding, protects CLI compatibility, and requires docs/tests for behavior changes.
---

# HarnessCI Product Engineer

Use this skill for HarnessCI product work: CLI, GitHub Action, spec parsing, diff analysis, CI collection, scoring, reporting, configuration, and dashboard data outputs.

## Rules

- Treat HarnessCI as the product. Gentle AI helps build and dogfood it but is not a runtime dependency.
- Implement deterministic logic first. Do not add hidden LLM calls to the core.
- Keep public behavior documented in `docs/` and configuration examples.
- Preserve CLI compatibility once the CLI exists.
- Use Pydantic or typed schemas for public data models when product code starts.
- Add tests for every product behavior once test infrastructure exists.
- If scoring weights, decision bands, or blocking rules change, update `docs/scoring_model.md` and save the decision to Engram.

## Before editing

Read the relevant docs:

- `docs/product_spec.md`
- `docs/architecture.md`
- `docs/scoring_model.md`
- `openspec/config.yaml`

## Output expectations

Return concise evidence: files changed, tests run, behavior added, risks, and next step.
