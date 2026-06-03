"""Markdown report renderer for HarnessCI.

Produces the canonical HarnessCI Audit comment format.
"""

from __future__ import annotations

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

    # Recommendation
    lines.append("### Recommendation")
    lines.append("")
    lines.append(report.recommendation)

    return "\n".join(lines)
