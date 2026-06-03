---
name: risk_sensitive_code_review
description: Use when reviewing code, diffs, or PRs where hidden security, architecture, dependency, auth, payment, permission, database, or public API risk matters. Produces structured risk findings instead of generic style review.
---

# Risk-Sensitive Code Review

Use this skill for review of sensitive or high-impact changes.

## Focus areas

Prioritize these risks:

- authentication and session handling;
- authorization, permissions, roles, and ACLs;
- payment, billing, subscription, and invoice logic;
- database migrations and data loss risk;
- dependency, lockfile, and build configuration changes;
- secrets and environment variables;
- `eval`, `exec`, unsafe deserialization, shell commands, and network calls;
- crypto and token handling;
- public API or contract changes;
- broad refactors not requested by the task.

## Review rules

- Tie each finding to evidence: file path, changed behavior, missing test, or violated spec.
- Separate severity from confidence.
- Do not request cosmetic changes unless they affect maintainability or risk.
- Highlight missing tests for sensitive behavior.
- Flag scope creep and architecture drift explicitly.

## Output shape

```text
findings:
  - severity: critical | high | medium | low
    confidence: high | medium | low
    area: security | architecture | tests | scope | dependency | data
    evidence: ...
    impact: ...
    recommendation: ...
summary: ...
```
