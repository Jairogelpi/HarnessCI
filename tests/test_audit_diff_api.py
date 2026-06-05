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

TEST_DIFF = """diff --git a/tests/test_app.py b/tests/test_app.py
new file mode 100644
index 0000000..9daeafb
--- /dev/null
+++ b/tests/test_app.py
@@ -0,0 +1,2 @@
+def test_login():
+    assert True
"""


def _audit_module():
    return importlib.import_module("harnessci.audit")


def _models_module():
    return importlib.import_module("harnessci.models")


def test_run_audit_from_diff_text_returns_report_without_git(monkeypatch):
    """The pure API audits loaded diff text and never calls subprocess/git."""

    def fail_subprocess_run(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("run_audit_from_diff_text must not call subprocess.run")

    def fail_trace_collection(*args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        raise AssertionError("run_audit_from_diff_text must not collect filesystem telemetry")

    monkeypatch.setattr(subprocess, "run", fail_subprocess_run)
    monkeypatch.setattr("harnessci.audit.TraceCollector.collect", fail_trace_collection)

    # Disable auto-detection of mined spec (test should not depend on repo state)
    def _fake_spec_exists(_root):
        return False

    monkeypatch.setattr("harnessci.spec_inference.spec_exists", _fake_spec_exists)

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


def test_run_audit_from_diff_text_derives_test_signals_from_diff():
    report = _audit_module().run_audit_from_diff_text(TEST_DIFF, spec_text="# Goal\nAdd tests")

    assert report.diff.test_files_changed == 1
    assert report.test_signals.new_tests_added is True
    assert report.test_signals.changed_tests == 1


def test_run_audit_from_diff_text_accepts_explicit_telemetry():
    report = _audit_module().run_audit_from_diff_text(
        SAMPLE_DIFF,
        spec_text="# Goal\nFix login",
        telemetry={
            "available": True,
            "edit_attempts": 11,
            "test_runs": 10,
            "failed_test_runs": 7,
            "tokens": 47_000,
            "latency_ms": 1_380_000,
        },
    )

    assert report.telemetry.available is True
    assert report.session_autopsy is not None
    assert report.session_autopsy["efficiency_score"] < 50
    assert "vueltas" in report.session_autopsy["headline"]
