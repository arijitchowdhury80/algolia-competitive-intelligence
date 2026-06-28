# CI v1 EOD goal and live delta

Date: 2026-06-27
Status: Active

## Goal

By end of day on 2026-06-27, Competitive Intelligence v1 should be complete enough to run on live Chowmes, produce tested daily and weekly output, and expose a working dashboard that Arijit can inspect.

This is not a generic CI platform build. The accepted direction remains the narrow Algolia-specific decision layer: source-backed deltas, Algolia-specific implications, owner-specific actions, evidence quality, and source health transparency.

## Shortest path

Implement CI Collector Router v1 on the live runtime, regenerate the dashboard, and inspect the first real output.

## Required deliverables

- Upgrade live CI schema with collector fields on `sources` and acquisition metadata on `snapshots`.
- Wire Scout `0.1.1` into CI through the shared `/scrape` endpoint with acquisition metadata enabled.
- Add RSS/feed parsing so OpenAI RSS and Reddit RSS are not treated as ordinary web pages.
- Run a six-source benchmark:
  - Google AI blog
  - Constructor product page
  - Coveo press/blog
  - Bloomreach updates
  - OpenAI RSS
  - one simple static source
- Assign collector defaults for every source: `direct_http`, `scout_scrape`, `rss_feed`, `parallel_search`, or `manual_only`.
- Populate source health events on every run with source, collector, status, duration, error, and quality score.
- Regenerate the dashboard with latest daily report, latest weekly report, source health, failed sources, collector strategy, action queue, and archive.

## Live delta verified before this work

Live CI artifacts are under:

`/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence`

The old `/opt/data/knowledge/...` paths are stale for current runtime inspection.

Current live ledger state:

- `sources`: 53
- `snapshots`: 121
- `signals`: 41
- `synthesis_runs`: 11
- `report_index`: 6
- `source_health_events`: 0
- `action_items`: 1

Current live schema gap:

- `sources` does not yet include collector strategy fields.
- `snapshots` does not yet include collector, duration, quality score, or Scout acquisition metadata.
- `source_health_events` exists but has no rows.

## Acceptance evidence

This work is not complete until the live runtime proves:

- CI tests pass for weekly rendering, collector routing, Scout metadata handling, RSS parsing, source health writes, and dashboard rendering.
- Live database schema includes collector and quality metadata.
- At least one live collection run writes source health events.
- The six-source benchmark writes a durable artifact.
- The dashboard HTML exists and includes current daily/weekly, source health, failed sources, collector strategy, action queue, and archive views.
- A generated daily or weekly output can be inspected and tied back to source-backed ledger records.

