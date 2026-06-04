# Agent Reputation — First Public AI Agent Safety Rankings

**Powered by HarnessCI** — deterministic audit of real GitHub PRs from AI coding agents.

## Rankings (June 2026)

| Rank | Agent | Score | Badge | Avg Risk | Pass Rate |
|---|---|---|---|---|---|
| #1 | OpenAI Codex | 88.5 | Safe | 20.5 | 94% |
| #2 | Devin | 74.5 | Trusted | 28.0 | 62% |
| #3 | Claude Code | 74.1 | Trusted | 29.5 | 62% |
| #4 | Copilot | 72.0 | Trusted | 29.6 | 56% |
| #5 | Cursor | 62.4 | Neutral | 34.6 | 31% |

## Methodology

- **Data:** 80 real GitHub pull requests from 5 AI agents (16 each), balanced merged/closed
- **Audit:** HarnessCI deterministic analysis — spec compliance, diff features, test signals
- **Scoring:** Weighted formula (safety 40%, pass rate 30%, focus 15%, consistency 10%, transparency 5%)
- **Badges:** Safe (80+), Trusted (65+), Neutral (45+), Caution (30+), Risky (<30)

## Key Findings

- **OpenAI Codex** generates the safest PRs: lowest risk (20.5) and highest pass rate (94%)
- **Cursor** generates the riskiest PRs: highest risk (34.6) and lowest pass rate (31%)
- **All agents** trigger security findings on sensitive changes without tests
- **Risk variance** is consistent across agents (std 10-15 points)

## Disclaimer

Based on 80 PRs from public data. Sample sizes are small (n=16 per agent).
Results are directional, not statistically significant. Larger samples needed for definitive rankings.

## Data Files

- `agent_profiles.json` — Full per-agent profiles with subscores and risk breakdowns
- `agent_rankings.json` — Summary rankings with metadata
- `index.html` — Interactive dashboard visualization

## Rebuild

```bash
py scripts/build_agent_reputation.py
open datasets/agent_reputation/index.html
```