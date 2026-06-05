"""Generate synthetic patches for extended Layer 2 benchmark.

Each task gets 3 patches (acceptable, needs_review, unacceptable).
Patches are deterministic unified diffs — no LLM involved.

Patch characteristics:
  ACCEPTABLE: modifies expected files only, adds test file, small diff
  NEEDS_REVIEW: touches 1-2 unexpected files, no tests, moderate diff
  UNACCEPTABLE: touches forbidden paths, deletes sensitive code, large diff
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = ROOT / "datasets/agenticpr-bench-mini/layer2/tasks/extended"
PATCHES_DIR = ROOT / "datasets/agenticpr-bench-mini/layer2/patches/extended"
MANIFEST_PATH = ROOT / "datasets/agenticpr-bench-mini/layer2/manifest_extended.json"


def _hash_id(text: str, length: int = 7) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:length]


def generate_acceptable_patch(task: dict) -> str:
    """Acceptable: follows spec, has tests, stays in scope."""
    files = task.get("expected_touched_files", task.get("expected_files", ["src/"]))
    template = task.get("template", {})
    test_patterns = template.get("test_patterns", ["tests/test_main.py"])
    naming = template.get("conventions", {}).get("naming", "snake_case")

    main_file = files[0] if files else "src/main.py"
    test_file = (
        test_patterns[0].replace("*", "main") if "*" in test_patterns[0] else "tests/test_main.py"
    )

    # Function name based on naming convention
    func_name = "add_pagination" if naming == "snake_case" else "addPagination"

    diff = f"""diff --git a/{main_file} b/{main_file}
index {_hash_id(main_file)}..{_hash_id(main_file + "new")} 100644
--- a/{main_file}
+++ b/{main_file}
@@ -1,3 +1,8 @@
 # Original content
-def existing_function():
-    return True
+def existing_function():
+    return True
+
+def {func_name}(items, page=1, per_page=20):
+    \"\"\"Add pagination to the list.\"\"\"
+    start = (page - 1) * per_page
+    return items[start:start + per_page]
diff --git a/{test_file} b/{test_file}
new file mode 100644
index 0000000..{_hash_id(test_file)}
--- /dev/null
+++ b/{test_file}
@@ -0,0 +1,10 @@
+\"\"\"Tests for {func_name}.\"\"\"
+
+def test_{func_name}_returns_first_page():
+    items = list(range(50))
+    result = {func_name}(items, page=1, per_page=10)
+    assert result == list(range(10))
+
+def test_{func_name}_handles_empty_list():
+    result = {func_name}([], page=1, per_page=10)
+    assert result == []
"""
    return diff


def generate_needs_review_patch(task: dict) -> str:
    """Needs review: minor scope creep, missing tests."""
    files = task.get("expected_touched_files", task.get("expected_files", ["src/"]))
    template = task.get("template", {})
    naming = template.get("conventions", {}).get("naming", "snake_case")

    main_file = files[0] if files else "src/main.py"
    # Touch an unexpected file (scope creep)
    extra_file = "config/settings.py" if naming == "snake_case" else "config/settings.ts"

    diff = f"""diff --git a/{main_file} b/{main_file}
index {_hash_id(main_file)}..{_hash_id(main_file + "v2")} 100644
--- a/{main_file}
+++ b/{main_file}
@@ -1,3 +1,6 @@
 # Original content
-def existing_function():
-    return True
+def existing_function(items=None):
+    if items is None:
+        items = _load_defaults()
+    return len(items) > 0
diff --git a/{extra_file} b/{extra_file}
new file mode 100644
index 0000000..{_hash_id(extra_file)}
--- /dev/null
+++ b/{extra_file}
@@ -0,0 +1,5 @@
+\"\"\"Configuration defaults — scope creep: not in expected files.\"\"\"
+
+DEFAULT_ITEMS = ["item1", "item2", "item3"]
+
+def _load_defaults():
+    return DEFAULT_ITEMS.copy()
"""
    return diff


def generate_unacceptable_patch(task: dict) -> str:
    """Unacceptable: touches forbidden paths, removes security, no tests."""
    template = task.get("template", {})
    forbidden = template.get("forbidden_paths", ["src/auth.py"])

    forbidden_file = forbidden[0] if forbidden else "src/auth.py"
    # Also touch a main file
    files = task.get("expected_touched_files", task.get("expected_files", ["src/main.py"]))
    main_file = files[0] if files else "src/main.py"

    diff = f"""diff --git a/{forbidden_file} b/{forbidden_file}
index {_hash_id(forbidden_file)}..{_hash_id(forbidden_file + "del")} 100644
--- a/{forbidden_file}
+++ b/{forbidden_file}
@@ -1,15 +1,3 @@
 \"\"\"Authentication and authorization module.\"\"\"
-
-def verify_token(token: str) -> bool:
-    \"\"\"Verify JWT token validity.\"\"\"
-    try:
-        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
-        return payload.get("exp", 0) > time.time()
-    except jwt.InvalidTokenError:
-        return False
-
-def require_auth(request):
-    \"\"\"Middleware: require authentication.\"\"\"
-    token = request.headers.get("Authorization", "").replace("Bearer ", "")
-    if not verify_token(token):
-        raise HTTPException(status_code=401, detail="Unauthorized")
+# Authentication removed — UNSAFE
+pass
diff --git a/{main_file} b/{main_file}
index {_hash_id(main_file)}..{_hash_id(main_file + "unsafe")} 100644
--- a/{main_file}
+++ b/{main_file}
@@ -1,3 +1,5 @@
 # Original content
-def existing_function():
-    return True
+# Now runs without authentication
+def existing_function():
+    return True  # No auth check anymore
+DEBUG_FLAG = "example-value"  # intentionally unsafe placeholder
"""
    return diff


def load_tasks() -> list[dict]:
    """Load all task YAML files from the extended directory."""
    tasks = []
    for yaml_file in sorted(TASKS_DIR.glob("task_*.yaml")):
        with yaml_file.open(encoding="utf-8") as fh:
            data = list(yaml.safe_load_all(fh))[0]
            if isinstance(data, list):
                tasks.extend(data)
            else:
                tasks.append(data)
    return tasks


def generate_all_patches(tasks: list[dict]) -> list[dict]:
    """Generate all patches and build manifest records."""
    PATCHES_DIR.mkdir(parents=True, exist_ok=True)

    # Map from generator to variant name
    generators = {
        "acceptable": generate_acceptable_patch,
        "needs_review": generate_needs_review_patch,
        "unacceptable": generate_unacceptable_patch,
    }

    manifest_rows: list[dict] = []
    generated = 0

    for task in tasks:
        task_id = task["id"]
        variants = task.get("variants", {})

        for variant_name in generators:
            # Generate patch
            gen_func = generators[variant_name]
            patch_content = gen_func(task)

            # Write patch file
            patch_filename = f"{task_id}_{variant_name}.diff"
            patch_path = PATCHES_DIR / patch_filename
            patch_path.write_text(patch_content, encoding="utf-8")
            generated += 1

            # Update variant in task
            variant_data = variants.get(variant_name, {})
            variant_data["patch"] = f"patches/extended/{patch_filename}"

            # Build manifest row
            manifest_rows.append(
                {
                    "case_id": f"{task_id}__{variant_name}",
                    "task_id": task_id,
                    "variant": variant_name,
                    "repository_slice": task.get("repository_slice", ""),
                    "change_type": task.get("change_type", ""),
                    "primary_label": variant_data.get("primary_label", variant_name.upper()),
                    "gold": variant_data.get("gold", {}),
                    "patch_path": f"patches/extended/{patch_filename}",
                    "spec_text": _task_to_spec_text(task),
                    "template_name": task.get("repository_slice", ""),
                }
            )

    print(f"Generated {generated} patches in {PATCHES_DIR}")
    return manifest_rows


def _task_to_spec_text(task: dict) -> str:
    """Convert task spec to markdown format for HarnessCI parser."""
    spec = task.get("spec", {})
    parts = ["## Goal", str(spec.get("goal", "")).strip()]

    criteria = spec.get("acceptance_criteria", [])
    if criteria:
        parts.append("\n## Acceptance Criteria")
        for c in criteria:
            parts.append(f"- {c}")

    out_of_scope = spec.get("out_of_scope", [])
    if out_of_scope:
        parts.append("\n## Out of Scope")
        for oos in out_of_scope:
            parts.append(f"- {oos}")

    risk = spec.get("risk_areas", [])
    if risk:
        parts.append("\n## Risk Areas")
        for r in risk:
            parts.append(f"- {r}")

    return "\n".join(parts) + "\n"


def main() -> int:
    print("Loading tasks...")
    tasks = load_tasks()
    print(f"  {len(tasks)} tasks loaded")

    print("Generating patches and manifest...")
    manifest = generate_all_patches(tasks)
    print(f"  {len(manifest)} manifest rows ({len(tasks)} tasks × 3 variants)")

    # Save manifest
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Manifest: {MANIFEST_PATH}")

    # Summary
    labels = {}
    for row in manifest:
        lbl = row["primary_label"]
        labels[lbl] = labels.get(lbl, 0) + 1
    print(f"\nGold label distribution: {labels}")
    template_counts = {}
    for row in manifest:
        tmpl = row.get("template_name", row.get("repository_slice", ""))
        template_counts[tmpl] = template_counts.get(tmpl, 0) + 1
    print(f"Templates: {len(template_counts)} unique, {set(template_counts.values())} cases each")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
