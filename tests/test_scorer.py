"""Tests for the Anthropic scoring layer.

The Anthropic client is mocked — no network calls are made.
"""

from types import SimpleNamespace

from reddit_digest.config import ScoringConfig
from reddit_digest.reddit_client import Post
from reddit_digest.scorer import score_posts


def _post(pid: str, title: str = "t") -> Post:
    return Post(
        id=pid,
        subreddit="homeassistant",
        title=title,
        selftext="",
        url="https://example.com",
        permalink=f"/r/homeassistant/comments/{pid}/x/",
        score=1,
        num_comments=0,
        created_utc=0.0,
        author="a",
    )


class FakeMessages:
    """Stands in for client.messages; returns a canned text block."""

    def __init__(self, text: str):
        self._text = text
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self._text)])


class FakeClient:
    def __init__(self, text: str):
        self.messages = FakeMessages(text)


def _cfg(batch_size: int = 8) -> ScoringConfig:
    return ScoringConfig(model="claude-haiku-4-5-20251001", batch_size=batch_size, min_relevance=7)


def test_parses_plain_json_array():
    payload = (
        '[{"id":"a","relevance":9,"angle":"good fit","spam_risk":"low",'
        '"talking_points":"Try X."}]'
    )
    client = FakeClient(payload)
    result = score_posts([_post("a")], _cfg(), client=client)
    assert result["a"].relevance == 9
    assert result["a"].spam_risk == "low"
    assert result["a"].talking_points == "Try X."


def test_strips_code_fences():
    payload = (
        '```json\n[{"id":"a","relevance":8,"angle":"x","spam_risk":"medium",'
        '"talking_points":"y"}]\n```'
    )
    client = FakeClient(payload)
    result = score_posts([_post("a")], _cfg(), client=client)
    assert result["a"].relevance == 8
    assert result["a"].spam_risk == "medium"


def test_bad_json_is_skipped_not_raised():
    client = FakeClient("not json at all")
    result = score_posts([_post("a")], _cfg(), client=client)
    assert result == {}


def test_clamps_out_of_range_relevance():
    payload = '[{"id":"a","relevance":99,"angle":"","spam_risk":"low","talking_points":""}]'
    client = FakeClient(payload)
    result = score_posts([_post("a")], _cfg(), client=client)
    assert result["a"].relevance == 10


def test_unknown_ids_ignored():
    payload = '[{"id":"zzz","relevance":9,"angle":"","spam_risk":"low","talking_points":""}]'
    client = FakeClient(payload)
    result = score_posts([_post("a")], _cfg(), client=client)
    assert result == {}


def test_batches_respect_batch_size():
    payload = "[]"
    client = FakeClient(payload)
    posts = [_post(str(i)) for i in range(20)]
    score_posts(posts, _cfg(batch_size=8), client=client)
    # 20 posts / batch 8 => 3 API calls
    assert len(client.messages.calls) == 3


def test_empty_posts_no_calls():
    client = FakeClient("[]")
    assert score_posts([], _cfg(), client=client) == {}
    assert client.messages.calls == []
