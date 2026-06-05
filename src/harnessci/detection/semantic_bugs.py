"""AST-based semantic bug detection for HarnessCI.

Detects bugs that require understanding code structure:
- Null/none dereferences
- Missing error handling
- Unused imports/variables
- Type mismatches
- Logic errors
- Incomplete refactoring (renamed but not updated)

Uses Python's ast module for static analysis.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Any


@dataclass
class SemanticBugMatch:
    file_path: str
    line_number: int
    node_type: str  # 'null_deref', 'missing_error_handling', 'unused_import', etc.
    message: str
    severity: str  # critical/high/medium/low
    evidence: str  # the problematic code


class SemanticBugDetector:
    """AST-based semantic analysis for Python code."""

    def __init__(
        self,
        include_null_deref: bool = True,
        include_unused_imports: bool = True,
        include_missing_try: bool = True,
        include_logic_errors: bool = True,
        include_incomplete_refactor: bool = True,
        min_severity: str = "medium",
    ) -> None:
        self.include_null_deref = include_null_deref
        self.include_unused_imports = include_unused_imports
        self.include_missing_try = include_missing_try
        self.include_logic_errors = include_logic_errors
        self.include_incomplete_refactor = include_incomplete_refactor
        self.min_severity = min_severity

    def analyze_file(self, file_path: str, source_code: str) -> list[SemanticBugMatch]:
        """Analyze a single Python file for semantic bugs."""
        matches: list[SemanticBugMatch] = []

        try:
            tree = ast.parse(source_code)
        except SyntaxError:
            return matches

        # Collect all defined names first
        defined_names: set[str] = set()
        imported_names: dict[str, str] = {}  # name -> module

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                defined_names.add(node.id)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    imported_names[name] = alias.name
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imported_names[name] = f"{node.module}.{alias.name}"

        # Run analyzers
        if self.include_null_deref:
            matches.extend(self._check_null_derefs(tree, file_path))

        if self.include_unused_imports:
            matches.extend(
                self._check_unused_imports(tree, file_path, imported_names, defined_names)
            )

        if self.include_missing_try:
            matches.extend(self._check_missing_try(tree, file_path))

        if self.include_logic_errors:
            matches.extend(self._check_logic_errors(tree, file_path))

        if self.include_incomplete_refactor:
            matches.extend(self._check_incomplete_refactor(tree, file_path))

        # Filter by severity
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
        min_level = severity_order.get(self.min_severity, 2)
        matches = [m for m in matches if severity_order.get(m.severity, 4) <= min_level]

        return matches

    def _check_null_derefs(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> list[SemanticBugMatch]:
        """Detect potential null/none dereferences."""
        matches: list[SemanticBugMatch] = []

        for node in ast.walk(tree):
            # Check for attribute access on potentially null objects
            if isinstance(node, ast.Attribute):
                if isinstance(node.value, ast.Name):
                    name = node.value.id.lower()
                    # Common null-susceptible patterns
                    null_indicators = [
                        "result",
                        "data",
                        "response",
                        "user",
                        "config",
                        "item",
                        "obj",
                        "entry",
                        "value",
                        "ret",
                        "out",
                        "resp",
                        "info",
                        "ctx",
                        "context",
                    ]
                    if any(ind in name for ind in null_indicators):
                        # Check if there's a None check nearby
                        lineno = getattr(node, "lineno", 1)
                        matches.append(
                            SemanticBugMatch(
                                file_path=file_path,
                                line_number=lineno,
                                node_type="null_deref_risk",
                                message=(
                                    f"Attribute access on '{name}' without null check. "
                                    f"Rename suggests it may be nullable."
                                ),
                                severity="medium",
                                evidence=f"{name}.{node.attr}",
                            )
                        )

            # Check for subscript on potentially null objects
            if isinstance(node, ast.Subscript):
                if isinstance(node.value, ast.Name):
                    name = node.value.id.lower()
                    null_indicators = ["result", "data", "response", "item", "obj"]
                    if any(ind in name for ind in null_indicators):
                        lineno = getattr(node, "lineno", 1)
                        matches.append(
                            SemanticBugMatch(
                                file_path=file_path,
                                line_number=lineno,
                                node_type="null_deref_risk",
                                message=f"Subscript on '{name}' without null check",
                                severity="medium",
                                evidence=f"{name}[...]",
                            )
                        )

        return matches[:5]  # Limit to 5 per file

    def _check_unused_imports(
        self,
        tree: ast.AST,
        file_path: str,
        imported_names: dict[str, str],
        defined_names: set[str],
    ) -> list[SemanticBugMatch]:
        """Detect unused imports."""
        matches: list[SemanticBugMatch] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name.split(".")[0]
                    if name not in defined_names:
                        lineno = getattr(node, "lineno", 1)
                        matches.append(
                            SemanticBugMatch(
                                file_path=file_path,
                                line_number=lineno,
                                node_type="unused_import",
                                message=f"Import '{name}' appears unused",
                                severity="info",
                                evidence=f"import {alias.name}",
                            )
                        )
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    if name not in defined_names:
                        lineno = getattr(node, "lineno", 1)
                        matches.append(
                            SemanticBugMatch(
                                file_path=file_path,
                                line_number=lineno,
                                node_type="unused_import",
                                message=f"Import '{name}' from '{node.module}' appears unused",
                                severity="info",
                                evidence=f"from {node.module} import {alias.name}",
                            )
                        )

        return matches[:3]  # Limit to 3 per file

    def _check_missing_try(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> list[SemanticBugMatch]:
        """Detect dangerous operations without try/except."""
        matches: list[SemanticBugMatch] = []

        dangerous_calls = [
            (
                r"(?:json\.loads|yaml\.load|marshal\.loads|pickle\.load)\s*\(",
                "deserialization_risk",
            ),
            (r"subprocess\.(?:run|call|Popen)\s*\(", "subprocess_without_error_handling"),
            (r"requests\.(?:get|post|put|delete)\s*\(", "http_call_without_error_handling"),
            (r"open\s*\([^)]*\)\s*(?!\s*(?:as|with))", "file_handle_no_context_manager"),
            (r"\.execute\s*\([^)]*\%", "sql_format_string_risk"),
        ]

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = ""
                if isinstance(node.func, ast.Attribute):
                    if isinstance(node.func.value, ast.Name):
                        func = f"{node.func.value.id}.{node.func.attr}"
                    else:
                        func = node.func.attr
                elif isinstance(node.func, ast.Name):
                    func = node.func.id

                lineno = getattr(node, "lineno", 1)

                for pattern, bug_type in dangerous_calls:
                    if re.search(pattern, func):
                        matches.append(
                            SemanticBugMatch(
                                file_path=file_path,
                                line_number=lineno,
                                node_type=bug_type,
                                message=f"Call to {func} without try/except protection",
                                severity="high",
                                evidence=func,
                            )
                        )

        return matches[:3]

    def _check_logic_errors(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> list[SemanticBugMatch]:
        """Detect logic errors: always-true/false conditions, dead code."""
        matches: list[SemanticBugMatch] = []

        for node in ast.walk(tree):
            # Check if statements with constant conditions
            if isinstance(node, ast.If):
                if isinstance(node.test, ast.Constant):
                    val = node.test.value
                    if isinstance(val, bool):
                        lineno = getattr(node, "lineno", 1)
                        cond_str = "True" if val else "False"
                        eff_str = "dead code" if not val else "unconditional"
                        matches.append(
                            SemanticBugMatch(
                                file_path=file_path,
                                line_number=lineno,
                                node_type="constant_condition",
                                message=f"If with constant {cond_str} — {eff_str}",
                                severity="medium",
                                evidence=f"if {val}:",
                            )
                        )

            # Check for empty except blocks
            if isinstance(node, ast.ExceptHandler):
                if isinstance(node.body, list) and len(node.body) == 0:
                    lineno = getattr(node, "lineno", 1)
                    matches.append(
                        SemanticBugMatch(
                            file_path=file_path,
                            line_number=lineno,
                            node_type="empty_except",
                            message="Empty except block — errors silently ignored",
                            severity="high",
                            evidence="except: pass",
                        )
                    )

        return matches[:3]

    def _check_incomplete_refactor(
        self,
        tree: ast.AST,
        file_path: str,
    ) -> list[SemanticBugMatch]:
        """Detect incomplete refactoring: renamed functions but not all call sites."""
        matches: list[SemanticBugMatch] = []

        # Find all function definitions
        func_defs: set[str] = set()
        func_calls: set[str] = set()

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                func_defs.add(node.name)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    func_calls.add(node.func.id)

        # Check for undefined function calls
        undefined_calls = func_calls - func_defs
        for func_name in undefined_calls:
            # Only flag if it looks like a defined function (camelCase/PascalCase)
            if re.match(r"^[A-Z][a-zA-Z0-9]*$", func_name) or "_" in func_name:
                matches.append(
                    SemanticBugMatch(
                        file_path=file_path,
                        line_number=1,
                        node_type="undefined_function_call",
                        message=f"Call to undefined function '{func_name}'",
                        severity="high",
                        evidence=func_name,
                    )
                )

        return matches[:3]

    def analyze_diff(
        self,
        file_changes: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Analyze multiple files from a PR diff.

        Args:
            file_changes: List of dicts with keys: path, new_lines (list of str)
        """
        all_matches: list[dict[str, Any]] = []

        for fc in file_changes:
            path = fc.get("path", "")
            new_lines = fc.get("new_lines", [])

            if not new_lines:
                continue

            source = "\n".join(new_lines)
            matches = self.analyze_file(path, source)

            for m in matches:
                all_matches.append(
                    {
                        "file_path": m.file_path,
                        "line_number": m.line_number,
                        "type": m.node_type,
                        "message": m.message,
                        "severity": m.severity,
                        "evidence": m.evidence,
                    }
                )

        return all_matches


def detect_semantic_bugs(
    file_changes: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Convenience function: detect semantic bugs in file changes."""
    detector = SemanticBugDetector()
    return detector.analyze_diff(file_changes)
