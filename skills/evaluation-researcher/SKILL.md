---
name: evaluation-researcher
description: Use when designing or running HarnessCI TFM experiments, datasets, gold labels, baselines, metrics, dashboards, or thesis evidence. Requires results to come from recorded datasets or reports, not invented outcomes.
---

# Evaluation Researcher

Use this skill for HarnessCI research and TFM evaluation work.

## Responsibilities

- Define experiments that answer the research question.
- Build and maintain AgenticPR-Bench-mini task, PR, label, and report files.
- Compare HarnessCI against tests-only, churn-only, and static-rule baselines.
- Produce metrics tables and dashboard-ready data.
- Track limitations clearly: small dataset, label subjectivity, language coverage, and optional judge effects.

## Rules

- Never invent results.
- Every quantitative claim must come from `datasets/`, `results/`, reports, or explicitly marked simulated examples.
- Keep gold label schema stable unless the research protocol changes.
- Separate product metrics from academic evaluation metrics.
- Save significant research decisions or findings to Engram.

## Key docs

Read:

- `docs/research_protocol.md`
- `docs/scoring_model.md`
- `docs/telemetry_schema.md`

## Output

Return concise experiment status, data sources used, metrics computed, limitations, and next recommended experiment.
