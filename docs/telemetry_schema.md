# Agentic Pull Request Telemetry Schema v0.1

HarnessCI defines an open telemetry format for traces left by coding agents and harnesses. Telemetry is optional: audits must still run without it, but telemetry improves harness-efficiency and agentic-risk analysis.

## File locations

Default configured search paths:

```text
.agent/trace.json
.openhands/trajectory.json
.harnessci/telemetry.json
```

## Schema

```json
{
  "schema_version": "0.1",
  "agent": {
    "name": "claude-code",
    "version": "x.y.z",
    "model": "claude-sonnet"
  },
  "harness": {
    "name": "plan-execute-repair",
    "planning": true,
    "reflection": false,
    "memory": "summary",
    "tool_retries": 3,
    "max_steps": 30
  },
  "execution": {
    "start_time": "2026-06-03T10:00:00Z",
    "end_time": "2026-06-03T10:12:00Z",
    "tokens_in": 52100,
    "tokens_out": 11800,
    "latency_ms": 430000,
    "tool_calls": 38,
    "file_reads": 19,
    "file_writes": 7,
    "edit_attempts": 9,
    "test_runs": 6,
    "failed_test_runs": 4,
    "errors": 3
  },
  "outputs": {
    "commit_sha": "abc123",
    "pr_number": 42,
    "summary": "Fixed expired session redirect"
  }
}
```

## Field semantics

### `agent`

Identifies the system that produced the PR: Claude Code, Codex, Copilot Coding Agent, OpenHands, Devin, Cursor, Kilo, or another agent.

### `harness`

Describes the process wrapped around the model: planning, reflection, memory mode, retry policy, and maximum steps. This allows comparison between harness strategies independent of the model.

### `execution`

Captures process cost and instability signals. High failed-test runs, edit attempts, retries, or tool errors can indicate unstable convergence even when final tests pass.

### `outputs`

Links telemetry to the generated commit/PR and provides a short human-readable summary.

## Compatibility rules

- Unknown fields are allowed and should be preserved in JSON reports when possible.
- Missing telemetry must not fail an audit.
- Invalid telemetry should produce a warning and be excluded from scoring unless policy says otherwise.
- HarnessCI must state whether telemetry was unavailable, invalid, or used.

## Research use

Telemetry supports TFM hypotheses about whether tool calls, retries, edit attempts, and failed test runs predict integration risk or review burden.
