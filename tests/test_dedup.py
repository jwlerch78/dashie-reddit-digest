"""Tests for the SQLite seen-post store."""

from reddit_digest.dedup import SeenStore
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
