"""Load and validate configuration from `.env` (secrets) + `config.yaml` (tunables)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or malformed."""


@dataclass
class PrefilterConfig:
    min_score: int = 0
    keywords: list[str] = field(default_factory=list)


@dataclass
class ScoringConfig:
    model: str = "claude-haiku-4-5-20251001"
    batch_size: int = 8
    min_relevance: int = 7
    max_tokens: int = 4096


@dataclass
class DigestConfig:
    max_items: int = 25
    subject_prefix: str = "[Dashie Digest]"
    send_when_empty: bool = False


@dataclass
class RedditCredentials:
    client_id: str
    client_secret: str
    username: str
    password: str
    user_agent: str


@dataclass
class SMTPConfig:
    host: str
    port: int
    username: str
    password: str
    sender: str
    recipient: str


@dataclass
class Config:
    subreddits: list[str]
    lookback_hours: int
    listing: str
    max_posts_per_sub: int
    prefilter: PrefilterConfig
    scoring: ScoringConfig
    digest: DigestConfig
    reddit: RedditCredentials
    anthropic_api_key: str
    db_path: str
    smtp: SMTPConfig | None  # None when email config is absent (e.g. dry-run only)


def _require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigError(f"Missing required environment variable: {name}")
    return value


def _load_reddit_credentials() -> RedditCredentials:
    return RedditCredentials(
        client_id=_require_env("REDDIT_CLIENT_ID"),
        client_secret=_require_env("REDDIT_CLIENT_SECRET"),
        username=_require_env("REDDIT_USERNAME"),
        password=_require_env("REDDIT_PASSWORD"),
        user_agent=_require_env("REDDIT_USER_AGENT"),
    )


def _load_smtp_config(require: bool) -> SMTPConfig | None:
    names = ["SMTP_HOST", "SMTP_USERNAME", "SMTP_PASSWORD", "DIGEST_FROM", "DIGEST_TO"]
    present = [n for n in names if os.environ.get(n, "").strip()]
    if not present and not require:
        return None
    # If any email var is set (or email is required), validate the whole block.
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as exc:
        raise ConfigError("SMTP_PORT must be an integer") from exc
    return SMTPConfig(
        host=_require_env("SMTP_HOST"),
        port=port,
        username=_require_env("SMTP_USERNAME"),
        password=_require_env("SMTP_PASSWORD"),
        sender=_require_env("DIGEST_FROM"),
        recipient=_require_env("DIGEST_TO"),
    )


def _load_yaml(config_path: Path) -> dict:
    if not config_path.exists():
        raise ConfigError(
            f"Config file not found: {config_path}. Copy config.example.yaml to config.yaml."
        )
    data = yaml.safe_load(config_path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} must contain a YAML mapping at the top level.")
    return data


def load_config(
    config_path: str | Path = "config.yaml",
    env_path: str | Path | None = None,
    *,
    require_email: bool = True,
) -> Config:
    """Load secrets from the environment (and `.env`) plus tunables from `config.yaml`.

    `require_email=False` lets a dry-run proceed without SMTP settings.
    """
    load_dotenv(dotenv_path=env_path)  # no-op if no .env present

    data = _load_yaml(Path(config_path))

    subreddits = data.get("subreddits") or []
    if not subreddits:
        raise ConfigError("config.yaml must list at least one subreddit under 'subreddits'.")

    listing = str(data.get("listing", "new"))
    if listing not in {"new", "hot", "rising"}:
        raise ConfigError("listing must be one of: new, hot, rising")

    pf = data.get("prefilter") or {}
    sc = data.get("scoring") or {}
    dg = data.get("digest") or {}

    prefilter = PrefilterConfig(
        min_score=int(pf.get("min_score", 0)),
        keywords=[str(k).lower() for k in (pf.get("keywords") or [])],
    )
    scoring = ScoringConfig(
        model=str(sc.get("model", ScoringConfig.model)),
        batch_size=int(sc.get("batch_size", 8)),
        min_relevance=int(sc.get("min_relevance", 7)),
        max_tokens=int(sc.get("max_tokens", 4096)),
    )
    digest = DigestConfig(
        max_items=int(dg.get("max_items", 25)),
        subject_prefix=str(dg.get("subject_prefix", "[Dashie Digest]")),
        send_when_empty=bool(dg.get("send_when_empty", False)),
    )

    return Config(
        subreddits=[str(s) for s in subreddits],
        lookback_hours=int(data.get("lookback_hours", 24)),
        listing=listing,
        max_posts_per_sub=int(data.get("max_posts_per_sub", 75)),
        prefilter=prefilter,
        scoring=scoring,
        digest=digest,
        reddit=_load_reddit_credentials(),
        anthropic_api_key=_require_env("ANTHROPIC_API_KEY"),
        db_path=os.environ.get("SEEN_DB_PATH", "seen.db").strip() or "seen.db",
        smtp=_load_smtp_config(require=require_email),
    )
