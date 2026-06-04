"""Drift detection using semantic embeddings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

DRIFT_THRESHOLD = 0.55


@dataclass
class DriftSignal:
    type: str
    severity: str
    evidence: str
    changed_files: list[str]


class DriftMatcher:
    def __init__(self, db_path: Path, embedder=None, threshold: float = DRIFT_THRESHOLD):
        self.db_path = db_path
        self.embedder = embedder
        self.threshold = threshold

    def detect_drift(self, files):
        if not self.db_path.exists():
            return []
        signals = []
        changed_items = []
        for f in files:
            vec = self._embed(f.path)
            if vec:
                changed_items.append((f.path, vec))
        if not changed_items:
            return []
        from .store import search_similar

        drifted_paths = []
        for path, vec in changed_items:
            results = search_similar(self.db_path, vec, top_k=3)
            if not results or results[0]["distance"] > self.threshold:
                drifted_paths.append(path)
        non_test = [f.path for f in files if not f.is_test and not f.is_docs and not f.is_config]
        if not non_test:
            return []
        fraction = len(drifted_paths) / len(non_test)
        if fraction >= 0.5:
            signals.append(
                DriftSignal(
                    type="major_scope_expansion",
                    severity="high",
                    evidence=f"{len(drifted_paths)}/{len(non_test)} files outside learned domain",
                    changed_files=drifted_paths,
                )
            )
        elif fraction >= 0.25:
            signals.append(
                DriftSignal(
                    type="partial_drift",
                    severity="medium",
                    evidence=f"{len(drifted_paths)}/{len(non_test)} files partially outside domain",
                    changed_files=drifted_paths,
                )
            )
        elif drifted_paths:
            signals.append(
                DriftSignal(
                    type="minor_outlier",
                    severity="low",
                    evidence=f"{len(drifted_paths)} outlier file(s) not matching domain",
                    changed_files=drifted_paths,
                )
            )
        return signals

    def compute_drift_score(self, files):
        if not self.db_path.exists():
            return 0.0
        from .store import search_similar

        non_test = [f for f in files if not f.is_test and not f.is_docs and not f.is_config]
        if not non_test:
            return 0.0
        drifted = 0
        for f in non_test:
            vec = self._embed(f.path)
            if not vec:
                drifted += 1
                continue
            results = search_similar(self.db_path, vec, top_k=1)
            if not results or results[0]["distance"] > self.threshold:
                drifted += 1
        return drifted / len(non_test)

    def _embed(self, text):
        try:
            if self.embedder is not None:
                return self.embedder.embed(text)
        except Exception:
            pass
        from .indexer import _deterministic_embed
        return _deterministic_embed(text)


def create_matcher(db_path, embedder=None):
    return DriftMatcher(db_path=db_path, embedder=embedder)
