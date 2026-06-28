# Competitive research methodology

The v2 skill implements a B2B SaaS competitive intelligence operating loop:

1. Collect public-source evidence.
2. Store raw snapshots and normalized signals.
3. Score signals by confidence, novelty, and impact.
4. Ask Hermes to synthesize from the ledger.
5. Deliver actionable outputs for Telegram and HTML review.
6. Reuse the ledger for weekly and monthly pattern analysis.

## Source hierarchy

Prefer primary and competitor-owned sources:

- Changelogs, docs, help centers, GitHub releases.
- Product pages, pricing pages, comparison pages.
- Press releases, investor news, named customer wins.
- Case studies, marketplace pages, partner pages.
- Analyst/review/community sources for buyer voice.
- Broader web search only for discovery or corroboration.

## Cadence

- Daily: material deltas only. Avoid a large report unless there is a real signal.
- Weekly: synthesize patterns and recommend owner-specific actions.
- Monthly: review pricing, positioning, customer voice, SEO/AI visibility, and battlecards.
- Quarterly: refresh competitor profiles, threat maps, and strategic recommendations.

## Output standard

Useful CI output must answer:

- What changed?
- Why does it matter to Algolia?
- Which team owns the first move?
- What evidence supports this?
- What would change the recommendation?
- What is unknown and needs validation?

Do not ship generic dashboards, undated claims, source dumps, or recommendations
without an action owner.
