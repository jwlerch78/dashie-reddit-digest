"""Score posts for relevance with the Anthropic API.

Posts are batched into a single API call each. The model is instructed to return
ONLY a JSON array; we parse defensively (stripping any accidental code fences) and
skip a batch rather than crash if it can't be parsed.

Note: the scoring model defaults to Haiku 4.5, which does not support the `effort`
or `thinking` parameters — so we deliberately omit them. To use a sharper model,
set `scoring.model: claude-sonnet-4-6` in config.yaml.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import anthropic

from .config import ScoringConfig
from .reddit_client import Post

log = logging.getLogger(__name__)

# Plain description of MY personal interests — used only to judge how relevant a post
# is to what I want to read. Not a product, not marketing copy.
INTERESTS = (
    "I'm a hobbyist interested in home dashboards, family organizers, and wall-mounted "
    "tablets or TVs used as smart-home displays and kiosks — things like Home Assistant "
    "dashboards, shared family calendars, and photo displays. I follow a few communities "
    "on these topics to keep up with what people are building and discussing."
)

_OUTPUT_CONTRACT = """For EACH post in the batch, return one JSON object with exactly these keys:
- "id": the post id you were given (string)
- "relevance": integer 0-10 — how relevant this post is to MY interests above
  (10 = exactly the kind of discussion I want to see, 0 = unrelated)
- "angle": one sentence on why this is or isn't relevant to my interests
- "spam_risk": "low" | "medium" | "high" — if I chose to join the discussion, how likely
  is it that a comment would come across as self-promotion rather than genuinely helpful?
- "talking_points": OPTIONAL private notes for my own reference — what's being discussed
  and, if I happen to have genuinely useful knowledge to contribute as a community member,
  what that might be. Do NOT write a ready-to-post reply. Do NOT promote, recommend, or
  even name any specific product, app, or brand. Do NOT write anything that reads as
  marketing. If there's nothing genuinely useful to note, return an empty string.

Return ONLY a JSON array of these objects. No prose, no explanation, no markdown code
fences — just the raw JSON array."""

SYSTEM_PROMPT = (
    "You are a personal research assistant for a single hobbyist. You help me keep up "
    "with discussions in a few online communities I follow: you rate how relevant each "
    "post is to my interests and jot down private notes for my own reading. You never "
    "write content to be posted, and you never promote or recommend products.\n\n"
    f"MY INTERESTS:\n{INTERESTS}\n\n"
    f"{_OUTPUT_CONTRACT}"
)

# Keep prompt size bounded — long self-posts add tokens without improving scoring.
_MAX_SELFTEXT_CHARS = 2000
_MAX_COMMENT_CHARS = 400


@dataclass
class ScoredPost:
    post: Post
    relevance: int
    angle: str
    spam_risk: str
    talking_points: str


def _post_payload(post: Post) -> dict:
    return {
        "id": post.id,
        "subreddit": post.subreddit,
        "title": post.title,
        "selftext": post.selftext[:_MAX_SELFTEXT_CHARS],
        "score": post.score,
        "num_comments": post.num_comments,
        "top_comments": [c[:_MAX_COMMENT_CHARS] for c in post.top_comments],
    }


def _chunks(items: list[Post], size: int):
    for i in range(0, len(items), max(1, size)):
        yield items[i : i + size]


def _strip_fences(text: str) -> str:
    """Remove leading/trailing whitespace and an accidental ```json ... ``` fence."""
    text = text.strip()
    if text.startswith("```"):
        # drop the opening fence line (``` or ```json)
        newline = text.find("\n")
        text = text[newline + 1 :] if newline != -1 else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _parse_json_array(text: str) -> list[dict]:
    cleaned = _strip_fences(text)
    data = json.loads(cleaned)
    if not isinstance(data, list):
        raise ValueError("Expected a top-level JSON array")
    return [item for item in data if isinstance(item, dict)]


def _make_client(api_key: str | None, client: anthropic.Anthropic | None) -> anthropic.Anthropic:
    if client is not None:
        return client
    return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()


def score_posts(
    posts: list[Post],
    cfg: ScoringConfig,
    *,
    api_key: str | None = None,
    client: anthropic.Anthropic | None = None,
) -> dict[str, ScoredPost]:
    """Score posts and return a mapping of post id -> ScoredPost.

    A batch that fails to call the API or parse is logged and skipped; the rest of
    the run continues.
    """
    if not posts:
        return {}

    api = _make_client(api_key, client)
    by_id = {p.id: p for p in posts}
    results: dict[str, ScoredPost] = {}

    for batch in _chunks(posts, cfg.batch_size):
        user_content = json.dumps([_post_payload(p) for p in batch], ensure_ascii=False)
        try:
            response = api.messages.create(
                model=cfg.model,
                max_tokens=cfg.max_tokens,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            parsed = _parse_json_array(text)
        except Exception as exc:  # one bad batch shouldn't kill the digest
            log.warning("Scoring batch failed (%d posts), skipping: %s", len(batch), exc)
            continue

        for item in parsed:
            post = by_id.get(str(item.get("id", "")))
            if post is None:
                continue
            try:
                relevance = int(item.get("relevance", 0))
            except (TypeError, ValueError):
                relevance = 0
            results[post.id] = ScoredPost(
                post=post,
                relevance=max(0, min(10, relevance)),
                angle=str(item.get("angle", "")).strip(),
                spam_risk=str(item.get("spam_risk", "")).strip().lower() or "unknown",
                talking_points=str(item.get("talking_points", "")).strip(),
            )

    log.info("Scored %d/%d posts", len(results), len(posts))
    return results
