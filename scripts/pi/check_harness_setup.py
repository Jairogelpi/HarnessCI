"""Check local Pi/Gentle AI harness setup without exposing secrets."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

HOME = Path.home()
REPO = Path(__file__).resolve().parents[2]

ROUTER_SKILL = REPO / "skills" / "harness-orchestration-router" / "SKILL.md"
LITELLM_CONFIG = REPO / "configs" / "litellm" / "harnessci.yaml"
GRAPHIFY_OUT = REPO / "graphify-out" / "graph.json"
GRAPHIFY_SEARCH = REPO / "graphify-out" / "graph_search.db"
UVX_EXE = HOME / ".local" / "bin" / "uvx.exe"
GRAPHIFY_EXE = HOME / ".local" / "bin" / "graphify.exe"


def has_langfuse_env() -> bool:
    return bool(os.environ.get("LANGFUSE_PUBLIC_KEY")) and bool(
        os.environ.get("LANGFUSE_SECRET_KEY")
    )


REQUIRED_CHECKS = [
    ("uvx", lambda: shutil.which("uvx") or UVX_EXE.exists()),
    ("npx", lambda: shutil.which("npx") is not None),
    ("litellm_cli", lambda: shutil.which("litellm") is not None),
    ("graphify_cli", lambda: shutil.which("graphify") or GRAPHIFY_EXE.exists()),
    ("graphify_graph", lambda: GRAPHIFY_OUT.exists()),
    ("graphify_search_index", lambda: GRAPHIFY_SEARCH.exists()),
    ("engram_mcp_config", lambda: has_mcp_server("engram")),
    ("serena_mcp_config", lambda: has_mcp_server("serena")),
    ("graphify_mcp_config", lambda: has_mcp_server("graphify")),
    ("project_router_skill", lambda: ROUTER_SKILL.exists()),
    ("litellm_config", lambda: LITELLM_CONFIG.exists()),
]

OPTIONAL_SECRET_CHECKS = [
    ("kilo_api_env", lambda: bool(os.environ.get("KILO_API_KEY"))),
    ("litellm_master_env", lambda: bool(os.environ.get("LITELLM_MASTER_KEY"))),
    ("langfuse_env", has_langfuse_env),
]


def main() -> int:
    print("Harness setup check")
    print(f"repo={REPO}")
    required_failures = run_checks("Required", REQUIRED_CHECKS)
    optional_missing = run_checks("Activation secrets", OPTIONAL_SECRET_CHECKS)

    print()
    if required_failures:
        print(f"{required_failures} required harness checks are missing.")
        print("See docs/ai_harness_setup.md for setup steps.")
        return 1
    if optional_missing:
        print(f"Required harness infrastructure is ready; {optional_missing} secrets are pending.")
        print("LiteLLM/Langfuse activation waits for env vars. This is expected if unset.")
        return 0
    print("All harness checks passed, including activation secrets.")
    return 0


def run_checks(title: str, checks: list[tuple[str, Any]]) -> int:
    print(title)
    failures = 0
    for name, check in checks:
        try:
            ok = bool(check())
        except Exception:  # noqa: BLE001 - diagnostic script should continue
            ok = False
        mark = "OK" if ok else "MISSING"
        if not ok:
            failures += 1
        print(f"[{mark:7s}] {name}")
    return failures


def has_mcp_server(name: str) -> bool:
    path = HOME / ".pi" / "agent" / "mcp.json"
    if not path.exists():
        return False
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return name in data.get("mcpServers", {})


if __name__ == "__main__":
    raise SystemExit(main())
