# Semantic Intelligence Layer

Date: 2026-06-28
Status: Implemented as the first deterministic v1 slice.

## Purpose

The CI engine must not publish raw page-change events as intelligence. Scout and direct fetch produce acquisition snapshots; `ci_core.py` now converts those snapshots into semantic facts, compares facts against the previous snapshot, and publishes only material semantic deltas.

## First Intelligence Lanes

1. Customer Proof Intelligence
   - Sources: customer pages, case studies, customer story pages.
   - Initial competitors: Constructor, Bloomreach, Coveo.
   - Publishable deltas: new named customer proof, new outcome, new metric, or new AI/search/product-discovery proof.
   - Default owner: Sales Enablement.

2. Content/Narrative Intelligence
   - Sources: blogs, press/news pages, RSS/content pages, AI/search pages.
   - Publishable deltas: new AI search, agentic search, product discovery, proof-backed narrative, or campaign-worthy claim.
   - Default owner: Product Marketing.

## Ledger Tables

`semantic_facts` stores extracted source-specific facts with source URL, evidence text, evidence URL, confidence, and typed JSON.

`semantic_deltas` stores before/after comparison results with materiality score, Algolia implication, action owner, recommended action, evidence URLs, and `quality_status`.

The legacy `signals` table remains for compatibility, but direct source collection now inserts signals only from `semantic_deltas` where `quality_status = publish`.

## Publish Gates

The engine suppresses:

- first-run baseline captures
- collector-method changes
- hash-only movement
- cookie, nav, footer, and boilerplate changes
- changes that do not map to a supported semantic schema
- deltas below materiality threshold

Suppressed deltas stay in `semantic_deltas` for diagnostics and dashboard trust, but they do not become executive findings.

## Report Contract

Daily reports should answer:

- What changed
- Why it matters to Algolia
- Recommended action
- Evidence
- Validation needed

Weekly reports should answer:

- Customer proof movement
- Content/narrative movement
- Campaign opportunities
- Recommended actions by owner
- Battlecard updates
- Suppressed weak signals
- Coverage gaps

## Dashboard Contract

Dashboard v2 exposes four intelligence products:

- Customer Proof Radar
- Narrative And Content Radar
- Decision Queue
- Suppressed Signals

Dashboard export still reads archived Markdown briefs, so semantic lane quality depends on daily and weekly reports being generated from semantic deltas.
