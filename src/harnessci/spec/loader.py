"""Spec loading and creation for HarnessCI audit.

Supports loading from files, dicts, and inference from PR context.
"""

from __future__ import annotations

from pathlib import Path

from ..models import SpecModel
from .parser import parse_spec_file, parse_spec_text
from .store import load_mined_spec_dict


class SpecLoader:
    """Load or infer a SpecModel for audit."""

    def load_from_path(self, path: Path) -> SpecModel:
        """Load spec from a YAML or Markdown spec file.

        Args:
            path: Path to spec file (.yaml, .md, etc.)

        Returns:
            Parsed SpecModel from the file.

        Raises:
            SpecParseError: If file cannot be read or parsed.
        """
        return parse_spec_file(path)

    def load_from_text(self, spec_text: str, source: str | None = None) -> SpecModel:
        """Parse a spec from raw text.

        Args:
            spec_text: Raw spec text (markdown format).
            source: Optional source path or identifier.

        Returns:
            SpecModel parsed from the text.
        """
        return parse_spec_text(spec_text, source_path=source)

    def load_mined_spec(self, root: Path) -> SpecModel | None:
        """Load spec from .harnessci/spec.json if it exists.

        Args:
            root: Repository root path.

        Returns:
            SpecModel from mined spec, or None if not found.
        """
        spec_dict = load_mined_spec_dict(root)
        if spec_dict is None:
            return None
        return self._dict_to_specmodel(spec_dict)

    def load_or_infer(
        self,
        root: Path,
        diff_text: str | None = None,
        pr_title: str = "",
    ) -> SpecModel:
        """Load mined spec if available, otherwise create a lightweight fallback.

        If .harnessci/spec.json exists, load it. Otherwise return a SpecModel
        with goal=pr_title and usable=True as a minimal fallback.

        Args:
            root: Repository root path.
            diff_text: Optional diff text for inference.
            pr_title: PR title used as fallback goal.

        Returns:
            SpecModel loaded or inferred.
        """
        mined = self.load_mined_spec(root)
        if mined is not None:
            return mined

        # Fallback: use PR title as goal
        fallback = SpecModel(
            source_path=str(root / ".harnessci" / "spec.json"),
            goal=pr_title or "Code change",
            usable=True,
        )
        return fallback

    def ensure_initialized(
        self,
        root: Path,
        llm_client=None,
        diff_text: str | None = None,
        pr_title: str = "",
    ) -> SpecModel:
        """Ensure spec is available, mining if necessary.

        If .harnessci/spec.json does not exist and an LLM client is provided,
        run the miner to extract a spec. Otherwise return an empty SpecModel.

        Args:
            root: Repository root path.
            llm_client: Optional LLM client for mining.
            diff_text: Optional diff text for context.
            pr_title: PR title for fallback.

        Returns:
            SpecModel available for audit.
        """
        mined = self.load_mined_spec(root)
        if mined is not None:
            return mined

        if llm_client is not None:
            # Import here to avoid circular dependency at module level
            try:
                from .miner import mine_spec  # noqa: F401
            except ImportError:
                # miner.py not yet implemented; skip mining
                return SpecModel(
                    source_path=str(root / ".harnessci" / "spec.json"),
                    usable=False,
                )

            spec_dict, _ = mine_spec(root, llm_client, diff_text=diff_text)
            return self._dict_to_specmodel(spec_dict)

        return SpecModel(
            source_path=str(root / ".harnessci" / "spec.json"),
            usable=False,
        )

    def _dict_to_specmodel(self, spec_dict: dict) -> SpecModel:
        """Convert a mined spec dict to SpecModel.

        Handles the mined spec format (entities, conventions, forbidden_paths,
        architecture, etc.) vs the SpecModel format (goal, acceptance_criteria,
        out_of_scope, risk_areas, expected_scope).

        Args:
            spec_dict: Mined spec dictionary.

        Returns:
            SpecModel compatible with the audit system.
        """
        domain = spec_dict.get("domain", "")
        entities = spec_dict.get("entities", [])
        security_invariants = spec_dict.get("security_invariants", [])
        conventions = spec_dict.get("conventions", {})

        # Build goal from domain + entities
        goal_parts = [domain] if domain else []
        if entities:
            entity_names = [e.get("name", "") for e in entities if e.get("name")]
            if entity_names:
                goal_parts.append(f"Entities: {', '.join(entity_names)}")

        # Build acceptance criteria from entities + security invariants
        acceptance_criteria: list[str] = []
        for entity in entities:
            invariants = entity.get("invariants", [])
            for inv in invariants:
                if inv:
                    acceptance_criteria.append(f"{entity.get('name', 'Entity')}: {inv}")

        for inv in security_invariants:
            if inv:
                acceptance_criteria.append(f"Security: {inv}")

        # Naming convention as acceptance criteria
        naming = conventions.get("naming", "")
        if naming:
            acceptance_criteria.append(f"Naming: {naming}")

        # Architecture layers as acceptance criteria
        arch = spec_dict.get("architecture", {})
        layers = arch.get("layers", [])
        if layers:
            acceptance_criteria.append(f"Layers: {' → '.join(layers)}")

        # Out of scope from forbidden_paths
        out_of_scope = spec_dict.get("forbidden_paths", [])

        # Risk areas from security invariants
        risk_areas = [inv for inv in security_invariants if inv]

        return SpecModel(
            source_path=".harnessci/spec.json",
            goal=" ".join(goal_parts) or "Repository specification",
            acceptance_criteria=acceptance_criteria,
            out_of_scope=out_of_scope,
            risk_areas=risk_areas,
            usable=True,
        )
