"""Tests for the seen-post store (SQLite + backend selection)."""

from reddit_digest.dedup import SeenStore, SupabaseSeenStore, build_seen_store
from reddit_digest.reddit_client import Post


def _post(pid: str) -> Post:
    return Post(
        id=pid,
        subreddit="smarthome",
        title="t",
        selftext="",
        url="https://example.com",
        permalink=f"/r/smarthome/comments/{pid}/x/",
        score=0,
        num_comments=0,
        created_utc=0.0,
        author="a",
    )


def test_unseen_then_seen(tmp_path):
    db = str(tmp_path / "seen.db")
    posts = [_post("a"), _post("b"), _post("c")]

    with SeenStore(db) as store:
        assert {p.id for p in store.filter_unseen(posts)} == {"a", "b", "c"}
        store.mark_seen([_post("a"), _post("b")])
        assert [p.id for p in store.filter_unseen(posts)] == ["c"]


def test_persists_across_instances(tmp_path):
    db = str(tmp_path / "seen.db")
    with SeenStore(db) as store:
        store.mark_seen([_post("x")])

    with SeenStore(db) as store:
        assert [p.id for p in store.filter_unseen([_post("x"), _post("y")])] == ["y"]


def test_mark_seen_is_idempotent(tmp_path):
    db = str(tmp_path / "seen.db")
    with SeenStore(db) as store:
        store.mark_seen([_post("dup")])
        store.mark_seen([_post("dup")])  # must not raise on duplicate PK
        assert store.filter_unseen([_post("dup")]) == []


def test_empty_inputs(tmp_path):
    db = str(tmp_path / "seen.db")
    with SeenStore(db) as store:
        assert store.filter_unseen([]) == []
        store.mark_seen([])  # no-op


class _FakeConfig:
    def __init__(self, db_path, supabase_url=None, supabase_key=None):
        self.db_path = db_path
        self.supabase_url = supabase_url
        self.supabase_key = supabase_key


def test_build_seen_store_picks_sqlite_without_supabase(tmp_path):
    store = build_seen_store(_FakeConfig(str(tmp_path / "seen.db")))
    assert isinstance(store, SeenStore)
    store.close()


def test_build_seen_store_picks_supabase_when_configured(tmp_path):
    store = build_seen_store(
        _FakeConfig(str(tmp_path / "seen.db"), "https://x.supabase.co", "service-key")
    )
    assert isinstance(store, SupabaseSeenStore)
    store.close()
