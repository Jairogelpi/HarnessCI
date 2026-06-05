"""Best-effort collection and normalization of coding-agent trace files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harnessci.models import TelemetrySummary

TRACE_PATHS = [
    ".agent/trace.json",
    ".openhands/trajectory.json",
    ".harnessci/telemetry.json",
    ".cursor/session.json",
    ".claude/trace.jsonl",
]


class TraceCollector:
    """Collect the first available agent trace and normalize it to TelemetrySummary."""

    def __init__(self, trace_paths: list[str] | None = None) -> None:
        self.trace_paths = trace_paths or TRACE_PATHS

    def collect(self, repo_root: Path) -> TelemetrySummary:
        """Return normalized telemetry from the first readable trace path.

        Parsing is deliberately non-fatal: missing, invalid, or unsupported traces
        return unavailable telemetry instead of failing the audit.
        """
        root = Path(repo_root)
        for path in self.trace_paths:
            full = root / path
            if full.exists() and full.is_file():
                parsed = self._parse(full)
                if parsed.available:
                    return parsed
        return TelemetrySummary(available=False)

    def _parse(self, path: Path) -> TelemetrySummary:
        try:
            if path.suffix == ".jsonl":
                data = self._parse_jsonl(path)
            else:
                data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            return TelemetrySummary(available=False)

        try:
            return self._normalize(data, source_path=str(path))
        except Exception:  # noqa: BLE001
            return TelemetrySummary(available=False)

    def _parse_jsonl(self, path: Path) -> dict[str, Any]:
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict):
                events.append(event)
        return _aggregate_jsonl_events(events)

    def _normalize(self, data: Any, source_path: str | None = None) -> TelemetrySummary:
        if isinstance(data, list):
            data = _aggregate_jsonl_events([item for item in data if isinstance(item, dict)])
        if not isinstance(data, dict):
            return TelemetrySummary(available=False)

        execution = _first_dict(data, "execution", "metrics", "stats", "summary")
        agent = _first_dict(data, "agent")
        harness = _first_dict(data, "harness")

        tokens_in = _number(_get_any(execution, data, keys=("tokens_in", "input_tokens")))
        tokens_out = _number(_get_any(execution, data, keys=("tokens_out", "output_tokens")))
        tokens = _number(_get_any(execution, data, keys=("tokens", "total_tokens", "token_count")))
        if tokens is None and (tokens_in is not None or tokens_out is not None):
            tokens = (tokens_in or 0) + (tokens_out or 0)

        edit_attempts = _number(
            _get_any(execution, data, keys=("edit_attempts", "file_writes", "edits", "writes"))
        )
        retries = _number(_get_any(execution, data, harness, keys=("retries", "tool_retries")))
        error_count = _number(
            _get_any(execution, data, keys=("error_count", "errors", "errorCount"))
        )

        fields = {
            "available": True,
            "agent_name": _str_or_none(
                _get_any(agent, data, keys=("name", "agent_name", "agentName"))
            ),
            "model_name": _str_or_none(
                _get_any(agent, data, keys=("model", "model_name", "modelName"))
            ),
            "harness_type": _str_or_none(
                _get_any(harness, data, keys=("name", "harness_type", "harnessType"))
            ),
            "tool_calls": _number(
                _get_any(execution, data, keys=("tool_calls", "toolCalls", "steps"))
            ),
            "test_runs": _number(_get_any(execution, data, keys=("test_runs", "testRuns"))),
            "failed_test_runs": _number(
                _get_any(
                    execution,
                    data,
                    keys=("failed_test_runs", "failedTestRuns", "test_failures"),
                )
            ),
            "edit_attempts": edit_attempts,
            "retries": retries,
            "tokens": tokens,
            "latency_ms": _number(
                _get_any(execution, data, keys=("latency_ms", "latencyMs", "duration_ms"))
            ),
            "error_count": error_count,
            "cost_estimate": _float_or_none(
                _get_any(execution, data, keys=("cost_estimate", "costEstimate", "cost"))
            ),
        }

        # Keep an otherwise-empty trace unavailable unless it has at least one signal.
        if not any(value is not None for key, value in fields.items() if key != "available"):
            return TelemetrySummary(available=False)

        return TelemetrySummary(**fields)


def normalize_telemetry(value: TelemetrySummary | dict[str, Any] | None) -> TelemetrySummary:
    """Normalize an explicit telemetry argument for audit APIs."""
    if value is None:
        return TelemetrySummary(available=False)
    if isinstance(value, TelemetrySummary):
        return value
    if isinstance(value, dict):
        return TraceCollector()._normalize(value)
    return TelemetrySummary(available=False)


def _aggregate_jsonl_events(events: list[dict[str, Any]]) -> dict[str, Any]:
    tool_calls = 0
    edit_attempts = 0
    test_runs = 0
    failed_test_runs = 0
    error_count = 0
    tokens = 0
    latency_ms = 0
    agent_name: str | None = None
    model_name: str | None = None

    for event in events:
        agent_name = agent_name or _str_or_none(_get_nested(event, ("agent", "name")))
        model_name = model_name or _str_or_none(_get_nested(event, ("agent", "model")))
        model_name = model_name or _str_or_none(event.get("model"))

        usage = _first_dict(event, "usage", "token_usage")
        event_tokens = _number(event.get("tokens")) or 0
        event_tokens += _number(usage.get("input_tokens")) or 0
        event_tokens += _number(usage.get("output_tokens")) or 0
        event_tokens += _number(usage.get("cache_creation_input_tokens")) or 0
        event_tokens += _number(usage.get("cache_read_input_tokens")) or 0
        tokens += event_tokens

        latency_ms += _number(event.get("latency_ms")) or _number(event.get("duration_ms")) or 0

        tool_name = _extract_tool_name(event)
        command = str(event.get("command") or event.get("input") or "").lower()
        if tool_name:
            tool_calls += 1
        if tool_name in {"edit", "multiedit", "write", "notebookedit"}:
            edit_attempts += 1
        if _looks_like_test(tool_name, command):
            test_runs += 1
            if _event_failed(event):
                failed_test_runs += 1
        if event.get("error") or event.get("is_error") or event.get("level") == "error":
            error_count += 1

    return {
        "agent": {"name": agent_name, "model": model_name},
        "execution": {
            "tool_calls": tool_calls or None,
            "edit_attempts": edit_attempts or None,
            "test_runs": test_runs or None,
            "failed_test_runs": failed_test_runs or None,
            "tokens": tokens or None,
            "latency_ms": latency_ms or None,
            "errors": error_count or None,
        },
    }


def _extract_tool_name(event: dict[str, Any]) -> str | None:
    candidates = [
        event.get("tool_name"),
        event.get("name"),
        _get_nested(event, ("tool", "name")),
        _get_nested(event, ("message", "tool_name")),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip().lower()
    return None


def _looks_like_test(tool_name: str | None, command: str) -> bool:
    if tool_name not in {"bash", "shell", "run", "terminal"}:
        return False
    test_markers = ("pytest", "npm test", "pnpm test", "yarn test", "cargo test")
    return any(marker in command for marker in test_markers)


def _event_failed(event: dict[str, Any]) -> bool:
    exit_code = _number(
        event.get("exit_code") or event.get("returncode") or event.get("status_code")
    )
    if exit_code is not None:
        return exit_code != 0
    return bool(event.get("failed") or event.get("is_error") or event.get("error"))


def _first_dict(source: Any, *keys: str) -> dict[str, Any]:
    if not isinstance(source, dict):
        return {}
    if not keys:
        return source
    for key in keys:
        value = source.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _get_any(*sources: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in keys:
            if key in source:
                return source[key]
    return None


def _get_nested(source: dict[str, Any], path: tuple[str, ...]) -> Any:
    current: Any = source
    for part in path:
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def _number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _float_or_none(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
