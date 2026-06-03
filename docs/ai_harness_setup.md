# Pi / Gentle AI Harness Setup

This project uses Pi + el Gentleman as the builder/evaluator harness. HarnessCI itself remains deterministic and must not import harness tooling at runtime.

## Target architecture

```text
Human
  ↓
el Gentleman parent session
  ├─ Engram: durable decisions, preferences, session summaries
  ├─ Serena MCP: symbol navigation/refactoring when available
  ├─ Graphify MCP: repo/module impact map when available
  ├─ pi-lens: LSP diagnostics/navigation + ast-grep
  ├─ subagents: scout / context-builder / worker / reviewer / oracle
  ↓
LiteLLM gateway
  ↓
Upstream providers
  ↓
Langfuse traces
```

## What is active now

Configured locally:

- User default provider/model: `kilo-test` / `kilo-auto/frontier`.
- Project `.pi/settings.json`: same default provider/model and subagent context policy.
- MCP config includes lazy entries for:
  - `engram` — active memory server.
  - `serena` — symbol-level MCP server via `uvx`.
  - `graphify` — knowledge graph MCP companion via `npx graphify-mcp-tools mcp`.
- Serena CLI was verified via `uvx`.
- Graphify CLI and LiteLLM CLI are installed as user tools via `uv tool`.
- A local Graphify AST graph/search index exists in gitignored `graphify-out/`.
- Project routing skill: `skills/harness-orchestration-router/SKILL.md`.

The current Pi session may not hot-reload MCP server definitions. Restart Pi after config changes.

## Routing rules

Use the project skill `harness-orchestration-router` for non-trivial work. The intended policy is:

| Need | First tool/layer | Fallback |
| --- | --- | --- |
| Past decisions/preferences | Engram | OpenSpec/docs |
| Large repo/module impact | Graphify | scout/context-builder + file reads |
| Code symbol/reference work | Serena | pi-lens LSP |
| Pattern search/replacement | ast-grep | rg/edit |
| Multi-file implementation | worker subagent | parent + fresh reviewer |
| Review/commit/PR readiness | fresh reviewer | parent manual review |
| Model routing/cost/fallback | LiteLLM | direct Pi provider |
| LLM trace/cost evidence | Langfuse | Pi logs/manual notes |

## Serena MCP

Configured command:

```json
{
  "command": "C:\\Users\\jairo\\.local\\bin\\uvx.exe",
  "args": [
    "--from", "git+https://github.com/oraios/serena",
    "serena", "start-mcp-server",
    "--context=oaicompat-agent",
    "--project-from-cwd",
    "--open-web-dashboard=false"
  ]
}
```

Use Serena when the task involves symbols, references, methods, classes, or refactors. Do not use it as a reason to skip tests or fresh review.

## Graphify

Configured command:

```json
{
  "command": "npx",
  "args": ["-y", "graphify-mcp-tools", "mcp", "--graph", "graphify-out"],
  "env": {"PATH": "C:\\Users\\jairo\\.local\\bin;${PATH}"}
}
```

Use Graphify for large impact mapping, especially Odoo modules. Treat the graph as a map, not ground truth: verify final claims against files/tests.

Build or refresh the local graph:

```powershell
powershell -File scripts/pi/build_graphify_map.ps1
```

This runs AST-only extraction (`graphify update . --no-cluster`) and builds the MCP search index without needing LLM keys.

## LiteLLM + Langfuse

Example config lives at:

```text
configs/litellm/harnessci.yaml
```

Required env vars:

```powershell
$env:KILO_API_KEY = "..."
$env:LITELLM_MASTER_KEY = "..."
$env:LANGFUSE_PUBLIC_KEY = "..."
$env:LANGFUSE_SECRET_KEY = "..."
```

Start gateway:

```powershell
powershell -File scripts/pi/start_litellm_gateway.ps1
```

A `litellm` provider entry has been added to `~/.pi/agent/models.json`, but Pi remains on `kilo-test` until the gateway is reachable.

After the gateway is running, switch defaults conservatively:

```powershell
py scripts/pi/use_litellm_provider.py
```

The switch script refuses to change defaults unless `http://localhost:4000/v1/models` responds.

## Secret policy

- Do not commit API keys.
- Prefer env vars over literal keys in `models.json`.
- Revoke any token pasted into chat.
- Keep raw third-party diffs and candidate pools gitignored.

## HarnessCI boundary

Allowed external integration zones:

- `scripts/`
- `datasets/`
- local Pi/MCP/settings files
- docs/skills

Forbidden in deterministic product runtime:

- LLM provider imports
- Engram imports
- Gentle AI/Pi imports
- Langfuse/Helicone SDK imports
- GitHub API client imports

`src/harnessci/` may use only deterministic local inputs, config, parsing, scoring, subprocess `git diff` where already designed, and pure Python dependencies declared as runtime dependencies.
