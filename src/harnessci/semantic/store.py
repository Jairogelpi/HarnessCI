"""Vector store for semantic domain learning using sqlite-vec.

Provides lightweight local vector storage with fallback when sqlite-vec
is not available.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

_sqlite_vec: object | None = None
try:
    import sqlite_vec as _sv

    _sqlite_vec = _sv
except ImportError:
    pass

_VEC_AVAILABLE = _sqlite_vec is not None

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    embedding BLOB,
    meta TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_created ON embeddings(created_at);
"""


def is_available() -> bool:
    """Check if sqlite-vec is available."""
    return _VEC_AVAILABLE


def ensure_db(db_path: Path) -> bool:
    """Create vector DB with schema. Returns True if available."""
    if not _VEC_AVAILABLE:
        return False
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with _sqlite_vec.connect(db_path) as conn:  # type: ignore[union-attr]
            _sqlite_vec.load_module(conn)  # type: ignore[union-attr]
            for stmt in _SCHEMA_SQL.split(";"):
                if stmt.strip():
                    conn.execute(stmt)  # noqa: S608
        return True
    except Exception:  # noqa: BLE001
        return False


def insert_embedding(db_path: Path, vector: list[float], meta: str = "") -> bool:
    """Insert a single embedding. Returns True on success."""
    if not _VEC_AVAILABLE:
        return False
    try:
        blob = struct.pack(f"{len(vector)}f", *vector)
        with _sqlite_vec.connect(db_path) as conn:  # type: ignore[union-attr]
            conn.execute("INSERT INTO embeddings(embedding, meta) VALUES (?, ?)", (blob, meta))
        return True
    except Exception:  # noqa: BLE001
        return False


def search_similar(
    db_path: Path,
    query_vector: list[float],
    top_k: int = 5,
) -> list[dict[str, object]]:
    """Search for similar embeddings. Returns list of {id, distance, meta}."""
    if not _VEC_AVAILABLE or not db_path.exists():
        return []
    try:
        with _sqlite_vec.connect(db_path) as conn:  # type: ignore[union-attr]
            cur = conn.execute("SELECT id, embedding, meta FROM embeddings")
            results: list[dict[str, object]] = []
            for row in cur:
                emb_blob = row[1]
                stored = struct.unpack(f"{len(query_vector)}f", emb_blob)
                dist = _cosine(query_vector, list(stored))
                results.append({"id": row[0], "distance": dist, "meta": row[2] or ""})
            results.sort(key=lambda x: float(x["distance"]))  # type: ignore[arg-type]
            return results[:top_k]
    except Exception:  # noqa: BLE001
        return []


def count_embeddings(db_path: Path) -> int:
    """Return total embedding count."""
    if not _VEC_AVAILABLE or not db_path.exists():
        return 0
    try:
        with _sqlite_vec.connect(db_path) as conn:  # type: ignore[union-attr]
            cur = conn.execute("SELECT COUNT(*) FROM embeddings")
            return cur.fetchone()[0] or 0
    except Exception:  # noqa: BLE001
        return 0


def clear_embeddings(db_path: Path) -> bool:
    """Delete all embeddings."""
    if not _VEC_AVAILABLE:
        return False
    try:
        with _sqlite_vec.connect(db_path) as conn:  # type: ignore[union-attr]
            conn.execute("DELETE FROM embeddings")
        return True
    except Exception:  # noqa: BLE001
        return False


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - (dot / (norm_a * norm_b))