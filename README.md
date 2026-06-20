# Reddit Interest Digest

A **personal, non-commercial, read-only** tool that reads new posts from a small set of
subreddits once per day, scores each for relevance to topics I personally follow (home
dashboards, smart-home displays, family organizers) using the Anthropic API, and emails me a
digest of the most relevant threads with private notes for my own reference.

**It never writes to Reddit — no posting, commenting, voting, or messaging, ever.** It does not
generate content to post anywhere and produces no promotional or marketing text.

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

The LLM only **scores** relevance and writes **private notes** for the operator to read. It does
not draft replies or any content to be posted, and produces no promotional or marketing text.
Nothing it produces is ever posted anywhere.

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
   with a relevance score, spam-risk flag, a one-line "why", and optional **private notes** for
   my own reference (never a reply to post).
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

## Running it in the cloud (recommended) — GitHub Actions + Supabase

No server or Raspberry Pi required. A scheduled GitHub Actions workflow
(`.github/workflows/digest.yml`) runs the job daily; the de-dup state lives in a
Supabase table so it survives between stateless runs.

**How the de-dup backend is chosen:** if both `SUPABASE_URL` and
`SUPABASE_SERVICE_ROLE_KEY` are set, the durable Supabase store is used;
otherwise it falls back to the local SQLite file. So the same code runs locally
(SQLite) and in the cloud (Supabase) with no changes.

### 1. Create the Supabase table

Run [`supabase_schema.sql`](supabase_schema.sql) once in your Supabase project
(SQL editor, or `psql`). It creates `public.reddit_digest_seen` — a single table
that stores only post IDs.

### 2. Add the GitHub Actions secrets

In the repo: **Settings → Secrets and variables → Actions → New repository secret**.
Add each of these (or use the `gh` CLI below):

| Secret | Value |
|---|---|
| `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD`, `REDDIT_USER_AGENT` | Your Reddit script-app credentials |
| `ANTHROPIC_API_KEY` | Anthropic API key |
| `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `DIGEST_FROM`, `DIGEST_TO` | Email settings (Gmail app password works). `SMTP_PORT` defaults to 587 if unset. |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Project service-role key (Project Settings → API) |

```bash
# Example with the gh CLI (run from the repo root)
gh secret set ANTHROPIC_API_KEY
gh secret set SUPABASE_URL
gh secret set SUPABASE_SERVICE_ROLE_KEY
# ...repeat for each secret above
```

### 3. Test and schedule

- Edit `config.example.yaml` (the cloud config source of truth) for your
  subreddits / keywords / thresholds, and commit.
- Trigger a manual run: **Actions → Daily Reddit Digest → Run workflow**. Check
  the logs and your inbox.
- After that it runs on the `cron:` schedule in the workflow (default 12:00 UTC
  daily — edit to taste).

## Scheduling on a Pi / Linux box (alternative)

If you'd rather self-host, run once daily via cron (uses the local SQLite store):

```cron
# daily at 7am
0 7 * * * cd /home/pi/reddit-interest-digest && /home/pi/reddit-interest-digest/.venv/bin/python -m reddit_digest >> digest.log 2>&1
```

Structured progress logging goes to stdout, which cron captures into `digest.log`.

---

## Responsible use

The digest is for my own reading. The notes are private reference material, not replies to post.
If I ever choose to take part in a discussion, I do it manually, in my own words, as a community
member — the tool never writes to Reddit and never generates promotional content. The `spam_risk`
flag is there to help me avoid chiming in where a comment would come across as self-promotion.

---

## License

MIT — see [LICENSE](LICENSE).
