"""Configuration loading for HarnessCI.

Supports YAML config files with deep-merge against built-in defaults.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

from .errors import HarnessCIError

# ---------------------------------------------------------------------------
# ConfigError
# ---------------------------------------------------------------------------


class ConfigError(HarnessCIError):
    """Raised when a config file cannot be read or parsed."""


# ---------------------------------------------------------------------------
# Default configuration
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "name": "unknown",
        "language": "python",
    },
    "spec": {
        "paths": [".agent/spec.md", "docs/spec.md"],
        "use_issue_body": False,
        "use_pr_body": False,
    },
    "checks": {
        "run_tests": False,
        "test_command": None,
        "run_lint": False,
        "run_coverage": False,
        "run_security": False,
    },
    "risk": {
        "strictness": "medium",
        "block_on_failed_tests": True,
        "block_on_security_critical": True,
        "require_tests_for_sensitive_changes": True,
    },
    "telemetry": {
        "enabled": True,
        "paths": [".agent/trace.json", ".harnessci/telemetry.json"],
    },
    "judge": {
        "enabled": False,
    },
    "report": {
        "comment_on_pr": False,
        "upload_artifact": False,
        "fail_check_on_block": False,
    },
}


# ---------------------------------------------------------------------------
# Deep merge helper
# ---------------------------------------------------------------------------


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return a new dict: base with override values applied recursively."""
    result = copy.deepcopy(base)
    for key, val in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(val, dict):
            result[key] = _deep_merge(result[key], val)
        else:
            result[key] = copy.deepcopy(val)
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load HarnessCI configuration from *path*.

    - If *path* is None or does not exist: return a deep copy of DEFAULT_CONFIG.
    - If *path* exists: read YAML and deep-merge with defaults (user values win).
    - If the file cannot be read or the YAML is invalid: raise ConfigError.
    """
    if path is None:
        return copy.deepcopy(DEFAULT_CONFIG)

    config_path = Path(path)
    if not config_path.exists():
        return copy.deepcopy(DEFAULT_CONFIG)

    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"Cannot read config file: {config_path}") from exc

    try:
        user_config = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in config file {config_path}: {exc}") from exc

    if not isinstance(user_config, dict):
        kind = type(user_config).__name__
        raise ConfigError(f"Config file {config_path} must contain a YAML mapping, got {kind}")

    return _deep_merge(DEFAULT_CONFIG, user_config)
