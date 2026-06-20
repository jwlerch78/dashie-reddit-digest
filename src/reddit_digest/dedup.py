"""SQLite-backed seen-post store for de-duplication.

Stores only post IDs (and a first-seen timestamp). No post content is retained.
"""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Iterable

from .reddit_client import Post


class SeenStore:
    """Tracks which post IDs have already been surfaced in a digest."""

    def __init__(self, db_path: str = "seen.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            "  post_id TEXT PRIMARY KEY,"
            "  first_seen_utc INTEGER"
            ")"
        )
        self._conn.commit()

    def filter_unseen(self, posts: Iterable[Post]) -> list[Post]:
        """Return only the posts whose IDs are not already recorded as seen."""
        posts = list(posts)
        if not posts:
            return []
        seen_ids = self._seen_ids({p.id for p in posts})
        return [p for p in posts if p.id not in seen_ids]

    def mark_seen(self, posts: Iterable[Post]) -> None:
        """Record the given posts as seen (idempotent)."""
        now = int(time.time())
        rows = [(p.id, now) for p in posts]
        if not rows:
            return
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen (post_id, first_seen_utc) VALUES (?, ?)",
            rows,
        )
        self._conn.commit()

    def _seen_ids(self, candidate_ids: set[str]) -> set[str]:
        if not candidate_ids:
            return set()
        placeholders = ",".join("?" for _ in candidate_ids)
        cur = self._conn.execute(
            f"SELECT post_id FROM seen WHERE post_id IN ({placeholders})",
            tuple(candidate_ids),
        )
        return {row[0] for row in cur.fetchall()}

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SeenStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
