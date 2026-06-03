"""Tests for CLI command (PR5)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_git_repo(tmp_path: Path) -> tuple[Path, str, str]:
    """Create a minimal git repo with two commits; return (repo_path, base_sha, head_sha)."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _run = lambda *args: subprocess.run(  # noqa: E731
        list(args), cwd=repo, check=True, capture_output=True
    )
    _run("git", "init")
    _run("git", "config", "user.email", "test@test.com")
    _run("git", "config", "user.name", "Test")

    (repo / "app.py").write_text("def login(): pass\n", encoding="utf-8")
    _run("git", "add", ".")
    _run("git", "commit", "-m", "base")
    base = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    (repo / "app.py").write_text("def login():\n    return redirect('/home')\n", encoding="utf-8")
    _run("git", "add", ".")
    _run("git", "commit", "-m", "fix login")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()

    return repo, base, head


def _run_main(argv: list[str], cwd: Path | None = None) -> int:
    """Set sys.argv, optionally chdir, call main(), restore state. Return exit code."""
    from harnessci.cli import main  # noqa: PLC0415

    orig_argv = sys.argv
    orig_cwd = os.getcwd()
    sys.argv = argv
    if cwd:
        os.chdir(cwd)
    try:
        main()
        return 0
    except SystemExit as exc:
        code = exc.code
        return int(code) if isinstance(code, int) else 0
    finally:
        sys.argv = orig_argv
        if cwd:
            os.chdir(orig_cwd)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCliHelp:
    def test_help_exits_zero(self):
        code = _run_main(["harnessci", "audit", "--help"])
        assert code == 0


class TestCliMissingArgs:
    def test_missing_base_exits_nonzero(self):
        code = _run_main(["harnessci", "audit", "--head", "HEAD"])
        assert code != 0

    def test_missing_head_exits_nonzero(self):
        code = _run_main(["harnessci", "audit", "--base", "HEAD~1"])
        assert code != 0


class TestCliHappyPath:
    def test_writes_json_output(self, tmp_path: Path):
        repo, base, head = _make_git_repo(tmp_path)
        out_json = tmp_path / "report.json"
        code = _run_main(
            ["harnessci", "audit", "--base", base, "--head", head, "--output", str(out_json)],
            cwd=repo,
        )
        assert code in (0, None), f"Unexpected exit code: {code}"
        assert out_json.exists(), "JSON output file not created"
        parsed = json.loads(out_json.read_text(encoding="utf-8"))
        assert "decision" in parsed
        assert "overall_agentic_risk" in parsed
        assert "scores" in parsed

    def test_writes_markdown_output(self, tmp_path: Path):
        repo, base, head = _make_git_repo(tmp_path)
        out_md = tmp_path / "report.md"
        code = _run_main(
            [
                "harnessci",
                "audit",
                "--base",
                base,
                "--head",
                head,
                "--markdown-output",
                str(out_md),
            ],
            cwd=repo,
        )
        assert code in (0, None), f"Unexpected exit code: {code}"
        assert out_md.exists(), "Markdown output file not created"
        content = out_md.read_text(encoding="utf-8")
        assert "## HarnessCI Audit" in content
