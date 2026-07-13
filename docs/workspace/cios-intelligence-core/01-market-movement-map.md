# Market Movement Map

## Problem

Argus already stores product events, conversation themes, demand signals, feature positions, patterns, recommendations, and run summaries. That proves the pipeline can produce a single-run read, but it does not yet give Hermes a compact longitudinal object that answers:

- What is heating up?
- Which companies are repeatedly moving?
- Which capabilities are turning from isolated events into a pattern?
- What evidence backs the read?
- Where is confidence constrained?

Without that object, the UI can show a heat map, but Hermes cannot reliably learn from it or explain it as a first-class run artifact.

## Decision

Add `cios.intelligence.market_movement` as a package-level primitive. It will derive a `MarketMovementMap` from current product-market patterns plus optional historical pattern rows. The map will include:

- `direction_summary`
- `hot_capabilities`
- `heat_cells`
- `entity_velocity`
- `evidence_urls`
- `confidence_limits`

The product-market runner will embed this map inside `ProductMarketIntelligenceBrief`, which is already persisted in `product_market_run_intelligence.intelligence_brief`.

## Boundary

Hermes remains the scheduler and executor. CI-OS owns this business logic. No Hermes core files are modified.
