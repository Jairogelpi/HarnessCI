"""Markdown report renderer for HarnessCI.

Produces the canonical HarnessCI Audit comment format.
"""

from __future__ import annotations

from typing import Any

from harnessci.models import AuditReport

# ---------------------------------------------------------------------------
# Status label helpers
# ---------------------------------------------------------------------------

# Quality scores (spec, diff, test, harness): higher = better
# Risk scores (security, architecture): higher = worse
# Both use the same band labels but the caller controls polarity.


def _quality_label(score: int) -> str:
    """Label for a quality score (higher is better): Low/Medium/High."""
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


def _risk_label(score: int) -> str:
    """Label for a risk score (higher is worse): Low/Medium/High."""
    if score >= 70:
        return "High"
    if score >= 40:
        return "Medium"
    return "Low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_markdown(report: AuditReport) -> str:
    """Render an AuditReport as a Markdown comment."""
    s = report.scores
    lines: list[str] = []

    lines.append("## HarnessCI Audit")
    lines.append("")
    lines.append(f"**Decision:** {report.decision}")
    lines.append(f"**Overall Agentic Risk:** {report.overall_agentic_risk}/100")
    lines.append("")

    # Score table
    lines.append("| Dimension | Score | Status |")
    lines.append("|---|---:|---|")
    lines.append(
        f"| Spec compliance | {s.spec_compliance_score} "
        f"| {_quality_label(s.spec_compliance_score)} |"
    )
    lines.append(
        f"| Diff minimality | {s.diff_minimality_score} "
        f"| {_quality_label(s.diff_minimality_score)} |"
    )
    lines.append(
        f"| Test adequacy | {s.test_adequacy_score} | {_quality_label(s.test_adequacy_score)} |"
    )
    lines.append(
        f"| Security risk | {s.security_risk_score} | {_risk_label(s.security_risk_score)} |"
    )
    lines.append(
        f"| Architecture drift | {s.architecture_drift_score} "
        f"| {_risk_label(s.architecture_drift_score)} |"
    )
    lines.append(
        f"| Harness efficiency | {s.harness_efficiency_score} "
        f"| {_quality_label(s.harness_efficiency_score)} |"
    )
    lines.append("")

    # Findings
    if report.findings:
        lines.append("### Main Findings")
        lines.append("")
        for i, finding in enumerate(report.findings, start=1):
            lines.append(f"{i}. {finding.message}")
        lines.append("")

    # Session autopsy
    if report.session_autopsy:
        _append_session_autopsy(lines, report.session_autopsy)

    # Recommendation
    lines.append("### Recommendation")
    lines.append("")
    lines.append(report.recommendation)

    return "\n".join(lines)


def _append_session_autopsy(lines: list[str], autopsy: dict) -> None:
    """Append a concise Spanish session-autopsy section."""
    stats = autopsy.get("stats", {}) if isinstance(autopsy.get("stats"), dict) else {}
    insights = autopsy.get("insights", []) if isinstance(autopsy.get("insights"), list) else []
    recommendations = autopsy.get("next_time", [])
    if not isinstance(recommendations, list):
        recommendations = []

    lines.append("## 🔬 Autopsia de Sesión")
    lines.append("")
    lines.append(f"**{_safe_text(autopsy.get('headline'), 'Sesión analizada')}**")
    lines.append("")
    tldr = _safe_text(autopsy.get("tldr"), "")
    if tldr:
        lines.append(tldr)
        lines.append("")

    lines.append("| Métrica | Valor |")
    lines.append("|---|---:|")
    lines.append(f"| Duración | {_safe_int(stats.get('duration_minutes'))} min |")
    lines.append(f"| Tokens usados | ~{_safe_int(stats.get('tokens_used')):,} |")
    lines.append(f"| Intentos de edición | {_safe_int(stats.get('edit_attempts'))} |")
    lines.append(f"| Líneas cambiadas | {_safe_int(stats.get('lines_changed'))} |")
    lines.append(f"| Coste estimado | ${_safe_float(stats.get('cost_estimate')):.4f} |")
    lines.append(f"| Score de eficiencia | {_safe_int(autopsy.get('efficiency_score'))}/100 |")
    lines.append("")

    for insight in insights[:3]:
        if not isinstance(insight, dict):
            continue
        title = _safe_text(insight.get("title"), "")
        explanation = _safe_text(insight.get("explanation"), "")
        icon = _safe_text(insight.get("icon"), "ℹ️")
        if title:
            lines.append(f"### {icon} {title}")
            lines.append("")
        if explanation:
            lines.append(explanation)
            lines.append("")

    if recommendations:
        lines.append("### 💡 Para la próxima vez")
        lines.append("")
        for recommendation in recommendations[:3]:
            text = _safe_text(recommendation, "")
            if text:
                lines.append(f"> {text}")
        lines.append("")


def _safe_int(value: Any, default: int = 0) -> int:
    if value is None or isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    if value is None or isinstance(value, bool):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_text(value: Any, default: str) -> str:
    if value is None:
        return default
    return str(value).replace("\n", " ").replace("|", "¦").strip()
