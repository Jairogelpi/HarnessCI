"""Deterministic spec verification for HarnessCI.

Verifies diffs against mined specs using rules:
- Forbidden path violations
- Architecture layer violations
- Naming convention violations
- Entity invariant violations (optional LLM check)
"""

from __future__ import annotations

import re

from ..models import (
    AuditFinding,
    DiffFeatures,
    FindingCategory,
    FindingSeverity,
    SpecModel,
)


class SpecVerifier:
    """Verify diffs against mined specifications."""

    def __init__(
        self,
        spec: SpecModel | dict,
        diff: DiffFeatures | None = None,
        llm_client=None,
    ) -> None:
        """Initialize verifier with spec and optional diff.

        Args:
            spec: SpecModel or mined spec dict.
            diff: Optional DiffFeatures for quick verification.
            llm_client: Optional LLM client for invariant checks.
        """
        self.spec = spec
        self.diff = diff
        self.llm_client = llm_client

    def verify(self, diff: DiffFeatures) -> list[AuditFinding]:
        """Verify a diff against the spec using deterministic rules.

        Findings:
        - Forbidden path violations: HIGH / SECURITY
        - Architecture layer violations: HIGH / ARCHITECTURE
        - Naming convention violations: LOW / CONFIG
        - Entity invariant violations: MEDIUM / ARCHITECTURE (if entities defined)

        Args:
            diff: DiffFeatures to verify.

        Returns:
            List of AuditFinding objects.
        """
        spec_dict = self._spec_as_dict()
        findings: list[AuditFinding] = []

        # --- Forbidden path violations ---
        findings.extend(self._check_forbidden_paths(diff, spec_dict))

        # --- Architecture layer violations ---
        findings.extend(self._check_architecture_violations(diff, spec_dict))

        # --- Naming convention violations ---
        findings.extend(self._check_naming_conventions(diff, spec_dict))

        # --- Entity invariant violations ---
        findings.extend(self._check_entity_invariants(diff, spec_dict))

        return findings

    def verify_mined_spec(
        self,
        spec_dict: dict,
        diff: DiffFeatures,
        llm_client=None,
    ) -> list[AuditFinding]:
        """Verify a mined spec dict against a diff.

        Alternative entry point when spec is a raw dict instead of SpecModel.

        Args:
            spec_dict: Mined spec dictionary.
            diff: DiffFeatures to verify.
            llm_client: Optional LLM client for invariant checks.

        Returns:
            List of AuditFinding objects.
        """
        self.spec = spec_dict
        self.diff = diff
        self.llm_client = llm_client
        return self.verify(diff)

    def _spec_as_dict(self) -> dict:
        """Convert spec to dict format for consistent access."""
        if isinstance(self.spec, dict):
            return self.spec
        # SpecModel → minimal dict reconstruction
        return {
            "domain": getattr(self.spec, "goal", ""),
            "entities": [],
            "conventions": {},
            "forbidden_paths": getattr(self.spec, "out_of_scope", []),
            "architecture": {},
            "security_invariants": getattr(self.spec, "risk_areas", []),
        }

    def _check_forbidden_paths(
        self,
        diff: DiffFeatures,
        spec_dict: dict,
    ) -> list[AuditFinding]:
        """Detect forbidden path violations."""
        findings: list[AuditFinding] = []
        forbidden_paths = spec_dict.get("forbidden_paths", [])
        if not forbidden_paths:
            return findings

        changed_paths = {f.path for f in diff.files}
        violations: list[str] = []
        for forbidden in forbidden_paths:
            for changed in changed_paths:
                if forbidden in changed:
                    violations.append(changed)
                    break

        if violations:
            findings.append(
                AuditFinding(
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.SECURITY,
                    message=(
                        f"PR modifies {len(violations)} file(s) listed as "
                        f"forbidden: {'; '.join(violations[:3])}"
                    ),
                    evidence="; ".join(violations[:5]),
                )
            )
        return findings

    def _check_architecture_violations(
        self,
        diff: DiffFeatures,
        spec_dict: dict,
    ) -> list[AuditFinding]:
        """Detect architecture layer violations."""
        findings: list[AuditFinding] = []
        architecture = spec_dict.get("architecture", {})
        layers = architecture.get("layers", [])

        if not layers or len(layers) < 2:
            return findings

        violations: list[str] = []
        non_test_files = [f for f in diff.files if not f.is_test]

        for file in non_test_files:
            file_layer = self._detect_file_layer(file.path, layers)
            if file_layer is None:
                continue

            # Flag files whose path doesn't match any known layer prefix
            matched = False
            for layer in layers:
                prefix = layer.lower()
                if prefix in file.path.lower():
                    matched = True
                    break

            if not matched and len(non_test_files) > 1:
                violations.append(file.path)

        if violations and len(violations) >= 2:
            findings.append(
                AuditFinding(
                    severity=FindingSeverity.HIGH,
                    category=FindingCategory.ARCHITECTURE,
                    message=(
                        f"{len(violations)} file(s) do not match any known "
                        f"architecture layer: {'; '.join(violations[:3])}"
                    ),
                    evidence=f"Layers defined: {' → '.join(layers)}",
                )
            )
        return findings

    def _detect_file_layer(self, path: str, layers: list[str]) -> str | None:
        """Detect which layer a file belongs to based on its path."""
        path_lower = path.lower()
        for layer in layers:
            if layer.lower() in path_lower:
                return layer
        return None

    def _check_naming_conventions(
        self,
        diff: DiffFeatures,
        spec_dict: dict,
    ) -> list[AuditFinding]:
        """Detect naming convention violations."""
        findings: list[AuditFinding] = []
        conventions = spec_dict.get("conventions", {})
        naming = conventions.get("naming", "")

        if not naming:
            return findings

        non_test_files = [f for f in diff.files if not f.is_test]
        if not non_test_files:
            return findings

        violations: list[str] = []
        naming_lower = naming.lower()
        if "snake_case" in naming_lower:
            camel_re = re.compile(r"[a-z][A-Z]|[A-Z][a-z]")
            for f in non_test_files:
                if camel_re.search(f.path):
                    violations.append(f.path)

        if "camelcase" in naming_lower:
            # Check for snake_case in file paths (underscores)
            for f in non_test_files:
                if "_" in f.path:
                    violations.append(f.path)

        if "kebab-case" in naming_lower:
            for f in non_test_files:
                if "_" in f.path or re.search(r"[a-z][A-Z]", f.path):
                    violations.append(f.path)

        if violations:
            msg = (
                f"Naming convention violation: {len(violations)} "
                f"file(s) don't follow {naming}"
            )
            findings.append(
                AuditFinding(
                    severity=FindingSeverity.LOW,
                    category=FindingCategory.CONFIG,
                    message=msg,
                    evidence="; ".join(violations[:5]),
                )
            )
        return findings

    def _check_entity_invariants(
        self,
        diff: DiffFeatures,
        spec_dict: dict,
    ) -> list[AuditFinding]:
        """Detect entity invariant violations.

        Only performs LLM check if spec has entities with invariants, entity
        files were modified, and LLM client is available. Otherwise returns [].
        """
        findings: list[AuditFinding] = []
        entities = spec_dict.get("entities", [])

        if not entities:
            return findings

        # Find affected entities
        affected_entities: list[dict] = []
        for entity in entities:
            entity_files = entity.get("files", [])
            invariants = entity.get("invariants", [])
            if not invariants or not entity_files:
                continue

            changed_paths = {f.path for f in diff.files}
            affected = any(
                any(ef in changed for changed in changed_paths)
                for ef in entity_files
            )
            if affected:
                affected_entities.append(entity)

        if not affected_entities:
            return findings

        if self.llm_client is None:
            # Without LLM, just note that entity invariants exist
            for entity in affected_entities:
                if entity.get("invariants"):
                    findings.append(
                        AuditFinding(
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.ARCHITECTURE,
                            message=(
                                f"Entity '{entity.get('name', 'unknown')}' has "
                                f"invariants but LLM client not available to "
                                f"verify compliance."
                            ),
                            evidence="; ".join(entity.get("invariants", [])[:3]),
                        )
                    )
            return findings

        # Light LLM check
        for entity in affected_entities:
            invariants = entity.get("invariants", [])
            entity_files = entity.get("files", [])
            entity_name = entity.get("name", "unknown")

            changed_files = [
                f for f in diff.files
                if any(ef in f.path for ef in entity_files)
            ]

            invariant_text = "\n".join(f"- {inv}" for inv in invariants)
            check_prompt = (
                f"Entity '{entity_name}' has these invariants:\n"
                f"{invariant_text}\n\n"
                f"Modified files: {', '.join(f.path for f in changed_files)}\n"
                f'Check if any invariant was violated. Reply JSON: '
                f'{{"violated": true/false, "details": "explanation"}}'
            )

            try:
                import json as json_mod

                response = self.llm_client.complete(check_prompt)
                result = json_mod.loads(response)
                if result.get("violated"):
                    details = result.get("details", "")
                    findings.append(
                        AuditFinding(
                            severity=FindingSeverity.MEDIUM,
                            category=FindingCategory.ARCHITECTURE,
                            message=f"Entity '{entity_name}' invariant violated: {details}",
                            evidence=invariant_text,
                        )
                    )
            except Exception:
                pass

        return findings

    def get_spec_coverage(self, diff: DiffFeatures) -> float:
        """Calculate fraction of changed files covered by spec entities.

        Args:
            diff: DiffFeatures to check.

        Returns:
            Fraction (0.0-1.0) of changed files covered by entity file patterns.
        """
        spec_dict = self._spec_as_dict()
        entities = spec_dict.get("entities", [])
        if not entities:
            return 0.0

        all_entity_files: set[str] = set()
        for entity in entities:
            all_entity_files.update(entity.get("files", []))

        if not all_entity_files:
            return 0.0

        changed_paths = {f.path for f in diff.files}
        covered = sum(
            1 for changed in changed_paths
            if any(ef in changed for ef in all_entity_files)
        )
        return covered / len(changed_paths) if changed_paths else 0.0