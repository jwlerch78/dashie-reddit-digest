"""Entrypoint: load config → fetch → prefilter → dedup → score → digest → send → mark seen.

Posts are marked seen only AFTER a successful send, so a crash doesn't silently drop
posts from a future run.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import Config, ConfigError, load_config
from .dedup import build_seen_store
from .digest import build_digest
from .mailer import send_digest
from .prefilter import passes_prefilter
from .reddit_client import fetch_recent_posts
from .scorer import score_posts

log = logging.getLogger("reddit_digest")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def run(config: Config, dry_run: bool) -> int:
    posts = fetch_recent_posts(config)

    prefiltered = [p for p in posts if passes_prefilter(p, config.prefilter)]
    log.info("%d/%d posts passed the prefilter", len(prefiltered), len(posts))

    store = build_seen_store(config)
    try:
        unseen = store.filter_unseen(prefiltered)
        log.info("%d posts are new (not previously surfaced)", len(unseen))

        scored = score_posts(unseen, config.scoring, api_key=config.anthropic_api_key)
        relevant = {
            pid: s for pid, s in scored.items() if s.relevance >= config.scoring.min_relevance
        }
        log.info(
            "%d posts at or above the relevance threshold (>= %d)",
            len(relevant),
            config.scoring.min_relevance,
        )

        digest = build_digest(relevant, config.digest)

        if not digest.items and not config.digest.send_when_empty:
            log.info("Nothing qualifies and send_when_empty is false — skipping email.")
            # Still mark scored posts seen so they aren't reconsidered.
            if not dry_run:
                store.mark_seen(unseen)
            return 0

        if dry_run:
            print("\n===== DRY RUN — digest preview (not sent) =====\n")
            print(digest.text_body)
            print("===== end preview — no email sent, nothing marked seen =====")
            return 0

        if config.smtp is None:
            log.error("No SMTP configuration available; cannot send. (Set email vars in .env.)")
            return 1

        send_digest(digest, config.smtp, config.digest)
        # Mark seen only after a successful send.
        store.mark_seen(unseen)
        return 0
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="reddit_digest",
        description="Personal, read-only Reddit relevance digest scored with the Anthropic API.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do everything except send the email and record seen posts; print the digest.",
    )
    parser.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml (default: config.yaml)"
    )
    args = parser.parse_args()

    _configure_logging()
    try:
        config = load_config(args.config, require_email=not args.dry_run)
    except ConfigError as exc:
        log.error("Configuration error: %s", exc)
        return 2

    return run(config, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
