"""Generate human-readable session autopsy narratives."""

from __future__ import annotations

from typing import Any

from harnessci.autopsy.analyzer import SessionInsight
from harnessci.autopsy.patterns import DEFAULT_COST_PER_TOKEN
from harnessci.models import AuditReport


class SessionNarrator:
    """Turn session insights and telemetry into a compact user-facing report."""

    def generate_report(
        self,
        insights: list[SessionInsight],
        report: AuditReport,
        trace: dict[str, Any],
    ) -> dict[str, Any]:
        """Return a serializable Spanish narrative for PR comments and JSON reports."""
        duration_min = _as_int(trace.get("latency_ms"), 0) // 60_000
        tokens = _as_int(trace.get("tokens"), 0)
        edit_attempts = _as_int(trace.get("edit_attempts"), 0)
        cost = trace.get("cost_estimate")
        if cost is None:
            cost = round(tokens * DEFAULT_COST_PER_TOKEN, 4)

        return {
            "headline": self._headline(insights),
            "tldr": self._tldr(insights, duration_min, tokens),
            "efficiency_score": self._efficiency_score(trace, report),
            "insights": [self._format_insight(i) for i in insights],
            "what_happened": self._narrative(insights),
            "next_time": self._recommendations(insights),
            "stats": {
                "duration_minutes": duration_min,
                "tokens_used": tokens,
                "edit_attempts": edit_attempts,
                "lines_changed": report.diff.total_churn,
                "cost_estimate": round(float(cost), 4),
            },
        }

    def _headline(self, insights: list[SessionInsight]) -> str:
        critical = [i for i in insights if i.severity == "critical"]
        if critical:
            return f"⚠️ Sesión problemática — {critical[0].title}"
        if not insights:
            return "✅ Sesión limpia y eficiente"
        return f"ℹ️ Sesión completada con {len(insights)} observación(es)"

    def _tldr(self, insights: list[SessionInsight], duration_min: int, tokens: int) -> str:
        if not insights:
            return (
                f"El agente completó la tarea en {duration_min} minutos usando "
                f"~{tokens:,} tokens sin señales problemáticas."
            )
        types = {i.type for i in insights}
        if "thrashing" in types:
            return (
                f"El agente tuvo dificultades: dio vueltas durante {duration_min} "
                "minutos antes de encontrar la solución."
            )
        return f"Tarea completada en {duration_min} min con {len(insights)} punto(s) a mejorar."

    def _efficiency_score(self, trace: dict[str, Any], report: AuditReport) -> int:
        """Return a simple 0-100 efficiency score, higher is better."""
        score = 100
        edit_attempts = _as_int(trace.get("edit_attempts"), 0)
        failed = _as_int(trace.get("failed_test_runs"), 0)
        runs = max(1, _as_int(trace.get("test_runs"), 1))
        retries = _as_int(trace.get("retries"), 0)

        if edit_attempts > 5:
            score -= 20
        if edit_attempts > 10:
            score -= 20
        if failed / runs > 0.4:
            score -= 25
        if retries > 3:
            score -= 15
        if report.diff.files_changed > 10:
            score -= 10

        return max(0, score)

    def _narrative(self, insights: list[SessionInsight]) -> str:
        if not insights:
            return "El agente navegó la tarea de forma directa."
        return " ".join(insight.explanation for insight in insights)

    def _recommendations(self, insights: list[SessionInsight]) -> list[str]:
        return [i.suggestion for i in insights if i.suggestion]

    def _format_insight(self, insight: SessionInsight) -> dict[str, Any]:
        icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        return {
            "icon": icons.get(insight.severity, "ℹ️"),
            "type": insight.type,
            "severity": insight.severity,
            "title": insight.title,
            "explanation": insight.explanation,
            "suggestion": insight.suggestion,
            "evidence": insight.evidence,
        }


def _as_int(value: Any, default: int) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
