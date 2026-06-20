"""Cheap keyword/score prefilter — drops obviously irrelevant posts before LLM spend.

Pure functions, fully unit-tested.
"""

from __future__ import annotations

from .config import PrefilterConfig
from .reddit_client import Post


def passes_prefilter(post: Post, cfg: PrefilterConfig) -> bool:
    """True if the post clears the score floor AND any keyword matches title/body.

    Keyword matching is case-insensitive. `cfg.keywords` are expected to already
    be lower-cased (see config loading); we lower-case defensively anyway.
    """
    if post.score < cfg.min_score:
        return False

    if not cfg.keywords:
        # No keywords configured → score floor is the only gate.
        return True

    haystack = f"{post.title}\n{post.selftext}".lower()
    return any(keyword.lower() in haystack for keyword in cfg.keywords)
