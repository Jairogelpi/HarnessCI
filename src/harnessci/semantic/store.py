"""Vector store for semantic domain learning using sqlite-vec.

Uses sqlite3 + sqlite_vec.load() for embedded vector storage.
"""

from __future__ import annotations

import math
import sqlite3
import struct
from pathlib import Path

try:
    import sqlite_vec

    _VEC_AVAILABLE = True
except ImportError:
    _VEC_AVAILABLE = False

_SCHEMA_SQL = (
    "CREATE TABLE IF NOT EXISTS embeddings ("
    "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
    "  embedding BLOB,"
    "  meta TEXT,"
    "  created_at TEXT DEFAULT CURRENT_TIMESTAMP"
    ");"
    "CREATE INDEX IF NOT EXISTS idx_created ON embeddings(created_at);"
)


def is_available() -> bool:
    return _VEC_AVAILABLE


def _connection(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def ensure_db(db_path: Path) -> bool:
    if not _VEC_AVAILABLE:
        return False
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = _connection(db_path)
        for stmt in _SCHEMA_SQL.split(";"):
            if stmt.strip():
                conn.execute(stmt.strip())  # noqa: S608
        conn.commit()
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def insert_embedding(db_path: Path, vector: list[float], meta: str = "") -> bool:
    if not _VEC_AVAILABLE:
        return False
    try:
        blob = struct.pack(f"{len(vector)}f", *vector)
        conn = _connection(db_path)
        conn.execute(
            "INSERT INTO embeddings(embedding, meta) VALUES (?, ?)",
            (blob, meta),
        )
        conn.commit()
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def search_similar(
    db_path: Path, query_vector: list[float], top_k: int = 5,
) -> list[dict[str, object]]:
    if not _VEC_AVAILABLE or not db_path.exists():
        return []
    try:
        conn = _connection(db_path)
        cur = conn.execute("SELECT id, embedding, meta FROM embeddings")
        results: list[dict[str, object]] = []
        for row in cur:
            emb_blob = row[1]
            stored = struct.unpack(f"{len(query_vector)}f", emb_blob)
            dist = _cosine(query_vector, list(stored))
            results.append({"id": row[0], "distance": dist, "meta": row[2] or ""})
        conn.close()
        results.sort(key=lambda x: float(x["distance"]))  # type: ignore[arg-type]
        return results[:top_k]
    except Exception:  # noqa: BLE001
        return []


def count_embeddings(db_path: Path) -> int:
    if not _VEC_AVAILABLE or not db_path.exists():
        return 0
    try:
        conn = _connection(db_path)
        cur = conn.execute("SELECT COUNT(*) FROM embeddings")
        result = cur.fetchone()[0] or 0
        conn.close()
        return result
    except Exception:  # noqa: BLE001
        return 0


def clear_embeddings(db_path: Path) -> bool:
    if not _VEC_AVAILABLE:
        return False
    try:
        conn = _connection(db_path)
        conn.execute("DELETE FROM embeddings")
        conn.commit()
        conn.close()
        return True
    except Exception:  # noqa: BLE001
        return False


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - (dot / (norm_a * norm_b))