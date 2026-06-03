"""Path classification and DiffFeatures builder for HarnessCI.

All classification is deterministic — no LLM calls, no subprocess.
"""

from __future__ import annotations

import os

from ..models import ChangeType, DiffFeatures, DiffFileChange

# ---------------------------------------------------------------------------
# Classification constants
# ---------------------------------------------------------------------------

_TEST_DIRS = {"tests", "test", "spec", "__tests__"}
_TEST_SUFFIXES = ("_test.py", "_test.js", "_test.ts", "_test.rb", "_test.go")
_TEST_INFIX = (".test.", ".spec.")

_DOCS_DIRS = {"docs", "doc"}
_DOCS_EXTS = {".md", ".rst", ".txt"}

_CONFIG_EXTS = {".yaml", ".yml", ".toml", ".ini", ".cfg", ".env"}
_CONFIG_NAMES = {"Makefile", "Dockerfile", ".dockerignore", ".env.example"}
_CONFIG_ENV_PREFIX = ".env."

_DEPENDENCY_NAMES = {
    "pyproject.toml",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "package.json",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "composer.json",
    "composer.lock",
}
_DEPENDENCY_GLOB_PREFIXES = ("requirements",)
_DEPENDENCY_GLOB_SUFFIX = ".txt"

_DATABASE_DIRS = {"migrations", "alembic"}
_DATABASE_KEYWORDS = {"migration", "migrate", "schema"}

_SENSITIVE_KEYWORDS = {
    "auth",
    "session",
    "password",
    "token",
    "secret",
    "permission",
    "role",
    "billing",
    "payment",
    "invoice",
    "subscription",
    "crypto",
    "jwt",
    "oauth",
}

_PUBLIC_API_DIRS = {"api", "routes", "controllers", "endpoints"}
_PUBLIC_API_KEYWORDS = {"router", "route", "endpoint", "view", "controller"}


# ---------------------------------------------------------------------------
# Per-file classification
# ---------------------------------------------------------------------------


def _is_test(path: str) -> bool:
    parts = _path_parts(path)
    # Directory-based
    if parts[:-1] and parts[0] in _TEST_DIRS:
        return True
    filename = parts[-1].lower()
    # Suffix-based
    if filename.endswith(_TEST_SUFFIXES):
        return True
    # Infix-based
    if any(infix in filename for infix in _TEST_INFIX):
        return True
    # "test" or "spec" anywhere in the name
    name_no_ext = os.path.splitext(filename)[0]
    return "test" in name_no_ext.split("_") or "spec" in name_no_ext.split("_")


def _is_docs(path: str) -> bool:
    parts = _path_parts(path)
    if parts[0] in _DOCS_DIRS:
        return True
    _, ext = os.path.splitext(parts[-1])
    return ext.lower() in _DOCS_EXTS


def _is_config(path: str) -> bool:
    parts = _path_parts(path)
    filename = parts[-1]
    _, ext = os.path.splitext(filename)
    if ext.lower() in _CONFIG_EXTS:
        return True
    if filename in _CONFIG_NAMES:
        return True
    if filename.startswith(_CONFIG_ENV_PREFIX):
        return True
    return False


def _is_dependency(path: str) -> bool:
    parts = _path_parts(path)
    filename = parts[-1]
    if filename in _DEPENDENCY_NAMES:
        return True
    # requirements*.txt
    name_lower = filename.lower()
    for prefix in _DEPENDENCY_GLOB_PREFIXES:
        if name_lower.startswith(prefix) and name_lower.endswith(_DEPENDENCY_GLOB_SUFFIX):
            return True
    return False


def _is_database(path: str) -> bool:
    parts = _path_parts(path)
    # Directory match
    if any(p in _DATABASE_DIRS for p in parts[:-1]):
        return True
    # Keyword in full path
    path_lower = path.lower()
    return any(kw in path_lower for kw in _DATABASE_KEYWORDS)


def _is_sensitive(path: str) -> bool:
    path_lower = path.lower()
    return any(kw in path_lower for kw in _SENSITIVE_KEYWORDS)


def _is_public_api(path: str, is_test: bool) -> bool:
    if is_test:
        return False
    parts = _path_parts(path)
    if parts[0] in _PUBLIC_API_DIRS:
        return True
    filename_no_ext = os.path.splitext(parts[-1].lower())[0]
    return any(kw in filename_no_ext for kw in _PUBLIC_API_KEYWORDS)


def _path_parts(path: str) -> list[str]:
    """Split a forward-slash path into parts (handles both / and \\)."""
    return path.replace("\\", "/").split("/")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_files(files: list[DiffFileChange]) -> list[DiffFileChange]:
    """Return new DiffFileChange instances with classification flags set."""
    result: list[DiffFileChange] = []
    for f in files:
        classified = f.model_copy(
            update={
                "is_test": _is_test(f.path),
                "is_docs": _is_docs(f.path),
                "is_config": _is_config(f.path),
                "is_dependency": _is_dependency(f.path),
                "is_database": _is_database(f.path),
                "is_sensitive": _is_sensitive(f.path),
            }
        )
        result.append(classified)
    return result


def build_diff_features(files: list[DiffFileChange]) -> DiffFeatures:
    """Aggregate classified DiffFileChange list into DiffFeatures."""
    if not files:
        return DiffFeatures(
            files_changed=0,
            lines_added=0,
            lines_deleted=0,
            total_churn=0,
            test_files_changed=0,
            config_files_changed=0,
            dependency_changes=0,
            database_migration_added=False,
            public_api_changed=False,
            change_type=ChangeType.UNKNOWN,
        )

    lines_added = sum(f.lines_added for f in files)
    lines_deleted = sum(f.lines_deleted for f in files)

    sensitive_files = [f.path for f in files if f.is_sensitive]
    public_api_changed = any(_is_public_api(f.path, f.is_test) for f in files)

    return DiffFeatures(
        files_changed=len(files),
        lines_added=lines_added,
        lines_deleted=lines_deleted,
        total_churn=lines_added + lines_deleted,
        test_files_changed=sum(1 for f in files if f.is_test),
        config_files_changed=sum(1 for f in files if f.is_config),
        dependency_changes=sum(1 for f in files if f.is_dependency),
        database_migration_added=any(f.is_database for f in files),
        public_api_changed=public_api_changed,
        sensitive_files_touched=sensitive_files,
        change_type=_classify_change_type(files),
        files=list(files),
    )


def _classify_change_type(files: list[DiffFileChange]) -> ChangeType:
    """Determine change type in priority order.

    Test-only and docs-only checks are applied first so that files whose
    names happen to contain sensitive keywords (e.g. test_auth.py) do not
    incorrectly escalate to SECURITY_SENSITIVE.
    """
    # Test-only and docs-only take precedence over keyword-based signals
    all_test = all(f.is_test for f in files)
    if all_test:
        return ChangeType.TEST_ONLY

    all_docs = all(f.is_docs for f in files)
    if all_docs:
        return ChangeType.DOCS_ONLY

    # Structural signals on non-test files
    non_test = [f for f in files if not f.is_test]
    has_dependency = any(f.is_dependency for f in non_test)
    has_database = any(f.is_database for f in non_test)
    has_sensitive = any(f.is_sensitive for f in non_test)

    non_dependency = [f for f in non_test if not f.is_dependency]

    if has_dependency and not non_dependency:
        return ChangeType.DEPENDENCY_UPDATE
    if has_database:
        return ChangeType.DATABASE_CHANGE
    if has_sensitive:
        return ChangeType.SECURITY_SENSITIVE

    return ChangeType.UNKNOWN
