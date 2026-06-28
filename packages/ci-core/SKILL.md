---
name: competitive-research
description: Daily competitive intelligence brief for Algolia's search/discovery landscape. Use when Arijit asks for the morning competitive update, or when building/editing the competitive research cron job. Covers Coveo, Bloomreach, Constructor, Google Vertex AI, Elastic, Meilisearch, Typesense, Perplexity, ChatGPT, and AI agent threats. Sources are MANDATORY for every claim.
version: 1.0.0
author: Athena (Chowmes)
license: MIT
metadata:
  hermes:
    tags: [competitive-intelligence, research, cron, search-discovery, algolia, osint]
    related_skills: [hermes-agent, hermes-agent-skill-authoring, parallel-cli]
---

# Competitive Research — Search & Discovery Landscape

Daily competitive intelligence engine for Arijit at Algolia. Covers competitor moves, industry signals, AI-native threats, and content angles for LinkedIn thought leadership. The v2 pipeline stores public-source evidence in a SQLite signal ledger before synthesis.

Important: Arijit cares about OEM/resale partnerships, but the skill must not force every recommendation into a partner-only strategy. Choose the action owner from the evidence: Product, Product Marketing, Sales Enablement, Partner Enablement, Competitive Intelligence, or a cross-functional group.

Canonical runtime contract:

- Workspace skill root: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research`
- Workspace artifacts: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research`
- Hermes compatibility link: `/opt/data/skills/competitive-research` points to the workspace skill root.
- Cron wrappers live in `/opt/data/scripts/` and call the workspace skill root directly.
- Do not keep a second executable copy under Chowmes; update the workspace skill and redeploy wrappers.

## Algolia Brand System Mandate

All Algolia-related outputs from this skill must use the official Algolia design language from:

```text
/Users/arijitchowdhury/Library/CloudStorage/GoogleDrive-arijit.chowdhury@gmail.com/My Drive/AI-Projects/Algolia-Design-System
```

Apply this to the daily Telegram pulse, Slack-ready summary, markdown brief, HTML report, and any future PDF/deck/export derived from the brief.

Brand rules:

- Voice: confident, technical, outcome-oriented, evidence-backed, sentence case.
- No emoji, no exclamation marks, no em dashes, no jokey headers, no generic AI phrasing.
- Use Algolia vocabulary precisely: AI Search, AI Search and Retrieval, Agent Studio, Ask AI, NeuralSearch, MCP Server, Intelligent Data Kit.
- Numbers should be clear and prominent: `+112%`, `4x`, `100x`, `18,000 customers`, `1.75T searches/year`.
- For visual artifacts, use Algolia Blue `#003DFF`, Sora, JetBrains Mono for code, mostly white surfaces, dark navy CTA/report bands where useful, 12-16px cards, 8px buttons, 999px badges only.
- Use official Algolia logos/assets when available. Never redraw the Algolia mark.
- Full HTML reports must use the Algolia report styling in `daily-research-run.py`; do not revert to placeholder Inter styling or fake logo marks.

## Workflow

### Daily Research Run
```bash
/opt/hermes/.venv/bin/python scripts/daily-research-run.py
/opt/hermes/.venv/bin/python scripts/daily-research-run.py --dry-run    # Collect/store only, no synthesis
/opt/hermes/.venv/bin/python scripts/daily-research-run.py --resume     # Skip collection, synthesize from SQLite ledger
/opt/hermes/.venv/bin/python scripts/daily-research-run.py --date 2026-06-17
/opt/hermes/.venv/bin/python scripts/daily-research-run.py --fixture "$COMPETITIVE_RESEARCH_OUTPUT_ROOT/raw/2026-06-17.json" --local-synthesis
/opt/hermes/.venv/bin/python scripts/daily-research-run.py --direct-limit 5 --skip-search --local-synthesis
```

### Telegram Execution Guard

Telegram is a request and delivery surface, not the workspace for installing, repairing, or rewriting this pipeline.

When this skill is triggered from Telegram:

1. Run the pipeline at most once with `/opt/hermes/.venv/bin/python /opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/scripts/daily-research-run.py`.
2. Return only the compact Telegram pulse and artifact paths.
3. Do not paste the full report, raw JSON, prompt text, source ledger, stack traces, or dependency output into Telegram.
4. Do not run package installs, device auth, symlink repair, broad file searches, or skill rewrites from the Telegram thread.
5. If prerequisites fail, stop after the first failure and tell Arijit that Codex/local operator repair is required.
6. If the Telegram thread is already large, looping, or receiving "maximum iterations" / "interrupted during API call" symptoms, stop work and request a fresh Telegram session before continuing.

Context exhaustion is a production failure mode. The correct response is not to keep trying inside the same chat. Save artifacts, stop, patch the skill or script from Codex, then restart the Telegram session if needed.

### Monitor Setup (one-time)
```bash
python3 scripts/setup-monitors.py
python3 scripts/setup-monitors.py --dry-run   # Preview only
python3 scripts/setup-monitors.py --list      # List existing monitors
```

### Weekly Review
```bash
python3 scripts/weekly-review.py
python3 scripts/weekly-review.py --date 2026-06-22
```

## Architecture

```
cron (9 AM ET daily)
  └─→ /opt/data/scripts/competitive-research-daily.sh
        └─→ /opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/scripts/daily-research-run.py
        ├─→ load sources.yaml into SQLite sources
        ├─→ direct public URL snapshots/diffs
        ├─→ parallel-cli monitor events    (if authenticated)
        ├─→ parallel-cli search            (if authenticated)
        ├─→ normalize scored signals → ci.sqlite
        ├─→ build synthesis packet from signal ledger
        ├─→ /opt/hermes/.venv/bin/hermes chat -q (Claude Sonnet) (synthesis)
        ├─→ save markdown brief → /opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/briefs/
        ├─→ save Algolia-branded HTML report → /opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/reports/
        └─→ stdout → Telegram pulse only, not full report
```

## Dependencies

- `parallel-cli`: authenticated, on PATH (`/usr/local/bin/parallel-cli`)
- `hermes`: on PATH for synthesis step (`/opt/hermes/.venv/bin/hermes` — full path required inside Docker)
- `curl`: for source health checks
- Python 3.10+: pyyaml
- SQLite (Python stdlib)
- OpenRouter API key (for Claude Sonnet synthesis)

## Prerequisites

1. `parallel-cli login` (device auth or API key)
2. `python3 scripts/setup-monitors.py` (one-time, creates 12+ monitors)
3. Hermes CLI available for synthesis step

## Cron Setup

Hermes cron resolves `--script competitive-research-daily.sh` from `/opt/data/scripts/`, not from the skill folder and not from `/opt/data/.hermes/scripts/`. The deployment contract is:

- Canonical skill code: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/`
- Canonical cron wrapper: `/opt/data/scripts/competitive-research-daily.sh`
- Canonical runtime outputs: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/`
- Local Vault archive: `/Volumes/Data/Dropbox/AI-Development/Personal/Obsidian-Vault/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/`
- Archive sync policy: mirror only final `reports/` and `briefs/` into the Vault. Keep `raw/`, `ci.sqlite`, and one-off debug files on the VPS unless actively debugging.

Do not install this cron wrapper under `/opt/data/.hermes/scripts/`; that path is not the Hermes cron lookup path for this job.

The full daily run can exceed Hermes' default 120-second no-agent script timeout because it performs source collection and Claude synthesis before stdout is delivered. Keep `/opt/data/config.yaml` aligned with:

```yaml
cron:
  script_timeout_seconds: 900
```

```bash
mkdir -p /opt/data/scripts
cp "/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/scripts/competitive-research-daily.sh" \
  /opt/data/scripts/competitive-research-daily.sh
chmod 755 /opt/data/scripts/competitive-research-daily.sh

hermes cron create "0 9 * * *" \
  --name "competitive-research-daily" \
  --deliver "telegram" \
  --script "competitive-research-daily.sh" \
  --no-agent
```

## Weekly Review Cron

```bash
cp "/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/scripts/competitive-research-weekly.sh" \
  /opt/data/scripts/competitive-research-weekly.sh
chmod 755 /opt/data/scripts/competitive-research-weekly.sh

hermes cron create "0 9 * * 0" \
  --name "competitive-research-weekly-review" \
  --deliver "telegram" \
  --script "competitive-research-weekly.sh" \
  --no-agent
```

## Competitor Map

### Tier 1 — Direct (Gartner MQ Leaders, same buyer)
- Coveo (enterprise AI relevance, public CVO, Salesforce/Adobe, RAG-as-a-Service)
- Bloomreach (Loomi AI, Clarity conversational agent, Shopify POS360, Loomi Connect)
- Constructor (pure ecommerce, AI Shopping Agents, clickstream-trained, 322B interactions)
- Google Vertex AI Search (managed, Google ecosystem, Universal Cart)

### Tier 2 — Traditional (same Gartner MQ)
- Elastic / Elastic Cloud / Swiftype (open-source foundation, massive installed base)
- Lucidworks (Fusion platform, commerce-oriented)
- Yext (AI answers platform, public company)
- Algonomy (retail CDP + personalization + search converged)

### Tier 3 — Developer / OSS (eating from below)
- Meilisearch (MIT license, Rust, 58K GitHub stars, developer-first)
- Typesense (memory-first speed, 26K stars, bootstrapped)
- AWS OpenSearch / CloudSearch (AWS-native Elastic fork)

### Tier 4 — AI-Native Existential Threats
- Perplexity Commerce (conversational shopping, PayPal checkout, bypasses site search)
- ChatGPT Search / Browse (conversational discovery, shopping integrations)
- Google Universal Cart (cross-merchant, Search + Gemini + YouTube + Gmail)
- AI Agents (Claude MCP, GPT agents querying catalogs directly, UX layer evaporates)

### Tier 5 — Adjacent / Watchlist
- Glean (workplace enterprise search)
- GoSearch (enterprise AI search + knowledge)
- Microsoft Search / Copilot (ecosystem lock-in)

### Removed
- search.io — acquired by Algolia, no longer a competitor

## Hard Rules

### Source Mandate (NON-NEGOTIABLE)
Every claim, finding, synthesis point, stat, quote, or observation MUST include a hyperlink to the primary source. No exceptions.
- If Parallel or web search returns a finding without a URL → flag as UNVERIFIED, hold back
- If the source is behind a login wall → note the wall, provide what's publicly accessible
- Bibliography must be preserved through every pipeline step (collection → processing → synthesis)
- No hallucinated data. If I cannot validate it, it does not ship.

### Algolia Baseline Mandate (NON-NEGOTIABLE)
Validate Algolia's public baseline before claiming an Algolia gap.


Rules:

- Do not say or imply Algolia lacks a certain feature, for example MCP.
- If a competitor has that feature, for example MCP, then compare packaging, positioning, adoption, partner narrative, GTM motion, or documentation clarity against Algolia's MCP baseline.
- If public evidence is insufficient, label the claim `Unknown - needs internal validation`.
- Separate `Confirmed fact`, `Public-evidence inference`, and `Unknown` in the brief.

### Delivery Cadence
- **Daily pulse**: material public-source deltas only, delivered 9 AM ET
- **Real-time alerts**: push on competitor moves, breaking news, major signals (via Parallel monitors)
- **Weekly synthesis**: pattern-first synthesis from the SQLite signal ledger
- **Monthly review**: pricing, positioning, customer voice, SEO/AI visibility, and battlecard refresh (planned)

### Delivery Channels
- **Telegram**: Primary. Compact 300-500 word format, mobile-friendly Markdown without tables. Always includes source links. User can reply "deep dive" or "expand" for full brief.
- **Slack**: Copy-paste from Telegram. Format preserved for Markdown bullets and links.
- All messages must be copy-pasteable into Slack with tables/lists intact.

### HN and Reddit
Passive monitors only. Check daily but report ONLY when relevant content surfaces. Do not include boilerplate "nothing on HN/Reddit today" in briefs.

## Output Structure

Daily pulse format (redesigned June 2026, v2 ledger-backed). DO NOT use the old multi-table decision-deck format.

1. **Bottom line** - one short paragraph with confidence.
2. **Recommended action** - the single daily action with owner and timeline.
3. **Evidence** - 2-4 dated, inline-linked bullets with competitive implication.
4. **Watch trigger** - only triggers that change the recommendation, urgency, or owner.
5. **Research coverage** - methods used, v1 exclusions, sources checked, known gaps.

Weekly synthesis format:

1. **What changed**
2. **Strategic pattern**
3. **Recommended actions by owner**
4. **Battlecard updates**
5. **Coverage gaps**

Do not output Executive Decision Table, Position Dashboard, Research Scope, Validated Algolia Baseline, AI Threat Radar, Implications for Arijit, Competitive Delta Matrix, duplicate Action Plan sections, Watch List tables, or Sources & Coverage sections.

See `references/output-template.md` for the full format.

## Self-Learning Loop
Failure modes to detect and patch:
- **Report/template/content sync spiral** (NEW June 2026): A June 20 report fix mixed stale content regeneration, HTML renderer edits, Telegram delivery, and Vault archive sync. The trusted report was the user-provided AWS OpenSearch Serverless plus Meilisearch v1.47 HTML, but reruns produced wrong stale narratives. Fixed by establishing the trusted dated artifact first, restoring it to live artifacts, patching the reusable `ci_core.py` renderer, syncing the live Obsidian/VPS skill paths, and sending mobile-test attachments with distinct filenames.
- **Mobile HTML false confidence** (NEW June 2026): Desktop/browser review missed Telegram iPhone document-viewer problems: cramped hero, tiny stat cards, duplicated bottom-line text, small body type, and long evidence URLs. Fixed by shortening the hero summary, removing duplicate body title, increasing mobile body typography, simplifying stat cards, and forcing evidence URL wrapping. Telegram's phone document viewer is now the acceptance surface for report formatting.
- **Vault archive clutter** (NEW June 2026): Raw/debug runtime files leaked into the local Vault archive (`raw/`, `ci.sqlite`, one-off OCR/debug files). Fixed by adding `scripts/sync-competitive-research-archive-from-hermes`, which mirrors only final `reports/` and `briefs/` into the Vault and leaves raw/audit data on the VPS unless debugging.
- **Telegram context exhaustion** (NEW June 2026): A Telegram run tried to install/repair Parallel, execute the pipeline, revise the skill, and redesign the report inside one growing DM session. The session reached 143K+ prompt tokens and repeatedly exhausted the 12-turn budget. Fixed by adding the Telegram Execution Guard: artifact-first delivery, one pipeline attempt, no interactive dependency repair, no full report dumps, and fresh-session recovery when the active DM is oversized.
- **Data dump regression** (NEW June 2026): Briefs that list findings without synthesis, implications, or recommendations. Fixed by redesigning prompt and output-template.md to mandate "why it matters" for every finding.
- **Same-company atomization** (NEW June 2026): Multiple findings from one competitor listed separately instead of synthesized into a narrative. Fixed by adding "synthesize, do not list" to prompt rules.
- **Missing gap analysis** (NEW June 2026): Quiet competitors not mentioned, creating false impression of comprehensive coverage. Fixed by adding explicit "Quiet" sections and gap acknowledgment.
- **Unvalidated Algolia-gap claim** (NEW June 2026): The report once implied Algolia lacked MCP even though Algolia has official MCP docs. Fixed by adding a validated Algolia baseline and replacing "gap" claims with baseline-backed competitive delta analysis.
- **Blind spot emergence**: new competitor appears that wasn't in config
- **Stale repetition**: same story, different day
- **Source rot**: blog stops publishing, changelog URL changes
- **Relevance drift**: starts pulling general AI news instead of search-specific signal
- **Missing sources**: claim shipped without URL → hard fail, patch pipeline

## Files

- `references/sources.yaml` — Complete source URLs, search queries, executive tracker
- `references/signal-taxonomy.md` — Signal categories, scoring, and action-owner routing
- `references/methodology.md` — Public-source CI operating model
- `references/output-template.md` — Brief format with 7 labeled sections
- `references/first-run-baseline.md` — Results from the first dry-run (2026-06-16); use as a smoke-test reference
- `scripts/ci_core.py` — SQLite ledger, source loading, fetch/diff, normalization, scoring, rendering
- `scripts/daily-research-run.py` — Main daily pipeline
- `scripts/competitive-research-daily.sh` — Cron delivery wrapper; deploy this file to `/opt/data/scripts/competitive-research-daily.sh`
- `scripts/setup-monitors.py` — Parallel CLI monitor creation
- `scripts/weekly-review.py` — Weekly self-audit and source health check
- Runtime output: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/briefs/YYYY-MM-DD.md`
- Runtime output: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/reports/YYYY-MM-DD.html`
- Runtime raw/audit output: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/raw/YYYY-MM-DD-v2-collection.json`
- Runtime ledger: `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/ci.sqlite`
- Local Vault archive: `/Volumes/Data/Dropbox/AI-Development/Personal/Obsidian-Vault/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/`
- Stdout: 2-3 minute Telegram pulse with artifact paths, not the full report.

## Common Pitfalls

1. **Novel, not briefing.** The daily pulse must stay compact, use no tables, and avoid duplicate action/watch/implication sections.
2. **Action ambiguity.** The single daily action belongs in Recommended action. Evidence explains why; it should not imply separate hidden tasks.
3. **Support sections treated as main content.** What would change this recommendation and Research coverage are secondary decision support, not equal-weight findings sections.
4. **Partner-only overfit.** Do not turn mixed product, protocol, marketplace, data-platform, or GTM evidence into a partner-only strategy. Use distribution readiness or cross-functional GTM/product readiness when the signal is broader than partner motion.
5. **Undated evidence.** Do not use `date not found` in Bottom line or Evidence behind the recommendation. Omit undated items or move the missing-date note to Research coverage.
6. **Multiple findings from same company listed separately without synthesis.** Group related events under one company bullet when they support the same conclusion.
7. **Parallel CLI not authenticated.** Run `parallel-cli login --device` on the VPS before first use.
8. **Python dependency drift.** If `import yaml` fails, reinstall `python3-yaml` or run the script with `/opt/hermes/.venv/bin/python`.
9. **Hermes CLI running as wrong user.** Daily script calls `hermes chat -q`. The script already hardcodes `/opt/hermes/.venv/bin/hermes`. Ensure it runs as `hermes` user, not root, to avoid permission issues on `/opt/data`.
10. **Monitors not created.** Run `scripts/setup-monitors.py` once before expecting real-time alerts.
11. **Synthesis timeout.** Claude Sonnet may take more than 2 minutes for full briefs. Hermes cron must allow the wrapper enough time to finish; set `/opt/data/config.yaml` `cron.script_timeout_seconds` to `900`.
12. **Quiet day spam.** If 5+ quiet days in a week, weekly review will flag for query expansion.
13. **Telegram tool-repair spiral.** If the skill fails from Telegram because a dependency, auth, path, or permission is wrong, do not keep probing from the DM. Stop, report the first failing prerequisite, and let Codex patch the skill or runtime from the ChowMes workspace.
14. **Wrong cron script directory.** Hermes cron `--script` resolves relative script names under `/opt/data/scripts/`. Do not place the executable only under `/opt/data/.hermes/scripts/` or inside the skill directory.
15. **Stale report resurrection.** When asked to show or send today's report, identify the trusted dated artifact first. Do not run collection/synthesis just to display an existing report.
16. **Mobile report validation.** Desktop rendering is not enough. Send a distinct Telegram attachment filename and inspect the report in the phone document viewer before calling HTML formatting fixed.
17. **Archive bloat.** Use `scripts/sync-competitive-research-archive-from-hermes` for Vault sync. Do not mirror `raw/`, `ci.sqlite`, or debug extraction files into the Vault archive unless actively debugging.

## Verification Checklist

- [ ] `/opt/hermes/.venv/bin/python -c "import yaml"` works (pyyaml available in Hermes venv)
- [ ] `parallel-cli auth` returns OK (API key active)
- [ ] `/opt/hermes/.venv/bin/hermes chat -q "test" -m deepseek/deepseek-v4-flash --quiet` works (synthesis path)
- [ ] `python3 scripts/setup-monitors.py --list` shows monitors (once created)
- [ ] `/opt/hermes/.venv/bin/python scripts/daily-research-run.py --dry-run` completes without errors
- [ ] Fixture run works: `python3 scripts/daily-research-run.py --fixture "$COMPETITIVE_RESEARCH_OUTPUT_ROOT/raw/2026-06-17.json" --local-synthesis`
- [ ] Direct fetch smoke run works: `python3 scripts/daily-research-run.py --direct-limit 5 --skip-search --local-synthesis`
- [ ] First real run produces the daily pulse: Bottom line, Recommended action, Evidence, Watch trigger, Research coverage
- [ ] Weekly run produces: What changed, Strategic pattern, Recommended actions by owner, Battlecard updates, Coverage gaps
- [ ] Brief contains synthesized narratives, not listed findings
- [ ] Every material claim has an inline source link and a date
- [ ] No `date not found` appears in Bottom line or Evidence behind the recommendation
- [ ] Algolia capability claims are checked against validated Algolia baseline
- [ ] Brief does not say or imply Algolia lacks MCP
- [ ] Confirmed facts, public-evidence inferences, and unknowns are labeled in plain language where needed
- [ ] Recommended action appears once and is not framed as a weekly plan
- [ ] Decision guardrails section has Validate and Do not do bullets
- [ ] Change-trigger section contains only conditions that would alter the recommendation, urgency, or owner
- [ ] Brief saves to `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/briefs/`
- [ ] HTML report saves to `/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/artifacts/competitive-research/reports/`
- [ ] HTML report uses official Algolia design language: Sora, Nebula Blue, Algolia-style cards/tables, and real logo asset when available
- [ ] HTML report first viewport shows decision, owner, evidence count, top competitor, confidence
- [ ] HTML report renders cleanly in Telegram's iPhone document viewer with readable body text, non-cramped stat cards, no duplicate body title, and wrapped evidence URLs
- [ ] Stdout is concise enough for Telegram and does not dump the full report
- [ ] `--resume` flag works to skip collection and re-synthesize from cached JSON
- [ ] `--deep` flag remains concise unless Arijit explicitly requests a long version
- [ ] Cron job created: `hermes cron list | grep competitive`
- [ ] Cron wrapper exists and is executable at `/opt/data/scripts/competitive-research-daily.sh`
- [ ] No duplicate cron wrapper exists at `/opt/data/.hermes/scripts/competitive-research-daily.sh`
- [ ] `/opt/data/config.yaml` has `cron.script_timeout_seconds: 900`
- [ ] Vault archive sync includes only `reports/` and `briefs/`; raw/audit/debug files remain on VPS unless debugging
