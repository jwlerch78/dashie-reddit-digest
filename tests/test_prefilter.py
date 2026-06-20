"""Tests for the keyword/score prefilter."""

from reddit_digest.config import PrefilterConfig
from reddit_digest.prefilter import passes_prefilter
from reddit_digest.reddit_client import Post


def _post(title="", selftext="", score=0) -> Post:
    return Post(
        id="abc",
        subreddit="homeassistant",
        title=title,
        selftext=selftext,
        url="https://example.com",
        permalink="/r/homeassistant/comments/abc/x/",
        score=score,
        num_comments=0,
        created_utc=0.0,
        author="someone",
    )


def test_keyword_match_in_title():
    cfg = PrefilterConfig(min_score=0, keywords=["kiosk"])
    assert passes_prefilter(_post(title="Best wall KIOSK setup?"), cfg) is True


def test_keyword_match_in_body():
    cfg = PrefilterConfig(min_score=0, keywords=["family calendar"])
    assert passes_prefilter(_post(selftext="Looking for a family calendar display"), cfg) is True


def test_no_keyword_match():
    cfg = PrefilterConfig(min_score=0, keywords=["kiosk", "dashboard"])
    assert passes_prefilter(_post(title="My new gaming PC"), cfg) is False


def test_score_floor_blocks():
    cfg = PrefilterConfig(min_score=5, keywords=["kiosk"])
    assert passes_prefilter(_post(title="kiosk", score=2), cfg) is False
    assert passes_prefilter(_post(title="kiosk", score=10), cfg) is True


def test_empty_keywords_passes_on_score_only():
    cfg = PrefilterConfig(min_score=0, keywords=[])
    assert passes_prefilter(_post(title="anything at all"), cfg) is True


def test_case_insensitive():
    cfg = PrefilterConfig(min_score=0, keywords=["Wall Tablet"])
    assert passes_prefilter(_post(title="wall tablet recommendations"), cfg) is True
