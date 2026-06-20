"""Assemble and render the email digest (plain text + minimal HTML)."""

from __future__ import annotations

import html
from dataclasses import dataclass

from .config import DigestConfig
from .scorer import ScoredPost

_REDDIT_BASE = "https://reddit.com"


@dataclass
class Digest:
    items: list[ScoredPost]
    text_body: str
    html_body: str


def _permalink(scored: ScoredPost) -> str:
    return f"{_REDDIT_BASE}{scored.post.permalink}"


def select_items(scored: dict[str, ScoredPost], cfg: DigestConfig) -> list[ScoredPost]:
    """Filter to relevance >= min (done upstream), sort descending, cap at max_items."""
    items = sorted(scored.values(), key=lambda s: s.relevance, reverse=True)
    return items[: cfg.max_items]


def _render_text(items: list[ScoredPost]) -> str:
    if not items:
        return "No relevant posts today.\n"
    lines: list[str] = [f"{len(items)} relevant post(s) today.\n"]
    for i, s in enumerate(items, 1):
        lines.append(f"{i}. [r/{s.post.subreddit}] {s.post.title}")
        lines.append(f"   relevance: {s.relevance}/10   spam_risk: {s.spam_risk}")
        if s.angle:
            lines.append(f"   why: {s.angle}")
        lines.append(f"   link: {_permalink(s)}")
        if s.talking_points:
            lines.append("   notes (private — for your own reference):")
            for cline in s.talking_points.splitlines():
                lines.append(f"   | {cline}")
        lines.append("")
    return "\n".join(lines)


def _render_html(items: list[ScoredPost]) -> str:
    if not items:
        return "<p>No relevant posts today.</p>"
    parts: list[str] = [f"<p>{len(items)} relevant post(s) today.</p>"]
    for i, s in enumerate(items, 1):
        title = html.escape(s.post.title)
        sub = html.escape(s.post.subreddit)
        angle = html.escape(s.angle)
        notes = html.escape(s.talking_points)
        link = html.escape(_permalink(s))
        parts.append(
            "<div style='margin:0 0 18px 0;padding:0 0 12px 0;"
            "border-bottom:1px solid #ddd;'>"
            f"<p style='margin:0 0 4px 0;'><b>{i}. [r/{sub}]</b> "
            f"<a href='{link}'>{title}</a></p>"
            f"<p style='margin:0 0 4px 0;color:#555;'>relevance: "
            f"<b>{s.relevance}/10</b> &nbsp; spam_risk: <b>{html.escape(s.spam_risk)}</b></p>"
            + (f"<p style='margin:0 0 6px 0;'><i>{angle}</i></p>" if angle else "")
            + (
                "<p style='margin:0 0 4px 0;color:#888;font-size:12px;'>"
                "Notes (private — for your own reference)</p>"
                f"<pre style='margin:0;padding:8px;background:#f6f6f6;border-radius:4px;"
                f"white-space:pre-wrap;font-family:inherit;'>{notes}</pre>"
                if notes
                else ""
            )
            + "</div>"
        )
    return "<div style='font-family:Arial,Helvetica,sans-serif;'>" + "".join(parts) + "</div>"


def build_digest(scored: dict[str, ScoredPost], cfg: DigestConfig) -> Digest:
    items = select_items(scored, cfg)
    return Digest(items=items, text_body=_render_text(items), html_body=_render_html(items))
