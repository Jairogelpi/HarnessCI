"""Semantic indexer for HarnessCI domain learning.

Uses Nomic embeddings to index domain patterns from a mined spec.
Falls back gracefully when dependencies are unavailable.
"""

from __future__ import annotations

from pathlib import Path

from ..models import DiffFileChange

_nomic: object | None = None
try:
    import nomic

    _nomic = nomic
except ImportError:
    pass


def is_available() -> bool:
    """Check if Nomic embeddings are available."""
    return _nomic is not None


def index_repo(
    root: Path,
    spec: dict,
    db_path: Path,
) -> int:
    """Index all entities and conventions from a mined spec.

    Returns the number of patterns indexed, or 0 if unavailable.
    """
    if not is_available():
        return 0

    from .store import ensure_db, insert_embedding

    if not ensure_db(db_path):
        return 0

    count = 0
    embedder = _NomicEmbedder()

    # Index entities
    for entity in spec.get("entities", []):
        name = entity.get("name", "")
        files = entity.get("files", [])
        text = f"{name} entity: {', '.join(files)}"
        vector = embedder.embed(text)
        if vector and insert_embedding(db_path, vector, f"entity:{name}"):
            count += 1

    # Index conventions
    conventions = spec.get("conventions", {})
    for key, val in conventions.items():
        if val:
            text = f"convention {key}: {val}"
            vector = embedder.embed(text)
            if vector and insert_embedding(db_path, vector, f"convention:{key}"):
                count += 1

    # Index security invariants
    for inv in spec.get("security_invariants", []):
        vector = embedder.embed(f"security invariant: {inv}")
        if vector and insert_embedding(db_path, vector, "security_invariant"):
            count += 1

    return count


def reindex_if_stale(root: Path, db_path: Path) -> bool:
    """Check if repo changed since last indexing. Return True if reindex needed."""
    from ..spec_inference import spec_exists

    if not spec_exists(root):
        return False

    # If we have embeddings and spec hash hasn't changed, no reindex needed
    from .store import count_embeddings

    if count_embeddings(db_path) > 0:
        return False  # No reindex needed if embeddings exist
    return True


def _deterministic_embed(text: str, dim: int = 64) -> list[float]:
    """Generate deterministic embedding from text hash."""
    import hashlib

    h = hashlib.sha256(text.encode()).digest()
    # Repeat hash to fill dim dimensions
    extended = h * ((dim // len(h)) + 1)
    return [(extended[i] / 128.0) - 1.0 for i in range(dim)]


class _NomicEmbedder:
    """Nomic embed text wrapper with deterministic fallback."""

    def __init__(self) -> None:
        self._model: str = "nomic-embed-text-v1.5"

    def embed(self, text: str) -> list[float] | None:
        """Generate embedding, falling back to deterministic when nomic fails."""
        if is_available() and _nomic:
            try:
                result = _nomic.embed.Text([text], model=self._model)
                if hasattr(result, "embeddings"):
                    first = result.embeddings[0]
                    return first.tolist() if hasattr(first, "tolist") else list(first)
            except Exception:  # noqa: BLE001
                pass
        return _deterministic_embed(text)


def embed_diff_files(
    files: list[DiffFileChange],
    embedder: _NomicEmbedder | None = None,
) -> list[list[float]]:
    """Generate embeddings for a list of changed files."""
    if embedder is None:
        embedder = _NomicEmbedder()
    vectors = []
    for f in files:
        text = f.path
        if hasattr(f, "status"):
            text = f"{f.path} {f.status}"
        vec = embedder.embed(text)
        if vec:
            vectors.append(vec)
    return vectors
