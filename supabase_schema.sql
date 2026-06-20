-- De-dup state for the Dashie Reddit Digest cloud job.
-- Stores only Reddit post IDs (no content), so the daily run never re-surfaces
-- a post it has already emailed. Run this once in your Supabase project.

create table if not exists public.reddit_digest_seen (
    post_id    text primary key,
    first_seen timestamptz not null default now()
);

-- Enable RLS as a safety default. The digest job authenticates with the
-- service-role key, which bypasses RLS, so no policies are needed. No anon /
-- authenticated client should ever touch this table.
alter table public.reddit_digest_seen enable row level security;
