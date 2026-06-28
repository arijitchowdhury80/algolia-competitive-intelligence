# Competitive intelligence signal taxonomy

This skill stores normalized public-source signals in SQLite before asking Hermes
to synthesize. Do not treat raw web results as finished intelligence.

## Categories

- `product_release`: public launch, feature announcement, GA notice, product expansion.
- `changelog_docs_change`: changelog, docs, help center, GitHub release, or protocol update.
- `pricing_packaging`: pricing, tiering, packaging, billing model, usage limit, free tier.
- `positioning_messaging`: homepage, product page, comparison page, category narrative.
- `customer_proof`: case study, customer win, named logo, deployment reference.
- `partnership_marketplace`: partner page, marketplace listing, co-sell, integration.
- `hiring_org_signal`: job posting, executive change, hiring pattern, org direction.
- `analyst_review_signal`: Gartner, Forrester, G2, TrustRadius, analyst or review signal.
- `customer_community_voice`: Reddit, HN, forum, public complaint, buyer discussion.
- `seo_content_movement`: blog, keyword/theme movement, content campaign, AI answer visibility source.
- `ai_visibility`: AI search, agent, MCP, A2A, ChatGPT, Perplexity, Gemini, agentic commerce.
- `sales_relevant_objection`: public evidence likely to matter in competitive deals.
- `algolia_baseline_comparison`: Algolia public baseline used to avoid false gap claims.

## Scoring

Each signal receives:

- `confidence`: source reliability and evidence clarity.
- `novelty`: whether this is a new delta or a baseline snapshot.
- `impact`: likely competitive relevance to Algolia.
- `score`: weighted combination of confidence, novelty, and impact.

Signals are not recommendations by themselves. Recommendations come only after
synthesis across the signal ledger.

## Action owners

- Product: product releases, docs/changelog changes, roadmap-adjacent deltas.
- Product Marketing: positioning, AI visibility, Algolia baseline comparison.
- Sales Enablement: customer proof, reviews, objections, pricing claims.
- Partner Enablement: partner, marketplace, co-sell, integration signals.
- Competitive Intelligence: weak or exploratory signals needing monitoring.
- Executive Review: category-level, financial, analyst, or market-structure shifts.

## V1 scope

V1 is public-source only. It does not connect to Gong, Salesforce, Slack, G2
paid exports, Semrush APIs, or internal win/loss systems. Add those only after
the public-source ledger proves useful.
