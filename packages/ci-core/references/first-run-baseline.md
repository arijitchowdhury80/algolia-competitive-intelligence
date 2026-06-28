# First Dry-Run Baseline (2026-06-16)

## Environment
- Host: Chowmes (Hostinger VPS, Docker container)
- Python: `/opt/hermes/.venv/bin/python` (3.13.5, pyyaml 6.0.3)
- Parallel CLI: 0.7.1, `/usr/local/bin/parallel-cli`, authed via `PARALLEL_API_KEY`
- Hermes CLI: `/opt/hermes/.venv/bin/hermes`
- Model: DeepSeek V4 Pro (workhorse), Claude Sonnet 4.6 (synthesis)

## Search Queries Run (15 total)
### Competitor Moves (6 queries, 30 results)
- Coveo AI search announcement release 2026
- Bloomreach discovery commerce latest news
- Constructor ecommerce AI search product update
- Google Vertex AI Search retail ecommerce new feature
- Elasticsearch enterprise search announcement
- Meilisearch Typesense open source search release

### Industry Signals (5 queries, 25 results)
- search and product discovery trends ecommerce 2026
- conversational commerce AI shopping agent
- retail ecommerce site search best practices
- Gartner Forrester IDC search discovery analyst
- MCP A2A UCP agent protocol commerce search

### AI Threats (4 queries, 20 results)
- Perplexity shopping commerce search
- ChatGPT search browse ecommerce product discovery
- Google Universal Cart agentic commerce
- AI agents replacing site search ecommerce 2026

## Results
- Monitor alerts: 0 (monitors not yet created)
- Total findings: 75
- Dry-run: completed in ~3 minutes
- Synthesis: blocked by `[ERROR] Hermes CLI not found` (script used bare `hermes` instead of `/opt/hermes/.venv/bin/hermes`) — fixed in `daily-research-run.py` with `HERMES_BIN` constant

## Raw findings saved to
`/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/raw/2026-06-16.json`
