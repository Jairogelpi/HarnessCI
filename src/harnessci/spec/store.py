"""Persist and load mined specifications for HarnessCI.

Stores extracted specs in .harnessci/ directory as JSON + Markdown.
"""

from __future__ import annotations

import json
from pathlib import Path

# ---------------------------------------------------------------------------
# Directory helpers
# ---------------------------------------------------------------------------


def _harnessci_dir(root: Path) -> Path:
    """Return the .harnessci/ directory path under root."""
    return root / ".harnessci"


def _spec_json_path(root: Path) -> Path:
    """Return the path to spec.json under .harnessci/."""
    return _harnessci_dir(root) / "spec.json"


def _spec_md_path(root: Path) -> Path:
    """Return the path to spec.md under .harnessci/."""
    return _harnessci_dir(root) / "spec.md"


def _hash_path(root: Path) -> Path:
    """Return the path to the indexed commit hash."""
    return _harnessci_dir(root) / ".hash"


# ---------------------------------------------------------------------------
# Save mined spec
# ---------------------------------------------------------------------------


def save_mined_spec(spec: dict, root: Path, summary_md: str = "") -> Path:
    """Save a mined spec dict and summary markdown to .harnessci/.

    Writes:
    - .harnessci/spec.json — machine-readable spec
    - .harnessci/spec.md — human-readable summary

    Args:
        spec: Mined spec dictionary (version, domain, entities, conventions, etc.)
        root: Repository root path.
        summary_md: Human-readable summary in Markdown format.

    Returns:
        Path to the spec.json file.
    """
    harnessci_dir = _harnessci_dir(root)
    harnessci_dir.mkdir(parents=True, exist_ok=True)

    # Save JSON spec
    spec_json_path = _spec_json_path(root)
    with spec_json_path.open("w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)

    # Save Markdown summary if provided
    if summary_md:
        spec_md_path = _spec_md_path(root)
        spec_md_path.write_text(summary_md, encoding="utf-8")

    return spec_json_path


# ---------------------------------------------------------------------------
# Load mined spec
# ---------------------------------------------------------------------------


def load_mined_spec_dict(root: Path) -> dict | None:
    """Load raw spec dict from .harnessci/spec.json.

    Args:
        root: Repository root path.

    Returns:
        Spec dictionary if found, or None if not present.
    """
    spec_path = _spec_json_path(root)
    if not spec_path.exists():
        return None
    try:
        with spec_path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


# ---------------------------------------------------------------------------
# Spec existence and hash
# ---------------------------------------------------------------------------


def spec_exists(root: Path) -> bool:
    """Check if .harnessci/spec.json exists.

    Args:
        root: Repository root path.

    Returns:
        True if spec.json exists, False otherwise.
    """
    return _spec_json_path(root).exists()


def get_spec_hash(root: Path) -> str | None:
    """Get the git hash of the last indexed commit.

    Returns None if not initialized (no .harnessci/.hash file).

    Args:
        root: Repository root path.

    Returns:
        Git commit hash as string, or None if not set.
    """
    hash_file = _hash_path(root)
    if not hash_file.exists():
        return None
    try:
        return hash_file.read_text(encoding="utf-8").strip() or None
    except OSError:
        return None


def save_spec_hash(root: Path, commit_hash: str) -> None:
    """Save the git hash of the last indexed commit.

    Args:
        root: Repository root path.
        commit_hash: Git commit SHA to save.
    """
    harnessci_dir = _harnessci_dir(root)
    harnessci_dir.mkdir(parents=True, exist_ok=True)
    _hash_path(root).write_text(commit_hash, encoding="utf-8")


def compute_repo_hash(root: Path) -> str | None:
    """Compute current git hash of the repo HEAD.

    Args:
        root: Repository root path.

    Returns:
        Git commit SHA of HEAD, or None if not a git repo.
    """
    git_dir = root / ".git"
    if not git_dir.exists():
        return None
    try:
        head_ref = (git_dir / "HEAD").read_text(encoding="utf-8").strip()
        if head_ref.startswith("ref: "):
            ref_path = head_ref[5:]
            commit_sha = (git_dir / ref_path).read_text(encoding="utf-8").strip()
            return commit_sha
    except OSError:
        pass
    return None


def needs_update(root: Path) -> bool:
    """Check if spec needs updating (repo changed since last indexing).

    Compares current git HEAD hash against saved hash.

    Args:
        root: Repository root path.

    Returns:
        True if spec is outdated or missing, False if current.
    """
    saved = get_spec_hash(root)
    current = compute_repo_hash(root)
    if saved is None or current is None:
        return True
    return saved != current