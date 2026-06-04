"""Spec inference integration for HarnessCI.

Provides zero-config spec loading: tries mined spec, then infers from PR context,
then falls back to empty spec.
"""

from __future__ import annotations

import json
from pathlib import Path

HARNESSCI_DIR = ".harnessci"
SPEC_JSON = "spec.json"
SPEC_MD = "spec.md"
SPEC_HASH = ".hash"


def harnessci_dir(root: Path) -> Path:
    return root / HARNESSCI_DIR


def spec_json_path(root: Path) -> Path:
    return harnessci_dir(root) / SPEC_JSON


def spec_md_path(root: Path) -> Path:
    return harnessci_dir(root) / SPEC_MD


def spec_hash_path(root: Path) -> Path:
    return harnessci_dir(root) / SPEC_HASH


def spec_exists(root: Path) -> bool:
    return spec_json_path(root).exists()


def load_mined_spec(root: Path) -> dict | None:
    """Load raw spec dict from .harnessci/spec.json if it exists."""
    path = spec_json_path(root)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_mined_spec(spec: dict, root: Path, summary_md: str = "") -> Path:
    """Save mined spec to .harnessci/spec.json and .harnessci/spec.md."""
    hdir = harnessci_dir(root)
    hdir.mkdir(parents=True, exist_ok=True)

    spec_path = spec_json_path(root)
    spec_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")

    if summary_md:
        md = spec_md_path(root)
        md.write_text(summary_md, encoding="utf-8")

    return spec_path


def get_spec_hash(root: Path) -> str | None:
    """Get the git hash when spec was last mined."""
    path = spec_hash_path(root)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip() or None


def save_spec_hash(root: Path, hash_val: str) -> None:
    """Save the git hash when spec was mined."""
    hdir = harnessci_dir(root)
    hdir.mkdir(parents=True, exist_ok=True)
    spec_hash_path(root).write_text(hash_val, encoding="utf-8")


def _extract_changed_files(diff_text: str) -> list[str]:
    """Extract changed file paths from unified diff text."""
    prefix = "+++ b/"
    return [ln[len(prefix) :] for ln in diff_text.strip().split("\n") if ln.startswith(prefix)]


def infer_spec_from_pr_context(diff_text: str, pr_title: str = "", pr_body: str = "") -> dict:
    """Infer a lightweight spec from PR context when no mined spec exists.

    This is a fallback for when:
    - .harnessci/spec.json doesn't exist
    - User runs audit on a PR without initializing first

    The inferred spec is lightweight but usable.
    """
    changed_files = _extract_changed_files(diff_text)
    file_summary = ", ".join(changed_files[:5])
    spec: dict = {
        "domain": pr_title or "unknown",
        "entities": [],
        "conventions": {},
        "forbidden_paths": [],
        "allowed_test_patterns": ["tests/", "*_test.py", "*.spec.ts", "*.test.ts"],
        "architecture": {},
        "security_invariants": [],
        "summary_md": (
            "## Spec inferred from PR\n\n"
            f"**Title:** {pr_title or 'N/A'}\n\n"
            f"**Body:** {(pr_body or 'N/A')[:500]}\n\n"
            f"**Changed files:** {file_summary or 'none'}\n\n"
            "This spec was auto-generated from PR metadata. "
            "Run `harnessci init` for full domain learning."
        ),
    }
    return spec


def get_inferred_goal(diff_text: str, pr_title: str) -> str:
    """Extract a usable goal from diff metadata when no spec exists."""
    changed_files = _extract_changed_files(diff_text)
    if changed_files:
        file_summary = ", ".join(changed_files[:5])
        return f"PR changes: {file_summary}"
    return pr_title or "Unknown PR"
