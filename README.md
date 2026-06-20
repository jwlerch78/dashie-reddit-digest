# Dashie Reddit Digest

A **personal, non-commercial, read-only** tool that reads new posts from a small set of
subreddits once per day, scores each for relevance to a family-dashboard / smart-home-display
product using the Anthropic API, and emails the operator a digest of the most relevant threads
with suggested (human-reviewed) talking points.

**It never writes to Reddit — no posting, commenting, voting, or messaging, ever.**

---

## Compliance posture

This tool is built for a single operator and is designed to sit comfortably inside Reddit's
Data API terms for personal, non-commercial use:

- **Read-only Data API usage** via OAuth2 (PRAW). The Reddit client is configured read-only and
  the code contains no write-capable calls.
- **No posting / commenting / voting / messaging** of any kind.
- **Single operator**, run once per day — well under the 100 queries-per-minute free-tier limit.
- **Minimal storage:** only post IDs are stored, solely for de-duplication. No post content is
  retained, and deletions on Reddit are honored (a deleted post simply never reappears).
- **Unique, descriptive User-Agent** per Reddit's Data API terms (see `.env.example`).

The LLM only **scores** relevance and **drafts** suggestions for the operator to review. Nothing
the model produces is ever posted anywhere automatically.

---

## How it works

```
fetch (last ~24h) → keyword prefilter → de-dup → LLM relevance score → render digest → email
```

1. Pull new posts from each configured subreddit (read-only).
2. Cheap keyword/score prefilter drops obviously irrelevant posts before spending any LLM tokens.
3. SQLite de-dup ensures a post is never surfaced twice.
4. Surviving posts are scored 0–10 by the Anthropic API, which returns structured JSON.
5. Posts at or above the relevance threshold are rendered into a plain-text + HTML digest, each
   with a relevance score, spam-risk flag, a one-line "why", and a **DRAFT** reply to review.
6. The digest is emailed to the operator over SMTP.

---

## Setup

Requires Python 3.11+.

1. **Create a Reddit "script" app** at <https://www.reddit.com/prefs/apps>:
   - Choose **script**, set the redirect URI to `http://localhost:8080` (unused, but required).
   - Note the client ID (under the app name) and the client secret.

2. **Install dependencies:**
   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure secrets** — copy `.env.example` to `.env` and fill it in:
   ```bash
   cp .env.example .env
   ```
   Set the Reddit credentials, your `ANTHROPIC_API_KEY`, and SMTP settings. For Gmail, use an
   [app password](https://support.google.com/accounts/answer/185833), not your account password.

4. **Configure subreddits and tunables** — copy the example config:
   ```bash
   cp config.example.yaml config.yaml
   ```
   Edit the subreddit list, keywords, and thresholds to taste.

5. **Dry run** (does everything except send the email and record seen posts):
   ```bash
   python -m reddit_digest --dry-run
   ```

6. **Real run:**
   ```bash
   python -m reddit_digest
   ```

---

## Scheduling (cron)

Run once daily at 7am on a Raspberry Pi (or any Linux box):

```cron
# daily at 7am
0 7 * * * cd /home/pi/dashie-reddit-digest && /home/pi/dashie-reddit-digest/.venv/bin/python -m reddit_digest >> digest.log 2>&1
```

Structured progress logging goes to stdout, which cron captures into `digest.log`.

---

## Responsible use

Every suggested reply in the digest is a **draft for the operator to read**. The operator decides
whether to engage at all, and if so posts manually, in their own words. The tool never writes to
Reddit. Suggested comments that read as self-promotion are flagged with an elevated `spam_risk`
so they can be skipped.

---

## License

MIT — see [LICENSE](LICENSE).
