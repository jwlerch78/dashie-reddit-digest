"""Send the digest over SMTP with STARTTLS."""

from __future__ import annotations

import logging
import smtplib
from datetime import date
from email.message import EmailMessage

from .config import DigestConfig, SMTPConfig
from .digest import Digest

log = logging.getLogger(__name__)


def _subject(cfg: DigestConfig, n: int) -> str:
    return f"{cfg.subject_prefix} {date.today().isoformat()} — {n} posts"


def send_digest(digest: Digest, smtp: SMTPConfig, digest_cfg: DigestConfig) -> None:
    """Send the rendered digest as a multipart text+HTML email."""
    msg = EmailMessage()
    msg["Subject"] = _subject(digest_cfg, len(digest.items))
    msg["From"] = smtp.sender
    msg["To"] = smtp.recipient
    msg.set_content(digest.text_body)
    msg.add_alternative(digest.html_body, subtype="html")

    log.info("Sending digest to %s via %s:%d", smtp.recipient, smtp.host, smtp.port)
    with smtplib.SMTP(smtp.host, smtp.port) as server:
        server.starttls()
        server.login(smtp.username, smtp.password)
        server.send_message(msg)
    log.info("Digest sent.")
