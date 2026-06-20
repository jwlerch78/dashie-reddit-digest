"""Read-only Reddit access via PRAW.

HARD RULE: this module must NEVER call any write method on the Reddit API
(no submit / comment / reply / vote / message / save / subscribe). The PRAW
instance is configured read-only and only listing + read calls are made here.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import praw

from .config import Config, RedditCredentials

log = logging.getLogger(__name__)

# How many top comments to pull per post for scoring context. Kept small to
# respect rate limits.
_MAX_COMMENTS = 5


@dataclass
class Post:
    id: str
    subreddit: str
    title: str
    selftext: str
    url: str
    permalink: str
    score: int
    num_comments: int
    created_utc: float
    author: str
    top_comments: list[str] = field(default_factory=list)


def build_reddit(creds: RedditCredentials) -> praw.Reddit:
    """Build a read-only PRAW instance. Intentionally never used for writes."""
    reddit = praw.Reddit(
        client_id=creds.client_id,
        client_secret=creds.client_secret,
        username=creds.username,
        password=creds.password,
        user_agent=creds.user_agent,
    )
    # Enforce read-only intent at the library level.
    reddit.read_only = True
    return reddit


def _top_comments(submission) -> list[str]:
    """Fetch up to `_MAX_COMMENTS` top-level comments as plain text for context."""
    comments: list[str] = []
    try:
        submission.comment_sort = "top"
        submission.comments.replace_more(limit=0)
        for comment in submission.comments[:_MAX_COMMENTS]:
            body = getattr(comment, "body", "") or ""
            if body:
                comments.append(body.strip())
    except Exception as exc:  # comment fetch is best-effort; never fail the run
        log.warning("Could not fetch comments for %s: %s", submission.id, exc)
    return comments


def _listing(subreddit, which: str, limit: int):
    if which == "hot":
        return subreddit.hot(limit=limit)
    if which == "rising":
        return subreddit.rising(limit=limit)
    return subreddit.new(limit=limit)


def fetch_recent_posts(config: Config, reddit: praw.Reddit | None = None) -> list[Post]:
    """Fetch recent posts from each configured subreddit (read-only).

    Filters to posts created within `lookback_hours` and caps each subreddit at
    `max_posts_per_sub`.
    """
    reddit = reddit or build_reddit(config.reddit)
    cutoff = time.time() - config.lookback_hours * 3600
    posts: list[Post] = []

    for name in config.subreddits:
        log.info("Fetching r/%s (%s, up to %d)", name, config.listing, config.max_posts_per_sub)
        try:
            subreddit = reddit.subreddit(name)
            for submission in _listing(subreddit, config.listing, config.max_posts_per_sub):
                if submission.created_utc < cutoff:
                    # `new` is reverse-chronological, so we could break; hot/rising
                    # are not, so just skip to be safe across listings.
                    continue
                posts.append(
                    Post(
                        id=submission.id,
                        subreddit=name,
                        title=submission.title or "",
                        selftext=submission.selftext or "",
                        url=submission.url or "",
                        permalink=submission.permalink or "",
                        score=int(submission.score or 0),
                        num_comments=int(submission.num_comments or 0),
                        created_utc=float(submission.created_utc),
                        author=str(submission.author) if submission.author else "[deleted]",
                        top_comments=_top_comments(submission),
                    )
                )
        except Exception as exc:  # one bad subreddit shouldn't abort the whole run
            log.warning("Failed to fetch r/%s: %s", name, exc)

    log.info("Fetched %d recent posts total", len(posts))
    return posts
