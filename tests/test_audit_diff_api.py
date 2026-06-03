"""Tests for pure diff audit API."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

SAMPLE_DIFF = """diff --git a/app.py b/app.py
index e69de29..9daeafb 100644
--- a/app.py
+++ b/app.py
@@ -0,0 +1,2 @@
+def login():
+    return True
"""


def _audit_module():
    return importlib.import_module("harnessci.audit")


def _models_module():
    return importlib.import_module("harnessci.models")


def test_run_audit_from_diff_text_returns_report_without_git(monkeypatch):
    """The pure API audits loaded diff text and never calls subprocess/git."""

    def fail_subprocess_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("run_audit_from_diff_text must not call subprocess.run")

    monkeypatch.setattr(subprocess, "run", fail_subprocess_run)

    audit = _audit_module()
    models = _models_module()
    report = audit.run_audit_from_diff_text(SAMPLE_DIFF)

    assert isinstance(report, models.AuditReport)
    assert report.decision == models.Decision.INSUFFICIENT_INFORMATION
    assert report.diff.files_changed == 1
    assert report.diff.lines_added == 2
    assert report.diff.lines_deleted == 0
    assert report.metadata["source"] == "diff_text"
    assert report.metadata["diff_bytes"] == len(SAMPLE_DIFF.encode("utf-8"))
    assert "diff_sha256" in report.metadata


def test_run_audit_from_diff_text_uses_optional_spec(tmp_path: Path):
    spec = tmp_path / "spec.md"
    spec.write_text(
        """# Goal
Fix login

## Acceptance Criteria
- Login returns a successful result.
""",
        encoding="utf-8",
    )

    report = _audit_module().run_audit_from_diff_text(SAMPLE_DIFF, spec_path=spec)

    assert report.spec.usable is True
    assert report.spec.goal == "Fix login"
    assert report.metadata["source"] == "diff_text"
