# Algolia Competitive Intelligence

Standalone Competitive Intelligence software for the Algolia public-source CI pack.

This repository is the product boundary for CI. Hermes/Chowmes executes it, Scout acquires web content, and the dashboard exposes the decision surface.

## Architecture

```text
Scout
  browser-grade acquisition and page quality metadata

Algolia Competitive Intelligence
  collector router, ledger, daily/weekly synthesis, action model, dashboard

Hermes / Chowmes
  scheduler, operator, delivery runner

Vercel
  dashboard app surface

Vault
  durable strategy, decisions, research, and operating memory
```

## Repository Layout

```text
apps/dashboard/          Static Vercel dashboard seed
packages/ci-core/        CI engine, source registry, tests, report renderers
workers/                 Thin runner entrypoints for Chowmes/Hermes
data/                    Benchmarks and future source data exports
docs/                    Decisions, runbooks, implementation logs
```

## Current Status

Bootstrap import from the Competitive Intelligence vault workspace.

CI Collector Router v1 is live on Chowmes and includes:

- `direct_http`, `scout_scrape`, and `rss_feed` collectors.
- Scout `0.1.1` acquisition metadata.
- RSS/feed parser for OpenAI and Reddit-style feeds.
- Fallback collector ladder.
- Source health events.
- Daily and weekly report generation.
- Static dashboard artifact.

## Local Verification

```bash
python3 -m pytest packages/ci-core/tests -q
```

## Run Locally

Use a temporary output root so local tests and experiments do not touch live artifacts:

```bash
export COMPETITIVE_RESEARCH_OUTPUT_ROOT="$PWD/.local/competitive-research"
python3 packages/ci-core/scripts/daily-research-run.py --skip-search --skip-monitors --local-synthesis
python3 packages/ci-core/scripts/weekly-review.py --local-synthesis
python3 packages/ci-core/scripts/generate-dashboard.py
```

## Runtime Boundary

Vercel should serve the dashboard. It should not run long collection jobs or browser acquisition.

Chowmes/Hermes should run the workers and call Scout.

Scout should remain the shared acquisition service. Do not add CI-specific Scout endpoints.

