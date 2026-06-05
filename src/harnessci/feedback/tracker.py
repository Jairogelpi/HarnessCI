"""SQLite-based feedback tracker for learning from team dismiss patterns.

Records dismissal events and adapts decision thresholds over time.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..models import Decision

_UTC = timezone.utc  # noqa: ERA001


def _now() -> str:
    return datetime.now(_UTC).isoformat()


def dismiss_pattern_key(
    finding_type: str,
    category: str,
    severity: str,
) -> str:
    """Generate a stable key for a finding type pattern."""
    return f"{category}:{severity}:{finding_type}"


def _ensure_db(db_path: Path) -> None:
    """Create schema if it doesn't exist."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS feedback_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_at    TEXT    NOT NULL,
                repo        TEXT    NOT NULL,
                pr_id       TEXT    NOT NULL,
                decision    TEXT    NOT NULL,
                finding_key TEXT    NOT NULL,
                category    TEXT    NOT NULL,
                severity    TEXT    NOT NULL,
                message     TEXT    NOT NULL,
                dismissed   INTEGER NOT NULL DEFAULT 0,
                reason      TEXT,
                reviewer    TEXT
            );

            CREATE TABLE IF NOT EXISTS dismiss_stats (
                finding_key  TEXT PRIMARY KEY,
                category     TEXT NOT NULL,
                severity     TEXT NOT NULL,
                total_seen      INTEGER NOT NULL DEFAULT 0,
                total_dismissed INTEGER NOT NULL DEFAULT 0,
                last_seen        TEXT,
                last_dismissed  TEXT,
                dismiss_rate REAL AS (
                    CASE WHEN total_seen > 0
                         THEN CAST(total_dismissed AS REAL) / total_seen
                         ELSE 0.0
                    END
                ) STORED
            );

            CREATE TABLE IF NOT EXISTS adapted_thresholds (
                repo               TEXT PRIMARY KEY,
                base_threshold     INTEGER NOT NULL DEFAULT 31,
                adapted_threshold  INTEGER NOT NULL DEFAULT 31,
                updated_at         TEXT NOT NULL,
                events_considered  INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS ix_feedback_events_finding_key
                ON feedback_events(finding_key);
            CREATE INDEX IF NOT EXISTS ix_feedback_events_repo
                ON feedback_events(repo, pr_id);
            """
        )
        conn.commit()
    finally:
        conn.close()


class FeedbackTracker:
    """Tracks feedback and adapts decision thresholds per repository."""

    def __init__(
        self,
        db_path: str | Path = ".harnessci/feedback.db",
        repo: str = "default",
    ) -> None:
        self.db_path = Path(db_path)
        self.repo = repo
        _ensure_db(self.db_path)

    # -------------------------------------------------------------------------
    # Record events
    # -------------------------------------------------------------------------

    def record_decision(
        self,
        pr_id: str,
        decision: Decision,
        findings: list[dict[str, Any]],
        reviewer: str | None = None,
    ) -> None:
        """Record the final decision and all findings for a PR."""
        conn = sqlite3.connect(self.db_path)
        try:
            for finding in findings:
                fkey = dismiss_pattern_key(
                    finding_type=finding.get("pattern", "unknown"),
                    category=str(finding.get("category", "")),
                    severity=str(finding.get("severity", "")),
                )
                conn.execute(
                    """
                    INSERT INTO feedback_events
                        (event_at, repo, pr_id, decision, finding_key,
                         category, severity, message, dismissed, reviewer)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        _now(),
                        self.repo,
                        pr_id,
                        decision.value,
                        fkey,
                        finding.get("category", ""),
                        finding.get("severity", ""),
                        finding.get("message", ""),
                        reviewer,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def record_dismiss(
        self,
        pr_id: str,
        finding_key: str,
        reason: str | None = None,
        reviewer: str | None = None,
    ) -> None:
        """Record that a finding was dismissed by a human reviewer."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                UPDATE feedback_events
                SET dismissed = 1, reason = ?, reviewer = ?
                WHERE repo = ? AND pr_id = ? AND finding_key = ?
                """,
                (reason, reviewer, self.repo, pr_id, finding_key),
            )
            # Update stats
            parts = finding_key.split(":")
            if len(parts) >= 3:
                category = parts[0]
                severity = parts[1]
                conn.execute(
                    """
                    INSERT INTO dismiss_stats
                        (finding_key, category, severity,
                         total_seen, total_dismissed, last_seen, last_dismissed)
                    VALUES (?, ?, ?, 1, 1, ?, ?)
                    ON CONFLICT(finding_key) DO UPDATE SET
                        total_seen = total_seen + 1,
                        total_dismissed = total_dismissed + 1,
                        last_seen = ?,
                        last_dismissed = ?
                    """,
                    (
                        finding_key,
                        category,
                        severity,
                        _now(),
                        _now(),
                        _now(),
                        _now(),
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def record_accepted(
        self,
        pr_id: str,
        finding_key: str,
        reviewer: str | None = None,
    ) -> None:
        """Record that a finding was accepted/addressed by the author."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                """
                INSERT OR IGNORE INTO feedback_events
                    (event_at, repo, pr_id, decision, finding_key,
                     category, severity, message, dismissed, reviewer)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    _now(),
                    self.repo,
                    pr_id,
                    Decision.REVIEW_REQUIRED.value,
                    finding_key,
                    "",
                    "",
                    "",
                    reviewer,
                ),
            )
            parts = finding_key.split(":")
            if len(parts) >= 3:
                category = parts[0]
                severity = parts[1]
                conn.execute(
                    """
                    INSERT INTO dismiss_stats
                        (finding_key, category, severity,
                         total_seen, total_dismissed, last_seen)
                    VALUES (?, ?, ?, 1, 0, ?)
                    ON CONFLICT(finding_key) DO UPDATE SET
                        total_seen = total_seen + 1,
                        last_seen = ?
                    """,
                    (finding_key, category, severity, _now(), _now()),
                )
            conn.commit()
        finally:
            conn.close()

    # -------------------------------------------------------------------------
    # Query patterns
    # -------------------------------------------------------------------------

    def get_dismiss_rate(self, finding_key: str) -> float:
        """Get the historical dismiss rate for a finding pattern."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT dismiss_rate FROM dismiss_stats WHERE finding_key = ?",
                (finding_key,),
            ).fetchone()
            return row[0] if row else 0.0
        finally:
            conn.close()

    def get_highly_dismissed_patterns(
        self,
        min_seen: int = 5,
        min_dismiss_rate: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Return patterns frequently dismissed (potential false positives)."""
        conn = sqlite3.connect(self.db_path)
        try:
            rows = conn.execute(
                """
                SELECT finding_key, category, severity,
                       total_seen, total_dismissed, dismiss_rate
                FROM dismiss_stats
                WHERE total_seen >= ? AND dismiss_rate >= ?
                ORDER BY dismiss_rate DESC
                """,
                (min_seen, min_dismiss_rate),
            ).fetchall()
            return [
                {
                    "finding_key": r[0],
                    "category": r[1],
                    "severity": r[2],
                    "total_seen": r[3],
                    "total_dismissed": r[4],
                    "dismiss_rate": r[5],
                }
                for r in rows
            ]
        finally:
            conn.close()

    def get_adapted_threshold(self) -> int:
        """Get the adapted risk threshold for the repo."""
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                "SELECT adapted_threshold FROM adapted_thresholds WHERE repo = ?",
                (self.repo,),
            ).fetchone()
            return row[0] if row else 31
        finally:
            conn.close()

    def adapt_threshold(self, base_threshold: int = 31) -> int:
        """Adapt risk threshold based on dismissal patterns.

        If the team dismisses >60% of REVIEW_REQUIRED findings,
        raise the threshold by 5 to reduce noise.
        """
        conn = sqlite3.connect(self.db_path)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*),
                       SUM(CASE WHEN dismissed = 1 THEN 1 ELSE 0 END)
                FROM feedback_events
                WHERE repo = ? AND decision = ?
                """,
                (self.repo, Decision.REVIEW_REQUIRED.value),
            ).fetchone()
            total = row[0] if row else 0
            dismissed = row[1] if row else 0

            if total < 10:
                threshold = base_threshold
            else:
                dismiss_rate = dismissed / total
                if dismiss_rate > 0.6:
                    threshold = min(base_threshold + 5, 61)
                elif dismiss_rate < 0.2:
                    threshold = max(base_threshold - 3, 20)
                else:
                    threshold = base_threshold

            conn.execute(
                """
                INSERT INTO adapted_thresholds
                    (repo, base_threshold, adapted_threshold, updated_at,
                     events_considered)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(repo) DO UPDATE SET
                    adapted_threshold = ?,
                    updated_at = ?,
                    events_considered = events_considered + ?
                """,
                (
                    self.repo,
                    base_threshold,
                    threshold,
                    _now(),
                    total,
                    threshold,
                    _now(),
                    total,
                ),
            )
            conn.commit()
            return threshold
        finally:
            conn.close()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of feedback data for the repo."""
        conn = sqlite3.connect(self.db_path)
        try:
            total_events = conn.execute(
                "SELECT COUNT(*) FROM feedback_events WHERE repo = ?",
                (self.repo,),
            ).fetchone()[0]

            total_dismissed = conn.execute(
                "SELECT COUNT(*) FROM feedback_events WHERE repo = ? AND dismissed = 1",
                (self.repo,),
            ).fetchone()[0]

            top_dismissed = conn.execute(
                """
                SELECT finding_key, total_dismissed, dismiss_rate
                FROM dismiss_stats
                WHERE total_seen >= 3
                ORDER BY dismiss_rate DESC
                LIMIT 10
                """,
            ).fetchall()

            return {
                "repo": self.repo,
                "total_events": total_events,
                "total_dismissed": total_dismissed,
                "dismiss_rate": total_dismissed / total_events if total_events > 0 else 0.0,
                "adapted_threshold": self.get_adapted_threshold(),
                "top_dismissed_patterns": [
                    {"finding_key": r[0], "dismissed": r[1], "rate": r[2]} for r in top_dismissed
                ],
            }
        finally:
            conn.close()


def load_tracker(
    repo: str = "default",
    db_path: str | Path = ".harnessci/feedback.db",
) -> FeedbackTracker:
    """Factory: load or create a feedback tracker."""
    return FeedbackTracker(db_path=db_path, repo=repo)
