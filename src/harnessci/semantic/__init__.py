"""Semantic domain learning for HarnessCI.

Provides embedding-based drift detection using Nomic embeddings and sqlite-vec.
"""

from __future__ import annotations

from .matcher import DRIFT_THRESHOLD, DriftMatcher, DriftSignal, create_matcher

__all__ = ["DriftMatcher", "DriftSignal", "create_matcher", "DRIFT_THRESHOLD"]
