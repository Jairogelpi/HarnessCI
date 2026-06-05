"""Analyze coding-agent session telemetry for human-readable failure modes."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnessci.autopsy.patterns import (
    CONTEXT_GAP_MAX_CHURN,
    CONTEXT_GAP_MIN_LATENCY_MS,
    INEFFICIENCY_MIN_TOKENS,
    INEFFICIENCY_MIN_TOKENS_PER_LINE,
    SCOPE_CREEP_MIN_FILES_CHANGED,
    SCOPE_CREEP_MIN_RETRIES,
    THRASHING_MIN_EDIT_ATTEMPTS,
    THRASHING_MIN_FAIL_RATIO,
)
from harnessci.models import DiffFeatures


@dataclass(frozen=True)
class SessionInsight:
    """One detected session behavior pattern with explanation and evidence."""

    type: str
    severity: str
    title: str
    explanation: str
    evidence: dict[str, Any]
    suggestion: str


class SessionAnalyzer:
    """Detect problem patterns from normalized telemetry and diff features."""

    def analyze(
        self,
        trace: dict[str, Any],
        diff_features: DiffFeatures | None,
    ) -> list[SessionInsight]:
        insights: list[SessionInsight] = []
        insights.extend(self._detect_thrashing(trace))
        insights.extend(self._detect_context_gap(trace, diff_features))
        insights.extend(self._detect_inefficiency(trace, diff_features))
        insights.extend(self._detect_scope_creep_pattern(trace, diff_features))
        return insights

    def _detect_thrashing(self, trace: dict[str, Any]) -> list[SessionInsight]:
        """Detect repeated editing plus high test failure ratio."""
        edit_attempts = _as_int(trace.get("edit_attempts"), 0)
        failed_runs = _as_int(trace.get("failed_test_runs"), 0)
        total_runs = _as_int(trace.get("test_runs"), 0)
        fail_ratio = failed_runs / total_runs if total_runs > 0 else 0.0

        if edit_attempts >= THRASHING_MIN_EDIT_ATTEMPTS and fail_ratio >= THRASHING_MIN_FAIL_RATIO:
            return [
                SessionInsight(
                    type="thrashing",
                    severity="critical",
                    title="El agente dio vueltas en círculos",
                    explanation=(
                        f"Con {edit_attempts} intentos de edición y "
                        f"{failed_runs}/{total_runs} tests fallando, el agente no encontró "
                        "el camino correcto de forma directa."
                    ),
                    evidence={"edit_attempts": edit_attempts, "fail_ratio": round(fail_ratio, 3)},
                    suggestion=(
                        "Prueba a dar más contexto sobre la arquitectura al inicio de la "
                        "sesión. El agente probablemente no entendió una dependencia clave."
                    ),
                )
            ]
        return []

    def _detect_context_gap(
        self,
        trace: dict[str, Any],
        diff_features: DiffFeatures | None,
    ) -> list[SessionInsight]:
        """Detect long sessions for a small diff."""
        latency_ms = _as_int(trace.get("latency_ms"), 0)
        churn = diff_features.total_churn if diff_features else 0

        if latency_ms > CONTEXT_GAP_MIN_LATENCY_MS and churn < CONTEXT_GAP_MAX_CHURN:
            minutes = latency_ms // 60_000
            return [
                SessionInsight(
                    type="context_gap",
                    severity="warning",
                    title=f"{minutes} minutos para {churn} líneas",
                    explanation=(
                        f"El cambio fue pequeño pero el agente tardó {minutes} minutos. "
                        "Esto suele indicar que el agente no tenía suficiente contexto "
                        "sobre cómo funciona esta parte del sistema."
                    ),
                    evidence={"latency_minutes": minutes, "lines_changed": churn},
                    suggestion=(
                        "Añade un comentario explicativo en el fichero o menciona "
                        "explícitamente la arquitectura relevante al pedir el cambio."
                    ),
                )
            ]
        return []

    def _detect_inefficiency(
        self,
        trace: dict[str, Any],
        diff_features: DiffFeatures | None,
    ) -> list[SessionInsight]:
        """Detect unusually high token spend per changed line."""
        tokens = _as_int(trace.get("tokens"), 0)
        churn = diff_features.total_churn if diff_features and diff_features.total_churn > 0 else 1
        ratio = tokens / churn if churn > 0 else 0.0

        if ratio > INEFFICIENCY_MIN_TOKENS_PER_LINE and tokens > INEFFICIENCY_MIN_TOKENS:
            return [
                SessionInsight(
                    type="inefficiency",
                    severity="info",
                    title="Sesión cara para el resultado obtenido",
                    explanation=(
                        f"Se usaron ~{tokens:,} tokens para producir {churn} líneas. "
                        f"Eso es {ratio:.0f} tokens por línea, inusualmente alto."
                    ),
                    evidence={"tokens": tokens, "ratio": round(ratio, 2)},
                    suggestion=(
                        "Considera dividir tareas grandes en subtareas más pequeñas. "
                        "El agente es más eficiente con instrucciones acotadas."
                    ),
                )
            ]
        return []

    def _detect_scope_creep_pattern(
        self,
        trace: dict[str, Any],
        diff_features: DiffFeatures | None,
    ) -> list[SessionInsight]:
        """Detect retry-heavy sessions that spread across many files."""
        retries = _as_int(trace.get("retries"), 0)
        files = diff_features.files_changed if diff_features else 0

        if retries >= SCOPE_CREEP_MIN_RETRIES and files > SCOPE_CREEP_MIN_FILES_CHANGED:
            return [
                SessionInsight(
                    type="scope_creep_pattern",
                    severity="warning",
                    title="El agente expandió el alcance mientras trabajaba",
                    explanation=(
                        f"Con {retries} reintentos y {files} ficheros cambiados, parece "
                        "que el agente fue expandiendo el alcance según encontraba "
                        "problemas relacionados."
                    ),
                    evidence={"retries": retries, "files_changed": files},
                    suggestion=(
                        "Usa instrucciones más restrictivas: "
                        "'Modifica SOLO estos ficheros: X, Y, Z'."
                    ),
                )
            ]
        return []


def _as_int(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
