"""SQLite-backed seen-post store for de-duplication.

Stores only post IDs (and a first-seen timestamp). No post content is retained.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
import urllib.parse
import urllib.request
from collections.abc import Iterable

from .config import Config
from .reddit_client import Post

log = logging.getLogger(__name__)

_SEEN_TABLE = "reddit_digest_seen"


def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


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


class SupabaseSeenStore:
    """Durable seen-post store backed by a Supabase (PostgREST) table.

    Used in the cloud, where a local SQLite file would not survive a stateless
    run. Talks to PostgREST over plain HTTP (stdlib `urllib`) — no extra deps.
    Requires the table created by `supabase_schema.sql` and a service-role key
    (which bypasses RLS for this backend job).
    """

    def __init__(self, url: str, key: str, table: str = _SEEN_TABLE, timeout: int = 30):
        self._endpoint = url.rstrip("/") + "/rest/v1/" + table
        self._key = key
        self._timeout = timeout

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Accept": "application/json",
        }
        if extra:
            headers.update(extra)
        return headers

    def filter_unseen(self, posts: Iterable[Post]) -> list[Post]:
        posts = list(posts)
        if not posts:
            return []
        seen: set[str] = set()
        for chunk in _chunked([p.id for p in posts], 100):
            query = urllib.parse.urlencode(
                {"select": "post_id", "post_id": f"in.({','.join(chunk)})"}
            )
            req = urllib.request.Request(f"{self._endpoint}?{query}", headers=self._headers())
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                rows = json.loads(resp.read().decode("utf-8"))
            seen.update(row["post_id"] for row in rows)
        return [p for p in posts if p.id not in seen]

    def mark_seen(self, posts: Iterable[Post]) -> None:
        rows = [{"post_id": p.id} for p in posts]
        if not rows:
            return
        headers = self._headers(
            {
                "Content-Type": "application/json",
                # Insert, ignoring rows whose post_id already exists.
                "Prefer": "return=minimal,resolution=ignore-duplicates",
            }
        )
        for chunk in _chunked(rows, 500):
            req = urllib.request.Request(
                self._endpoint,
                data=json.dumps(chunk).encode("utf-8"),
                method="POST",
                headers=headers,
            )
            urllib.request.urlopen(req, timeout=self._timeout).close()

    def close(self) -> None:  # nothing to close; symmetry with SeenStore
        pass

    def __enter__(self) -> "SupabaseSeenStore":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def build_seen_store(config: Config) -> SeenStore | SupabaseSeenStore:
    """Pick the durable Supabase backend when configured, else local SQLite."""
    if config.supabase_url and config.supabase_key:
        log.info("Using Supabase seen-store (durable, cloud)")
        return SupabaseSeenStore(config.supabase_url, config.supabase_key)
    log.info("Using local SQLite seen-store: %s", config.db_path)
    return SeenStore(config.db_path)
