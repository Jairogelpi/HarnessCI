---
name: harness-orchestration-router
description: Use for non-trivial coding, repo exploration, Odoo/custom addon work, HarnessCI dataset/evaluation, PR review, or model/harness setup. Routes context through Engram, Serena, Graphify, pi-lens, subagents, LiteLLM, and Langfuse without bloating prompts or compromising determinism.
---

# Harness Orchestration Router

Use this skill before substantial work in this project or in large customer repos.
It tells the agent which context/intelligence layer to use and when.

## Core Rule

Use the smallest reliable context layer. Do not read raw files until a more precise tool cannot answer the question.

```text
Memory first → repo map/symbols → precise files → edits → fresh review → validation
```

HarnessCI product code must remain deterministic. Do not add Gentle AI, Engram, MCP, LiteLLM, Langfuse, GitHub API, or LLM provider imports to `src/harnessci/` runtime paths.

## Routing Ladder

### 1. Memory / history

Use Engram when the question depends on previous decisions, preferences, architecture, or prior bugs.

Examples:
- “What did we decide about Odoo 19?”
- “How did we configure staging?”
- “Why is HarnessCI deterministic?”
- “Continue the TFM/dataset work.”

Protocol:
1. Parent calls memory context/search.
2. Parent passes only relevant observations to subagents.
3. Save significant discoveries/decisions/bugfixes after the work.

### 2. Repo map / impact map

Use Graphify when the task asks “what is connected to this?” or the repo is large/multimodal.

Best triggers:
- Odoo module impact: manifests, models, XML views, security, data, reports.
- “What will this change touch?”
- “Map this repo/module before planning.”
- Cross-cutting changes across 4+ files or multiple subsystems.

Use Graphify for broad structure, then verify with real files via Serena/pi-lens/read.
Do not rely on a graph alone for final correctness.

### 3. Symbol navigation

Use Serena when the task involves code symbols, references, methods, classes, refactors, or large code navigation.

Best triggers:
- Find class/method definitions.
- Find references/callers.
- Rename/move/refactor by symbol.
- Understand a model/service/controller without opening many files.

Fallback: if Serena is unavailable, use pi-lens LSP (`lsp_navigation`, `lsp_diagnostics`) and ast-grep.

### 4. Structural search / diagnostics

Use pi-lens for precise code intelligence:

- `lsp_navigation` for definitions, references, symbols, call hierarchy.
- `lsp_diagnostics` before builds/tests.
- `ast_grep_search` before grep when searching code patterns.
- `ast_grep_replace` for mechanical AST-safe replacements.

Use `rg` only for plain text, docs, config, or when AST/LSP are not suitable.

### 5. Subagents

Delegate when work would inflate parent context:

- 4+ files to understand → `scout` or `context-builder`.
- 2+ non-trivial files to write → one `worker`, then fresh `reviewer`.
- PR/commit/push after code changes → fresh `reviewer` first.
- Incidents/tooling confusion → fresh audit reviewer.

One writer at a time. Parallel readers are OK; parallel writers require isolated worktrees and explicit approval.

### 6. Model gateway / observability

Pi should route models through LiteLLM when available:

```text
Pi → LiteLLM → upstream providers
```

Use model tiers:
- cheap/fast model: scouting, simple docs, low-risk summaries.
- frontier model: architecture, implementation, review, debugging, SDD phases.

Langfuse/Helicone traces are for harness observability and TFM evidence. Do not insert observability SDKs into HarnessCI deterministic runtime code.

## Odoo-Specific Routing

For Odoo work:

1. Load the version-specific Odoo skill.
2. Use Graphify to map module dependencies if available.
3. Use Serena/pi-lens for Python symbols and references.
4. Use XML-aware/text search for views, actions, security, and data records.
5. Always inspect manifests and security files for module changes.
6. Run relevant Odoo tests or at minimum static checks; record what could not be validated.

## HarnessCI-Specific Routing

For HarnessCI product work:

1. Read project memory for decisions and constraints.
2. Preserve deterministic boundary:
   - `src/harnessci/` has no LLM/GitHub/Gentle/Engram runtime imports.
   - Dataset/build/eval scripts may use external APIs if documented.
3. Use strict tests before claiming completion.
4. Save methodology discoveries to Engram.
5. Document proxy labels and limitations honestly.

## Completion Checklist

Before final response:

- Did the context source match the task size?
- Were broad graph/memory claims verified against files or tests?
- Were raw diffs, secrets, and third-party code kept out of commits?
- Did tests/lints or next-best validation run?
- Was a significant decision/discovery saved to memory?
