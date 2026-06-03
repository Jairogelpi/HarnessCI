---
name: agentic-telemetry-writer
description: Use when generating, validating, or documenting Agentic Pull Request Telemetry for HarnessCI. Writes transparent JSON traces for agent runs, including model, harness, tool calls, retries, tests, errors, cost, and PR outputs.
---

# Agentic Telemetry Writer

Use this skill when an agent or harness run should leave a trace for HarnessCI.

## Principles

- Telemetry is evidence, not marketing.
- Do not invent counts, timings, costs, or test results.
- Mark unavailable fields as absent or null rather than guessing.
- Keep the schema compatible with `docs/telemetry_schema.md`.
- Prefer `.harnessci/telemetry.json` for HarnessCI dogfooding.

## Required sections

- `schema_version`
- `agent`
- `harness`
- `execution`
- `outputs`

## Data quality checks

Before writing telemetry:

- verify timestamps are ISO-8601 if known;
- ensure counters are non-negative integers;
- ensure PR number and commit SHA match actual outputs when available;
- state when telemetry is partial;
- avoid including secrets, prompts with credentials, or private tokens.

## Output

Produce valid JSON and a short note explaining any missing or partial fields.
