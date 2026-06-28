# CI collector benchmark

Date: 2026-06-27

| Source | Expected | direct_http | scout_scrape | rss_feed | Recommendation |
|---|---|---:|---:|---:|---|
| Google AI blog | scout_scrape | ok / 266ms / 3234 chars | ok / 2377ms / 3737 chars | skipped | scout_scrape |
| Constructor product | scout_scrape | ok / 115ms / 12035 chars | ok / 2807ms / 5418 chars | skipped | scout_scrape |
| Coveo press/blog | scout_scrape | ok / 151ms / 1922 chars | ok / 2518ms / 5833 chars | skipped | scout_scrape |
| Bloomreach updates | direct_http | ok / 112ms / 13873 chars | ok / 3123ms / 17465 chars | skipped | direct_http |
| OpenAI RSS | rss_feed | ok / 497ms / 120000 chars | ok / 15351ms / 120000 chars | ok / 453ms / 12719 chars | rss_feed |
| Simple static source | direct_http | ok / 16ms / 142 chars | ok / 1291ms / 165 chars | skipped | direct_http |

Raw benchmark samples are intentionally excluded from the repository; rerun the benchmark to regenerate them locally.
