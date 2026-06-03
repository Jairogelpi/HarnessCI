"""JSON report renderer for HarnessCI."""

from __future__ import annotations

from harnessci.models import AuditReport


def render_json(report: AuditReport) -> str:
    """Return the audit report serialised as indented JSON."""
    return report.model_dump_json(indent=2)
