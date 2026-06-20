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

# Short, factual, neutral description used only to judge relevance — NOT ad copy.
PRODUCT_CONTEXT = (
    "Dashie is a self-hosted family dashboard / kiosk app for wall-mounted tablets and "
    "TVs. It shows a shared family calendar, photos, weather, chores, and can embed Home "
    "Assistant dashboards. It targets people who want an always-on wall display or a "
    "Skylight/Hearth-style family organizer they can run on their own hardware."
)

_OUTPUT_CONTRACT = """For EACH post in the batch, return one JSON object with exactly these keys:
- "id": the post id you were given (string)
- "relevance": integer 0-10 — how relevant this post is to someone building or running
  a family-dashboard / smart-home-display product (10 = perfect fit, 0 = unrelated)
- "angle": one sentence explaining why this is or isn't relevant
- "spam_risk": "low" | "medium" | "high" — would a reply here read as self-promotion?
- "suggested_comment": a helpful, human-sounding draft reply that answers the person's
  actual question FIRST. Only mention a dashboard/kiosk approach if it's directly
  relevant and genuinely helpful. It must never read as an advertisement.

Bias toward genuinely helpful answers. If a post would only let you reply by plugging a
product, mark spam_risk "high" so the operator can skip it.

Return ONLY a JSON array of these objects. No prose, no explanation, no markdown code
fences — just the raw JSON array."""

SYSTEM_PROMPT = (
    "You are a relevance-scoring assistant for a personal tool. You evaluate Reddit posts "
    "for how relevant they are to the following product, and draft optional, human-reviewed "
    "reply suggestions.\n\n"
    f"PRODUCT CONTEXT:\n{PRODUCT_CONTEXT}\n\n"
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
    suggested_comment: str


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
                suggested_comment=str(item.get("suggested_comment", "")).strip(),
            )

    log.info("Scored %d/%d posts", len(results), len(posts))
    return results
