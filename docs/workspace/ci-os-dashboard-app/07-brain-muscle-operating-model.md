# Argus Brain And Muscle Operating Model

Date: 2026-07-11
Status: Architecture contract for implementation

## Core Point

The screen is not the product.

The product is the operating loop behind the screen:

1. Hermes runs the CI operating cadence.
2. CI-OS, as a separate package, owns the competitive intelligence domain logic.
3. Argus, as the CI agent, turns evidence into judgments, challenges weak reads, and records learnings.
4. The UI only exposes the current state of that intelligence system.

If the UI cannot trace a recommendation back to product evidence, conversation evidence, demand evidence, coverage state, and learning history, it is not intelligence. It is decoration.

## Brain Versus Muscle

### Muscle

Muscle is the product reality layer. It answers:

- What did competitors actually ship?
- What did Algolia actually ship?
- Which capabilities exist, are claimed, are missing, are unproven, or are stale?
- How does the market feature map change over time?

Muscle data comes from:

- competitor changelogs
- competitor release notes
- competitor docs
- competitor API docs
- competitor integration pages
- competitor pricing and packaging pages
- competitor product pages
- Algolia changelogs
- Algolia docs
- Algolia product pages
- Algolia release notes
- Scout extraction runs over those surfaces

The muscle output is a comparable feature matrix, not a list of pages.

### Awareness

Awareness is the market conversation layer. It answers:

- What are competitors saying?
- Which themes are heating up?
- Which competitors are trying to own a narrative?
- Which partner or ecosystem movement changes the market?

Awareness data comes from:

- competitor blogs
- customer stories
- launch pages
- webinars and events
- analyst pages
- public news
- executive posts and public statements
- social posts where permitted and sourceable
- public partner ecosystem pages

Awareness cannot prove product reality. It can only prove narrative movement.

### Demand

Demand is the audience response layer. It answers:

- What is Algolia's audience showing interest in?
- Which themes are gaining or losing engagement?
- Which competitor narratives overlap with high-intent Algolia traffic?
- Which product gaps matter because the market is actually paying attention?

Demand data comes from:

- GA4 or Looker Studio exports
- page-level traffic
- campaign/referrer data
- search query data if available
- engagement metrics
- conversion metrics
- time-window deltas

Demand does not prove competitor movement. It proves audience response.

### Brain

Brain is the synthesis layer. It answers:

- What changed?
- Who moved?
- Is this speech, product reality, or audience demand?
- Is there a product gap, narrative gap, opportunity, or false alarm?
- What should Algolia do next?
- How confident is Argus, and why?
- What did Hermes fail to check?
- What should the next run do differently?

Brain is built from deterministic scoring, evidence constraints, and agent synthesis. It is not a free-form LLM summary.

## Storage Model

CI-OS stores intelligence as durable objects. The UI should read these objects, not scrape generated prose.

### Registry Tables

- `tenants`: customer context, such as Algolia.
- `competitors`: monitored competitors.
- `sources`: monitored conversation sources.
- `product_surfaces`: monitored product/changelog/docs surfaces.
- `source_candidates`: discovered sources awaiting promotion.
- `source_health_events`: health and failure history.
- `competitor_scan_rollups`: daily coverage by competitor.

### Evidence Tables

- `intel_fetch_runs`: collection sweep records.
- `source_snapshots`: captured source content.
- `raw_findings`: atomic extracted observations with evidence URL/text.
- `feature_evidence_links`: normalized feature evidence edges.

### Muscle Tables

- `feature_capabilities`: canonical capability taxonomy.
- `product_change_events`: observed product releases, docs updates, pricing changes, integrations, deprecations.
- `company_feature_positions`: current feature matrix position for Algolia, competitors, and partners.
- `product_surfaces`: source registry for changelog/docs/product extraction.

### Awareness Tables

- `conversation_themes`: source-backed theme intensity by company/topic.
- `gtm_narrative_signals`: positioning and campaign shifts.
- `executive_speech_signals`: executive public claims.
- `content_observations`: public content pieces.
- `social_observations`: public social observations where allowed.

### Demand Tables

- `demand_signals`: GA4/Looker/analytics-derived demand by topic, metric, window, and source.

### Intelligence Tables

- `semantic_facts`: durable evidence-backed facts.
- `semantic_deltas`: material changes with why-it-matters and recommended action.
- `claims` and `claim_observations`: repeated claims over time.
- `competitor_theses`: living hypotheses about competitor strategy.
- `pattern_observations`: cross-plane product/conversation/demand patterns.
- `argus_recommendations`: owner-specific actions with scorecard and evidence.
- `action_items`: routed work items for PMM, Product, Sales, Content, Executive.
- `product_market_run_intelligence`: one durable Argus read per run.

### Learning Tables

- `learning_events`: lessons from runs and operator feedback.
- `improvement_queue`: proposed changes to source strategy, thresholds, taxonomy, or prompts.
- `quality_reviews`: quality gate output.
- `false_negative_audits`: "was it really quiet?" checks.
- recommendation challenge records in the learning layer.

### Artifact Storage

Generated artifacts are derived from database state:

- dashboard JSON
- brief HTML
- entity-specific brief HTML
- evidence bundles
- run reports
- Telegram/email delivery payloads

Artifacts are publish outputs, not the source of truth.

## Hermes And CI-OS Boundary

Hermes core owns:

- cron scheduling
- profile execution
- Argus session and memory context
- model routing
- channel routing
- runtime observability
- generic tool execution

CI-OS package owns:

- competitor and partner registry
- source registry
- product surface registry
- source collection contracts
- Scout-style product surface extraction
- feature taxonomy
- evidence store
- semantic extraction
- scoring
- pattern detection
- recommendation generation
- quality gates
- dashboard and brief state generation
- admin UI

CI-OS must remain installable into another Hermes instance without modifying Hermes core.

## Daily Operating Workflow

### Stage 1: Run Initialization

Hermes starts a CI-OS run for a tenant.

Inputs:

- tenant slug
- run window
- cadence: daily, weekly, ad hoc
- Argus profile
- active registry state
- last run state
- active learning instructions

Outputs:

- run id
- run record
- stage plan
- coverage thresholds

### Stage 2: Registry Resolution

CI-OS reads the active monitored universe:

- competitors
- partners
- product surfaces
- conversation sources
- source status
- priorities
- retired/paused/skipped entries

This prevents the "only Elastic and Constructor exist" failure. The monitored universe comes from DB runtime state, not a small static YAML list.

### Stage 3: Outward Collection

Hermes invokes CI-OS collectors.

Conversation collectors capture:

- blogs
- pages
- public announcements
- news
- executive speech
- case studies

Product muscle collectors capture:

- changelogs
- docs updates
- release notes
- product pages
- pricing
- integrations
- API docs

All captures create:

- source health events
- snapshots
- raw findings
- fetch-run metadata

Quiet is not allowed unless sources were checked or explicitly skipped.

### Stage 4: Scout Product Extraction

Scout-style extraction converts product surfaces into structured product events:

- capability text
- canonical capability candidate
- change type
- company
- date observed
- evidence text
- evidence URL
- confidence

The output updates:

- `product_change_events`
- `feature_capabilities`
- `company_feature_positions`
- `feature_evidence_links`

This is the feature comparison matrix engine.

### Stage 5: Conversation Extraction

CI-OS extracts market conversation into:

- claims
- themes
- narrative shifts
- executive speech signals
- content observations

The output updates:

- `conversation_themes`
- `gtm_narrative_signals`
- `executive_speech_signals`
- `claims`
- `semantic_facts`
- `semantic_deltas`

### Stage 6: Demand Import

CI-OS imports GA4/Looker exports into demand signals:

- topic
- metric
- value
- delta
- period
- source label
- evidence refs

The output updates:

- `demand_signals`

Demand is explicitly marked as tenant-side audience response, not competitor proof.

### Stage 7: Normalization And Linking

CI-OS links the three evidence planes:

- product changes to canonical capabilities
- conversation themes to capabilities
- demand topics to capabilities and themes
- competitors and partners to categories
- repeated claims to prior observations

This creates the semantic graph that powers the UI.

### Stage 8: Pattern Detection

Argus detects cross-plane patterns, for example:

- competitor ships feature and increases narrative pressure
- competitor talks loudly but has weak product proof
- Algolia has product strength but weak public narrative
- market demand rises around a theme where Algolia is under-positioned
- several competitors converge on the same capability
- a quiet period is untrustworthy because source coverage degraded

The output updates:

- `pattern_observations`
- `competitor_theses`

### Stage 9: Scoring

Every promoted pattern or recommendation receives a scorecard.

Required dimensions:

- materiality
- novelty
- recency
- evidence strength
- source coverage
- corroboration
- product proof strength
- conversation intensity
- demand overlap
- Algolia actionability
- confidence penalty for failed or stale sources

The score is explainable. A user must be able to see why Constructor outranks Coveo or why Elastic is a watch item instead of P1.

### Stage 10: Recommendation Generation

Argus generates owner-specific recommendations:

- PMM: positioning and narrative actions
- Sales: battlecard and objection actions
- Product: feature investigation and roadmap watch items
- Content: campaign/content ideas
- Executive: strategic watch or escalation

The output updates:

- `argus_recommendations`
- `action_items`

No recommendation can publish without evidence refs and a scorecard.

### Stage 11: Quality And False-Quiet Review

Argus challenges the run before publish:

- Were all active sources checked?
- Were failures disclosed?
- Were quiet competitors actually checked?
- Are recommendations overclaiming beyond evidence?
- Are product claims backed by product surfaces, not blogs?
- Are demand claims backed by analytics, not intuition?
- Are there contradictory signals?
- Did the run consume learning instructions from prior failures?

The output updates:

- `quality_reviews`
- `false_negative_audits`
- `product_market_run_intelligence`

### Stage 11b: Product Muscle Work Queue

Before Argus treats the feature matrix as trustworthy, CI-OS derives a
product-muscle operator queue from the registry, feature comparison matrix, and
evidence ledger.

The queue names active monitored competitors that cannot yet support product
intelligence:

- no active changelog, docs, release notes, API docs, pricing, integration, or
  product page surfaces
- active product surfaces exist, but Scout extraction has not produced feature
  evidence or product events

These work items do not live in Hermes core. They are CI-OS package state. Hermes
uses them to know what product-surface or Scout work must happen next before
Argus can trust quiet-day reads, product gaps, or product-backed
recommendations.

The admin/API contract is:

- `/api/tenants/{tenant_slug}/argus/product-muscle-work-queue`
- admin section: `Argus product muscle work queue`
- package preflight requires `src/cios/admin/product_muscle_work_queue.py`

### Stage 12: Publish Gate

CI-OS publishes only when gates pass or degradation is explicitly allowed and disclosed.

Gate checks:

- coverage threshold
- source failures named
- generated_at current
- dashboard, brief, entity briefs, and JSON share the same run id
- recommendations have evidence and scorecards
- no entity link bleeds into another entity
- no "quiet day" claim if sources failed or were not checked

### Stage 13: Delivery

Hermes delivers the output through configured channels:

- web dashboard
- Telegram
- email
- future Slack or other channels

Delivery records are stored in delivery tables.

### Stage 14: Learning Loop

Argus records what happened after the run:

- user challenged a recommendation
- user accepted or dismissed an action
- source failed repeatedly
- a quiet competitor later produced a missed signal
- a taxonomy mapping was wrong
- a recommendation was too generic
- a demand signal should change priority rules

The next run consumes these as learning instructions.

Learning updates:

- source reliability weights
- extraction prompts
- scoring thresholds
- taxonomy mappings
- source discovery priorities
- recommendation specificity rules

Learning is not magic memory. It is explicit state that modifies future runs.

## Internal Synthesis Contract

Argus should never synthesize directly from raw source text into an executive answer.

The chain must be:

```text
source snapshot
-> raw finding
-> evidence-backed claim or product event
-> normalized capability/theme/topic
-> signal
-> move
-> pattern
-> implication
-> recommendation
-> scorecard
-> evidence chain
-> run intelligence record
-> UI state and delivery artifact
```

If the chain breaks, the UI may show the item in Evidence, but it cannot promote it to the Brief.

## What Data The UI Should Receive

The live UI should consume a single dashboard state payload derived from current DB state.

Required top-level sections:

- run: id, cadence, generated_at, publish status, degradation state
- argus_read: verdict, top insight, why now, confidence limits
- recommendations: owner, action, why now, urgency, scorecard, evidence refs
- market_patterns: pattern type, capability/theme, companies, confidence, trend
- heatmap: entity x theme/capability intensity, materiality, confidence
- timeline: dated moves across product, conversation, and demand
- entities: competitors and partners, status, coverage, source count, recent moves
- entity_details: selected entity read, moves, features, gaps, evidence, recommendations
- feature_matrix: capabilities x companies, status, evidence, confidence
- demand_lens: topic metrics, changes, source labels, evidence refs
- evidence: claims, product events, failed sources, rejected/suppressed items
- learning: consumed instructions, saved learnings, open improvement proposals

## What Makes It Intelligent

Argus is intelligent only if it can do these jobs:

1. Separate talk from shipped product.
2. Compare competitors and Algolia on canonical capabilities.
3. Detect change over time, not just today's scrape.
4. Merge outside market movement with inside demand signals.
5. Explain why one competitor deserves attention over another.
6. Say when it does not know.
7. Penalize weak coverage.
8. Surface contradictions.
9. Convert patterns into owner-specific actions.
10. Learn from challenges, failures, misses, and accepted actions.

## Minimum Viable Brain

The first real version does not need every possible connector. It needs one complete vertical slice:

1. 10 to 20 active competitors and partners.
2. Product surfaces for Algolia plus at least 5 priority competitors.
3. Conversation sources for all monitored entities.
4. One GA4/Looker import format.
5. A canonical feature taxonomy with 20 to 40 capabilities.
6. Product change extraction into feature positions.
7. Conversation theme extraction.
8. Demand topic import.
9. Pattern detection across product, conversation, and demand.
10. Evidence-backed recommendation generation.
11. Quality gate and false-quiet audit.
12. Dashboard state powered by these objects.
13. Argus command surface that can explain, challenge, rerun, save learning, and open evidence.

## Build Priority

1. Make the database/state contract authoritative.
2. Make Hermes execute the complete CI-OS run.
3. Make Scout/product-surface extraction update the feature matrix.
4. Import GA4/Looker demand into `demand_signals`.
5. Build the pattern engine and recommendation scorecards.
6. Make the UI read only from the synthesized state payload.
7. Add Argus Command actions that mutate learning and run state.
8. Add full E2E validation from source capture to recommendation click.

## Implementation Note: Product-Muscle Work Queue As Run Truth

Date: 2026-07-12

The product-muscle work queue is no longer only an admin/UI read model. Hermes
now receives it as a same-run artifact:

- `scripts/export_argus_product_muscle_work_queue.py`
- `out/argus-product-muscle-work-queue.json`
- `build_argus_operator_handoff.py --product-muscle-queue ...`
- `export_argus_data_plane_manifest.py --product-muscle-work-queue ...`

Meaning:

- Missing product surfaces now block the product-reality plane in the
  data-plane manifest.
- The operator handoff can tell Hermes the next product-muscle action, such as
  adding a changelog/docs/release/API/pricing/integration/product source.
- `deploy/cios-daily.sh` validates the artifact before publishing, so the
  public dashboard cannot quietly ignore missing feature-matrix coverage.
- `verify_hermes_package_contract.py` requires the exporter and wrapper
  arguments, so a deployed package cannot pass preflight while missing this
  run-truth path.

## Acceptance Test

Argus passes the brain test when it can answer this with evidence:

> In the last 7 and 30 days, what did competitors ship, what did they say, what did Algolia ship, what did Algolia's audience respond to, where is the mismatch, and what should PMM, Product, Sales, Content, and Executive teams do next?

Pass conditions:

- every product claim cites product/changelog/docs evidence
- every conversation claim cites public conversation evidence
- every demand claim cites GA4/Looker evidence
- every recommendation has a scorecard
- every scorecard is explainable
- every entity can be opened without cross-entity bleed
- quiet entities have coverage proof
- failed sources reduce confidence
- Argus can challenge and revise its own read
- the next run consumes saved learning
