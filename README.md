# HarnessCI

**CI for AI-generated Pull Requests.**

Stop merging AI-generated PRs blindly.

AI coding agents can now open complete pull requests. HarnessCI tells maintainers whether those PRs are safe to review, merge, or block.

## What HarnessCI checks

- Did the PR follow the original issue, task, or spec?
- Did it touch unrelated files or sensitive areas?
- Did it pass tests for the right reasons?
- Did it add or change adequate tests?
- Did it introduce security-sensitive changes?
- Did the agent or harness show unstable behavior such as many retries, failed test runs, or excessive edits?
- Should a human review this before merge?

## Planned GitHub Action usage

```yaml
name: HarnessCI

on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  audit:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write
      checks: write

    steps:
      - uses: actions/checkout@v4
      - name: Run HarnessCI
        uses: harnessci/audit@v0
        with:
          spec-path: ".agent/spec.md"
          strictness: "medium"
          language: "python"
          llm-judge: "optional"
```

## MVP status

This repository is currently at the governance/scaffolding stage. Product code has not been implemented yet.

Planned MVP:

- Local CLI
- GitHub Action
- Specification parser
- Diff parser and minimality analysis
- Configurable tests/lint execution
- Rules-based risk scoring
- Markdown PR report
- Agentic PR telemetry schema
- Experimental dataset and dashboard for TFM evaluation

## Core principle

HarnessCI must work without Gentle AI or any LLM. The deterministic core audits PRs. Gentle AI is used to build the product, generate dogfooding PRs, and support experiments; it is not a required runtime dependency.
