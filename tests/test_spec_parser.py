from pathlib import Path

from harnessci.models import ExpectedScope
from harnessci.spec import parse_spec_file, parse_spec_text


def test_parse_documented_task_spec() -> None:
    spec = parse_spec_text(
        """
## Goal
Fix the login redirect bug when a user session expires.
## Acceptance Criteria
- Expired sessions redirect to /login.
- Active sessions continue normally.
## Out of Scope
- Authentication provider refactor.
## Risk Areas
- auth/session.py
## Expected Scope
small bugfix
""",
        source_path=".agent/spec.md",
    )

    assert spec.source_path == ".agent/spec.md"
    assert spec.goal == "Fix the login redirect bug when a user session expires."
    assert spec.acceptance_criteria == [
        "Expired sessions redirect to /login.",
        "Active sessions continue normally.",
    ]
    assert spec.out_of_scope == ["Authentication provider refactor."]
    assert spec.risk_areas == ["auth/session.py"]
    assert spec.expected_scope == ExpectedScope.SMALL_BUGFIX
    assert spec.usable is True


def test_parse_variants_and_unusable_specs() -> None:
    usable = parse_spec_text(
        "## goal\nShip audit scaffold.\n## acceptance-criterion\n* Imports package.\n"
        "## risk_area\n- src/harnessci/__init__.py"
    )
    unusable = parse_spec_text("# Notes\nContext only.\n## Out Of Scope\n- Billing changes")

    assert usable.acceptance_criteria == ["Imports package."]
    assert usable.risk_areas == ["src/harnessci/__init__.py"]
    assert usable.expected_scope == ExpectedScope.UNKNOWN
    assert usable.usable is True
    assert unusable.goal == ""
    assert unusable.acceptance_criteria == []
    assert unusable.out_of_scope == ["Billing changes"]
    assert unusable.usable is False


def test_parse_spec_file_reads_path(tmp_path: Path) -> None:
    spec_path = tmp_path / "task.md"
    spec_path.write_text(
        "## Goal\nFix auth redirect.\n\n## Acceptance Criteria\n- Redirect expired sessions.",
        encoding="utf-8",
    )

    spec = parse_spec_file(spec_path)

    assert spec.source_path == str(spec_path)
    assert spec.goal == "Fix auth redirect."
    assert spec.acceptance_criteria == ["Redirect expired sessions."]
