"""Diff parsing and feature extraction for HarnessCI."""

from .features import build_diff_features, classify_files
from .parser import parse_diff_text

__all__ = ["parse_diff_text", "classify_files", "build_diff_features"]
