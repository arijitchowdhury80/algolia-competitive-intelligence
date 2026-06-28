# ADR: Use Scout As A First-Class CI Collector

**Date:** 2026-06-27
**Status:** Accepted

## Context

The CI build plan correctly moved to a data-first architecture, but the acquisition layer was still too vague. It treated direct HTTP fetching as the default and Scout as a possible fallback even though Scout is a Chowmes-owned acquisition engine built for browser-grade scraping, markdown extraction, screenshots, crawling, and product intelligence.

Arijit challenged this assumption: if Scout is ours and this is the right workload for it, the CI system should test Scout seriously, expose its failures, and improve it rather than defaulting to external or simpler collectors.

## Smoke Test Evidence

On the Chowmes VPS, Scout is live and healthy at `127.0.0.1:8421`.

- Health: `ok`
- Scout version: `0.1.0`
- Crawl4AI version: `0.7.7`
- Relevant endpoints: `/scrape`, `/crawl`, `/extract`, `/map`, `/screenshot`
- Protected endpoints require `X-API-Key`.

Same-URL smoke comparison:

| Source | Direct HTTP | Scout scrape | Finding |
|---|---:|---:|---|
| Coveo press | 1,951 chars, 132 ms | 6,268 chars, 10.1 sec | Direct is faster; Scout captures richer article links. |
| Bloomreach updates | 14,115 chars, 89 ms | 17,560 chars, 8.5 sec | Both work; Scout cleaner but slower. |
| Constructor product | 12,156 chars, 169 ms | 5,491 chars, 3.8 sec | Scout produces cleaner markdown but includes consent text. |
| Google AI blog | 3,352 chars, 9.6 sec | 3,740 chars, 1.9 sec | Scout is faster and cleaner. |
| OpenAI RSS | 140,440 chars, 378 ms | 643,968 chars, 16 sec | Neither generic path is ideal; this needs feed parsing. |

## Decision

Scout is promoted from "fallback only" to **first-class collector** for Competitive Intelligence.

The CI acquisition layer should become a collector router:

```text
sources.yaml
  -> collector strategy
  -> direct_http | scout_scrape | rss_feed | parallel_search | parallel_monitor | manual_only
  -> normalized snapshot
  -> semantic delta
  -> claim gate
  -> Algolia action
```

## Rationale

Direct HTTP is cheap and fast, but it returns noisy text for many modern pages and cannot handle JavaScript-rendered or browser-sensitive surfaces.

Scout is slower on simple pages, but it returns cleaner markdown for several product/blog surfaces and can eventually support screenshots, JS rendering, crawling, mapping, and browser-assisted capture.

The correct architecture is not "Scout versus direct HTTP." It is a per-source collector strategy with measured performance and extraction quality.

## Collector Strategy Defaults

| Source type | Primary collector | Secondary collector |
|---|---|---|
| RSS/feed | `rss_feed` | `direct_http` |
| Docs/changelog/static page | `direct_http` | `scout_scrape` |
| Product/positioning page | `scout_scrape` | `direct_http` |
| Blog/news index | `scout_scrape` or `rss_feed` | `direct_http` |
| Dynamic/JS page | `scout_scrape` | direct only for failure record |
| Search/discovery | `parallel_search` | Scout/direct for canonical capture |
| Gated/paid page | `manual_only` | no fake coverage |

## Consequences

- CI source configuration must include collector strategy metadata.
- The daily runner must support Scout scraping with secure `SCOUT_API_KEY` use.
- Source health must record collector method, duration, and error.
- Scout weaknesses become product-improvement inputs, not reasons to bypass Scout.
- Scout needs a dedicated enhancement plan based on CI acquisition needs.

## Open Follow-Ups

- Add a durable Scout-vs-direct benchmark harness.
- Add cookie/consent cleanup to Scout output.
- Add RSS/feed-specific parsing rather than using generic scraping for feeds.
- Add source-level strategy and fallback configuration to `sources.yaml`.
- Decide after a broader benchmark which sources should use Scout as primary.
