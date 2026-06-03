"""Tests for PR3: unified diff parser and path classification."""

from harnessci.diff import build_diff_features, classify_files, parse_diff_text
from harnessci.models import ChangeType, DiffFileChange

# ---------------------------------------------------------------------------
# Fixtures — raw unified diff strings
# ---------------------------------------------------------------------------

BASIC_DIFF = """\
diff --git a/src/auth/session.py b/src/auth/session.py
index abc1234..def5678 100644
--- a/src/auth/session.py
+++ b/src/auth/session.py
@@ -1,5 +1,7 @@
 import os
+import time
+
 def get_session(token):
-    return None
+    return {"token": token, "ts": time.time()}
 
 def destroy_session(token):
"""

NEW_FILE_DIFF = """\
diff --git a/src/utils/helpers.py b/src/utils/helpers.py
new file mode 100644
index 0000000..aabbccd
--- /dev/null
+++ b/src/utils/helpers.py
@@ -0,0 +1,3 @@
+def helper():
+    pass
+
"""

DELETED_FILE_DIFF = """\
diff --git a/src/old_module.py b/src/old_module.py
deleted file mode 100644
index 1234abc..0000000
--- a/src/old_module.py
+++ /dev/null
@@ -1,2 +0,0 @@
-def old():
-    pass
"""

RENAMED_DIFF = """\
diff --git a/src/foo.py b/src/bar.py
similarity index 90%
rename from src/foo.py
rename to src/bar.py
index 1111111..2222222 100644
--- a/src/foo.py
+++ b/src/bar.py
@@ -1,3 +1,3 @@
 def func():
-    return 1
+    return 2
"""

EMPTY_DIFF = ""

MULTI_FILE_DIFF = """\
diff --git a/tests/test_auth.py b/tests/test_auth.py
index 111..222 100644
--- a/tests/test_auth.py
+++ b/tests/test_auth.py
@@ -1,2 +1,4 @@
 import pytest
+
+def test_new():
+    pass
diff --git a/tests/test_utils.py b/tests/test_utils.py
new file mode 100644
--- /dev/null
+++ b/tests/test_utils.py
@@ -0,0 +1,3 @@
+def test_helper():
+    assert True
+
"""

# ---------------------------------------------------------------------------
# 3.1  parse_diff_text
# ---------------------------------------------------------------------------


class TestParseDiffText:
    def test_basic_diff_returns_one_file(self) -> None:
        files = parse_diff_text(BASIC_DIFF)
        assert len(files) == 1

    def test_basic_diff_path(self) -> None:
        files = parse_diff_text(BASIC_DIFF)
        assert files[0].path == "src/auth/session.py"

    def test_basic_diff_line_counts(self) -> None:
        files = parse_diff_text(BASIC_DIFF)
        f = files[0]
        assert f.lines_added == 3
        assert f.lines_deleted == 1

    def test_basic_diff_status_modified(self) -> None:
        files = parse_diff_text(BASIC_DIFF)
        assert files[0].status == "modified"

    def test_new_file_detected(self) -> None:
        files = parse_diff_text(NEW_FILE_DIFF)
        assert len(files) == 1
        f = files[0]
        assert f.status == "added"
        assert f.path == "src/utils/helpers.py"
        assert f.old_path is None
        assert f.lines_added == 3
        assert f.lines_deleted == 0

    def test_deleted_file_detected(self) -> None:
        files = parse_diff_text(DELETED_FILE_DIFF)
        assert len(files) == 1
        f = files[0]
        assert f.status == "deleted"
        assert f.path == "src/old_module.py"
        assert f.lines_added == 0
        assert f.lines_deleted == 2

    def test_renamed_file_detected(self) -> None:
        files = parse_diff_text(RENAMED_DIFF)
        assert len(files) == 1
        f = files[0]
        assert f.status == "renamed"
        assert f.path == "src/bar.py"
        assert f.old_path == "src/foo.py"

    def test_empty_diff_returns_empty_list(self) -> None:
        assert parse_diff_text(EMPTY_DIFF) == []

    def test_multi_file_diff_returns_two_files(self) -> None:
        files = parse_diff_text(MULTI_FILE_DIFF)
        assert len(files) == 2

    def test_metadata_lines_not_counted(self) -> None:
        # "--- a/..." and "+++ b/..." lines must not be counted as edits
        files = parse_diff_text(BASIC_DIFF)
        f = files[0]
        assert f.lines_added == 3
        assert f.lines_deleted == 1


# ---------------------------------------------------------------------------
# 3.2  classify_files
# ---------------------------------------------------------------------------


class TestClassifyFiles:
    def _make(self, path: str, status: str = "modified") -> DiffFileChange:
        return DiffFileChange(path=path, status=status)

    def test_test_file_by_prefix(self) -> None:
        f = classify_files([self._make("tests/test_auth.py")])[0]
        assert f.is_test is True

    def test_test_file_by_name_contains_test(self) -> None:
        f = classify_files([self._make("src/auth_test.py")])[0]
        assert f.is_test is True

    def test_spec_file_is_test(self) -> None:
        f = classify_files([self._make("src/auth.spec.js")])[0]
        assert f.is_test is True

    def test_non_test_file(self) -> None:
        f = classify_files([self._make("src/auth/session.py")])[0]
        assert f.is_test is False

    def test_docs_md(self) -> None:
        f = classify_files([self._make("README.md")])[0]
        assert f.is_docs is True

    def test_docs_rst(self) -> None:
        f = classify_files([self._make("docs/architecture.rst")])[0]
        assert f.is_docs is True

    def test_docs_dir(self) -> None:
        f = classify_files([self._make("docs/product_spec.md")])[0]
        assert f.is_docs is True

    def test_config_yaml(self) -> None:
        f = classify_files([self._make("config/settings.yaml")])[0]
        assert f.is_config is True

    def test_config_dockerfile(self) -> None:
        f = classify_files([self._make("Dockerfile")])[0]
        assert f.is_config is True

    def test_dependency_pyproject(self) -> None:
        f = classify_files([self._make("pyproject.toml")])[0]
        assert f.is_dependency is True

    def test_dependency_requirements(self) -> None:
        f = classify_files([self._make("requirements-dev.txt")])[0]
        assert f.is_dependency is True

    def test_dependency_package_json(self) -> None:
        f = classify_files([self._make("package.json")])[0]
        assert f.is_dependency is True

    def test_database_migration(self) -> None:
        f = classify_files([self._make("alembic/versions/001_add_users.py")])[0]
        assert f.is_database is True

    def test_database_migration_name(self) -> None:
        f = classify_files([self._make("src/db/migrate_users.py")])[0]
        assert f.is_database is True

    def test_sensitive_auth(self) -> None:
        f = classify_files([self._make("src/auth/session.py")])[0]
        assert f.is_sensitive is True

    def test_sensitive_payment(self) -> None:
        f = classify_files([self._make("billing/payment_gateway.py")])[0]
        assert f.is_sensitive is True

    def test_sensitive_jwt(self) -> None:
        f = classify_files([self._make("src/utils/jwt_helper.py")])[0]
        assert f.is_sensitive is True

    def test_non_sensitive_regular(self) -> None:
        f = classify_files([self._make("src/utils/helpers.py")])[0]
        assert f.is_sensitive is False


# ---------------------------------------------------------------------------
# 3.2  build_diff_features — change_type and aggregate fields
# ---------------------------------------------------------------------------


class TestBuildDiffFeatures:
    def _make(
        self, path: str, status: str = "modified", added: int = 0, deleted: int = 0
    ) -> DiffFileChange:
        return DiffFileChange(path=path, status=status, lines_added=added, lines_deleted=deleted)

    def test_change_type_test_only(self) -> None:
        files = classify_files(
            [
                self._make("tests/test_auth.py", added=5),
                self._make("tests/test_utils.py", added=3),
            ]
        )
        feat = build_diff_features(files)
        assert feat.change_type == ChangeType.TEST_ONLY

    def test_change_type_dependency_update(self) -> None:
        files = classify_files([self._make("pyproject.toml", added=2)])
        feat = build_diff_features(files)
        assert feat.change_type == ChangeType.DEPENDENCY_UPDATE

    def test_change_type_database(self) -> None:
        files = classify_files(
            [
                self._make("alembic/versions/001_add_table.py", added=10),
                self._make("src/models.py", added=5),
            ]
        )
        feat = build_diff_features(files)
        assert feat.change_type == ChangeType.DATABASE_CHANGE

    def test_change_type_security_sensitive(self) -> None:
        files = classify_files([self._make("src/auth/session.py", added=3)])
        feat = build_diff_features(files)
        assert feat.change_type == ChangeType.SECURITY_SENSITIVE

    def test_change_type_docs_only(self) -> None:
        files = classify_files(
            [
                self._make("README.md", added=5),
                self._make("docs/architecture.md", added=2),
            ]
        )
        feat = build_diff_features(files)
        assert feat.change_type == ChangeType.DOCS_ONLY

    def test_public_api_changed_api_dir(self) -> None:
        files = classify_files([self._make("api/users.py")])
        feat = build_diff_features(files)
        assert feat.public_api_changed is True

    def test_public_api_changed_route_file(self) -> None:
        files = classify_files([self._make("src/router.py")])
        feat = build_diff_features(files)
        assert feat.public_api_changed is True

    def test_public_api_not_changed_for_test(self) -> None:
        # test file in api/ should not count
        files = classify_files([self._make("tests/test_api_router.py")])
        feat = build_diff_features(files)
        assert feat.public_api_changed is False

    def test_aggregate_counts(self) -> None:
        files = classify_files(
            [
                self._make("src/auth/session.py", added=10, deleted=5),
                self._make("tests/test_auth.py", added=3),
            ]
        )
        feat = build_diff_features(files)
        assert feat.files_changed == 2
        assert feat.lines_added == 13
        assert feat.lines_deleted == 5
        assert feat.total_churn == 18
        assert feat.test_files_changed == 1

    def test_sensitive_files_list(self) -> None:
        files = classify_files(
            [
                self._make("src/auth/session.py"),
                self._make("src/utils/helpers.py"),
            ]
        )
        feat = build_diff_features(files)
        assert "src/auth/session.py" in feat.sensitive_files_touched
        assert "src/utils/helpers.py" not in feat.sensitive_files_touched

    def test_database_migration_added_flag(self) -> None:
        files = classify_files([self._make("alembic/versions/001.py")])
        feat = build_diff_features(files)
        assert feat.database_migration_added is True

    def test_empty_files_produces_zero_counts(self) -> None:
        feat = build_diff_features([])
        assert feat.files_changed == 0
        assert feat.total_churn == 0
        assert feat.change_type == ChangeType.UNKNOWN
