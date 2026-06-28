# CI v1 implementation closeout

Date: 2026-06-27
Status: Completed for CI Collector Router v1

## What shipped

Implemented CI Collector Router v1 on live Chowmes.

The live CI runtime now supports:

- Collector strategy fields on `sources`.
- Acquisition quality metadata on `snapshots`.
- Scout `0.1.1` `/scrape` calls with acquisition metadata enabled.
- RSS/feed parsing for OpenAI and Reddit-style feeds.
- Fallback collector ladder using `fallback_collectors`.
- Source health event writes for every collection run.
- Six-source benchmark artifacts.
- Dashboard collector summary showing `direct_http`, `scout_scrape`, and `rss_feed`.
- Path-aware daily and weekly wrappers that use the real `/root/.hermes/...` runtime path.

## Live runtime paths

Live workspace:

`/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence`

Live skill:

`/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research`

Live artifacts:

`/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research`

Dashboard:

`/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/dashboard/index.html`

Benchmark:

`/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/benchmarks/2026-06-27-ci-collector-benchmark/`

## Key implementation details

- Added snapshot columns: `quality_score`, `quality_reasons`, `recommended_collector`, `recommended_collector_reason`, `content_markers_found`, `content_markers_missing`, `acquisition_json`.
- Added source health columns: `collector`, `duration_ms`, `quality_score`, `recommended_collector`.
- Added `fetch_rss_url` using feed-specific XML parsing.
- Updated `fetch_scout_url` to send `quality_analysis`, `cleanup`, `expected_markers`, `recommend_collector`, and `source_id`.
- Added fallback routing so Scout failures can recover through direct HTTP or RSS where configured.
- Added benchmark script: `scripts/collector-benchmark.py`.
- Updated dashboard source section to include collector strategy summary.

## Scout operational fix

CI initially could not call Scout because Hermes/CI did not have `SCOUT_API_KEY`.

Then Scout still returned `403` because the running container was using the old 7-character fallback key while `/opt/prism/scout/.env` contained the intended 48-character key.

Fix:

- Copied the existing Scout key reference into `/root/.hermes/.env` without printing the secret.
- Added `SCOUT_BASE_URL=http://127.0.0.1:8421`.
- Recreated the Scout container with `/opt/prism/scout/.env` loaded into the compose shell.
- Verified protected `/scrape` returned `200` with acquisition metadata.

## Benchmark result

Six-source benchmark selected:

| Source | Selected collector |
|---|---|
| Google AI blog | `scout_scrape` |
| Constructor product | `scout_scrape` |
| Coveo press/blog | `scout_scrape` |
| Bloomreach updates | `direct_http` |
| OpenAI RSS | `rss_feed` |
| Simple static source | `direct_http` |

Important finding:

OpenAI RSS direct HTTP produced a noisy 120,000-character capture. RSS parsing produced a cleaner 12,719-character feed representation and was selected as the correct collector.

## Latest live verification

Local test suite:

- `python3 -m pytest tests/test_ci_core_weekly.py -q`
- Result: `18 passed`

Live database after fallback-enabled daily run:

- `sources`: 53
- `snapshots`: 160+
- `signals`: 65+
- `synthesis_runs`: 13+
- `report_index`: 8+
- `source_health_events`: 39+
- `action_items`: 1

Latest enabled source health:

- `ok`: 39
- failed: 0

Latest enabled collector mix:

- `scout_scrape`: 23
- `direct_http`: 14
- `rss_feed`: 2

Fallback success:

Coveo blog, platform, commerce, and case studies were blocked through Scout but recovered through direct HTTP fallback. The failed Scout attempt and successful direct fallback are stored in snapshot acquisition metadata.

Generated artifacts:

- Daily Markdown: `/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/briefs/2026-06-27.md`
- Daily HTML: `/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/reports/2026-06-27.html`
- Weekly Markdown: `/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/briefs/2026-06-27-weekly.md`
- Weekly HTML: `/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/reports/2026-06-27-weekly.html`
- Dashboard: `/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/dashboard/index.html`

Dashboard verification:

- Latest daily visible.
- Latest weekly visible.
- Collector summary visible.
- `scout_scrape`, `direct_http`, and `rss_feed` visible.
- Actions visible.
- Archive visible.

Health check:

- `scripts/chowmes-health-check --repair --send-test`
- Result: success.
- Runtime files readable by `hermes`.
- Gateway running.
- Parallel web backend ready.
- No recent permission errors.
- Telegram send-test delivered.
- No root-owned runtime drift after checks.

## Remaining product work

CI Collector Router v1 is complete and running. The next product-quality work is not more acquisition plumbing. It is intelligence quality:

- Improve semantic delta extraction so the report says what materially changed, not merely that a page changed.
- Add weekly baseline-only gate so battlecard/action recommendations require real deltas.
- Add evidence claim gates for unsupported material claims.
- Improve dashboard action workflow and usefulness feedback.
- Build the dedicated CI bot only after the dashboard/report quality is stable.

