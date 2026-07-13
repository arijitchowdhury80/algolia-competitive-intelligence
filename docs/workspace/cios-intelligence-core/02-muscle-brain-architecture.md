# CI-OS Muscle And Brain Architecture

Date: 2026-07-11
Status: Architecture contract for the next build slice

## Core Decision

The dashboard is not the product. The product is the Hermes-run intelligence loop behind it.

CI-OS must become a Hermes extension package that gives Hermes a competitive intelligence operating capability. Hermes schedules, executes, remembers, routes, and delivers. CI-OS owns the domain model, evidence store, scoring, synthesis, recommendations, source registry, feature matrix, and admin workflows.

If a screen cannot trace a recommendation back to product evidence, conversation evidence, demand evidence, coverage state, scorecard, and learning history, it is only a report shell. It should not be called intelligence.

## What Exists Now

The codebase already has partial foundations:

- `src/cios/collect`: public source fetching, snapshots, facts, deltas.
- `src/cios/hunter`: source discovery, validation, lifecycle.
- `src/cios/intelligence`: product-market value objects, product-market synthesis, market movement, feature matrix helpers, GA4 / Looker import helpers, Scout-style product surface exporter.
- `src/cios/learn`: learning events, improvement queue, recommendation challenge flow.
- `src/cios/dashboard`: generated dashboard state and renderers.
- `src/cios/db/schema.sql`: tenant-scoped Postgres schema with competitors, sources, product surfaces, product events, feature positions, conversation themes, demand signals, patterns, recommendations, quality, learning, and delivery tables.
- Hermes scheduler path has been repaired for the live daily run: `Hermes cron -> cios-daily.sh -> /opt/data/apps/cios`.

This is not enough. The missing piece is the durable operating loop: every stage must write its run state, every judgment must have a scorecard, every quiet claim must have coverage proof, every inward demand read must be imported, and every user challenge must feed the next run.

## The Five Data Planes

### 1. Product Reality Plane: The Muscle

Purpose: prove what companies actually ship, document, price, deprecate, integrate, or package.

Inputs:

- competitor changelogs
- competitor release notes
- competitor docs
- competitor API docs
- competitor integration pages
- competitor pricing and packaging pages
- competitor product pages
- Algolia changelog, docs, release notes, product pages, integration pages, pricing and packaging pages
- Scout extraction over all product surfaces

Stored as:

- `product_surfaces`
- `feature_capabilities`
- `product_change_events`
- `company_feature_positions`
- `feature_evidence_links`

Output:

- product and feature comparison matrix
- product velocity by company
- capability heat by company
- Algolia versus competitor product gaps
- evidence-backed product events

Rule:

Blogs and marketing pages cannot prove product reality. They can point to a hypothesis, but product reality needs changelog, docs, release note, product page, API doc, pricing page, or equivalent product-surface evidence.

### 2. Market Conversation Plane: The Awareness Layer

Purpose: prove what the market and competitors are saying.

Inputs:

- blogs
- launch pages
- case studies
- webinars
- events
- press pages
- analyst pages
- executive public posts and statements
- public social content where permitted and sourceable
- partner ecosystem pages

Stored as:

- `conversation_themes`
- `claims`
- `claim_observations`
- `semantic_facts`
- `semantic_deltas`
- `gtm_narrative_signals` when added or mapped through semantic deltas

Output:

- narrative pressure
- repeated claims
- campaign shifts
- competitor positioning moves
- conversation heat by theme

Rule:

Conversation proves narrative, not shipped capability.

### 3. Tenant Demand Plane: The Inside Signal

Purpose: prove what Algolia's audience is responding to.

Inputs:

- GA4 / Looker Studio exports
- page-level analytics
- topic-level engagement
- search query data if available
- campaign and referrer data if available
- conversion metrics if available
- Algolia.com traffic to product, solution, docs, comparison, and pricing pages

Stored as:

- `demand_signals`

Output:

- rising or falling demand by topic
- demand overlap with competitor narratives
- demand overlap with Algolia product strengths or gaps
- conversion blockers and interest mismatches

Rule:

Demand proves audience behavior. It does not prove competitor movement.

Current gap:

The live system still has `demand_signal_count=0` because GA4 / Looker demand has not been configured or uploaded into the daily loop.

### 4. Registry And Coverage Plane

Purpose: define what Argus is responsible for watching and whether it actually watched it.

Inputs:

- tenant registry
- competitor registry
- partner registry
- source registry
- product surface registry
- paused, retired, blocked, missing, and credentials-needed statuses

Stored as:

- `tenants`
- `competitors`
- `sources`
- `product_surfaces`
- `source_health_events`
- `source_scan_runs`
- `source_observations`
- `competitor_scan_rollups`

Output:

- monitored universe
- active source count
- failed source count
- checked today state
- stale source state
- false quiet risk

Rule:

The run reads runtime DB registry state. YAML can seed defaults, but YAML must not limit what Hermes checks.

### 5. Operator Learning Plane

Purpose: make Argus improve from failures, challenges, accepted actions, dismissed actions, and source reliability.

Inputs:

- user challenges
- accepted recommendations
- dismissed recommendations
- saved learnings
- quality review failures
- false-negative audits
- repeated source failures
- missed signals discovered later
- taxonomy corrections
- operator reruns

Stored as:

- `learning_events`
- `improvement_queue`
- `quality_reviews`
- `false_negative_audits`
- recommendation challenge records through the learning layer
- `run_stage_ledgers`
- `run_stage_events`

Output:

- next-run instructions
- source reliability changes
- scoring threshold changes
- extraction prompt changes
- taxonomy mapping proposals
- source discovery priorities
- recommendation specificity rules

Rule:

Learning is not vague LLM memory. Learning is explicit state that modifies future runs only after policy gates.

## The Internal Workflow

### Stage 0: Hermes Run Start

Hermes starts a tenant run for a cadence: daily, weekly, ad hoc, or operator-triggered.

Inputs:

- tenant slug
- Argus profile
- run window
- active learning instructions
- active registry state
- last successful run state
- policy thresholds

Outputs:

- `run_id`
- run stage plan
- coverage thresholds
- execution budget
- model budget

Required new object:

- `run_stage_ledgers`: one durable run parent row
- `run_stage_events`: one ordered row per stage result, with start/end timestamps, success/failure/skip status, elapsed time, artifact metadata, and error summary

### Stage 1: Registry Resolution

CI-OS resolves the monitored universe from the DB:

- active competitors
- active partners
- active conversation sources
- active product surfaces
- paused / retired / blocked sources
- credentials-needed sources
- last check state
- priority

This prevents the old failure where the UI looked like only Elastic and Constructor existed.

### Stage 2: Source Sweep

Hermes invokes CI-OS collectors for public conversation sources.

Writes:

- `intel_fetch_runs`
- `source_snapshots`
- `raw_findings`
- `semantic_facts`
- `semantic_deltas`
- `source_health_events`

Gates:

- active source threshold met
- failed source count disclosed
- quiet competitors have checked-source proof

### Stage 3: Product Muscle Extraction

Scout-style extraction runs over product surfaces.

Writes:

- `product_change_events`
- `feature_capabilities`
- `company_feature_positions`
- `feature_evidence_links`

Jobs:

- detect releases
- detect docs updates
- detect pricing and packaging changes
- detect integrations
- detect API changes
- detect deprecations
- update the feature matrix

This is where Argus stops being a blog scanner and starts becoming a product intelligence system.

### Stage 4: Conversation Extraction

The awareness plane extracts what competitors and the market are saying.

Writes:

- `conversation_themes`
- `claims`
- `claim_observations`
- `semantic_facts`
- `semantic_deltas`

Jobs:

- detect narrative themes
- detect repeated claims
- detect GTM shifts
- detect executive speech signals
- detect partner and ecosystem moves

### Stage 5: Inward Demand Import

GA4 / Looker data is imported.

Writes:

- `demand_signals`

Jobs:

- normalize topics
- calculate deltas
- preserve source row and source file evidence
- map demand topics to capabilities and conversation themes
- expose diagnostics for skipped rows

This is the missing inside-out layer. Without it, Argus can say what competitors are doing, but not whether Algolia's audience cares.

### Stage 6: Normalization And Linking

CI-OS links the three evidence planes:

- product events to canonical capabilities
- conversation themes to canonical capabilities
- demand topics to canonical capabilities
- companies to competitor, partner, or own-brand roles
- new claims to historical claim ledgers
- source reliability to confidence penalties

Output:

- semantic graph edges
- feature matrix updates
- claim-history updates
- confidence limits

### Stage 7: Pattern Detection

Argus detects cross-plane patterns:

- competitor shipped capability and is also increasing narrative pressure
- competitor is talking loudly without product proof
- Algolia has product strength but weak public narrative
- audience demand is rising where Algolia is under-positioned
- competitors are converging on the same capability
- a quiet day is untrustworthy because coverage degraded

Writes:

- `pattern_observations`
- `competitor_theses`
- `product_market_run_intelligence`

### Stage 8: Scoring

Every pattern and recommendation receives an explainable scorecard.

Required dimensions:

- materiality
- novelty
- recency
- product proof strength
- conversation intensity
- demand overlap
- evidence breadth
- source coverage
- corroboration
- Algolia actionability
- confidence penalty for failed or stale sources

This is how the system answers "why Constructor over Coveo?" instead of just asserting it.

### Stage 9: Recommendation Generation

Argus produces role-specific recommendations:

- PMM: positioning and narrative response
- Product: capability investigation, roadmap watch, gap analysis
- Sales: battlecard and objection handling
- Content: topic and campaign actions
- Executive: strategic escalation or watch item

Writes:

- `argus_recommendations`
- `action_items`

Gate:

No recommendation can publish without evidence refs and a scorecard.

### Stage 10: Quality And False-Quiet Review

Argus challenges its own read:

- Were all active sources checked?
- Were failures disclosed?
- Are product claims backed by product surfaces?
- Are conversation claims backed by public conversation evidence?
- Are demand claims backed by analytics evidence?
- Are quiet entities really quiet?
- Are scorecards honest?
- Is the recommendation generic?
- Did prior learning instructions affect this run?

Writes:

- `quality_reviews`
- `false_negative_audits`
- `suppressed_diagnostics`
- updated `product_market_run_intelligence`

### Stage 11: Publish Gate

CI-OS publishes only when the run is internally consistent.

Required same-run artifacts:

- dashboard JSON
- dashboard HTML
- full brief
- entity-specific briefs
- evidence bundle
- run report
- delivery payload

Block publish if:

- run failed
- source coverage threshold failed without degraded publish approval
- product-market synthesis failed
- recommendations lack evidence
- generated timestamps are stale
- entity links bleed into another entity
- quiet day is unsupported

### Stage 12: Delivery

Hermes routes the output:

- public read-only dashboard
- Telegram / Argus delivery
- email when configured
- future Slack or other channels

Writes:

- `reports`
- `bot_deliveries`
- `delivery_attempts`

### Stage 13: Operator Interaction

Argus must be usable as an agent, not just a static box.

User actions:

- ask why a recommendation was made
- challenge a recommendation
- compare two competitors
- ask what changed since yesterday, last week, or last month
- ask what was checked
- ask what failed
- ask what evidence supports a claim
- accept / dismiss / assign an action
- save a learning
- rerun a stage
- add or pause a competitor or source through admin controls

Writes:

- `learning_events`
- `improvement_queue`
- `action_items`
- `audit_events`
- future `argus_interactions`

### Stage 14: Learning Apply

Before the next run, Argus reads approved learning and changes behavior.

Examples:

- penalize a repeatedly failing source
- recheck a competitor where false-quiet risk was high
- adjust a taxonomy mapping
- increase weight for product proof over marketing talk
- suppress generic recommendations
- add missing product surfaces
- propose source additions from discovery

Writes:

- applied learning status
- new improvement proposals
- next-run instructions in the run stage ledger

## The Actual Intelligence Chain

Argus must not jump from source text to executive prose.

The required chain is:

```text
registry
-> run stage ledger
-> fetch run
-> source snapshot
-> raw finding
-> evidence-backed product event / claim / theme / demand signal
-> canonical capability or topic
-> feature position / conversation intensity / demand trend
-> pattern observation
-> scorecard
-> recommendation
-> quality review
-> learning event
-> dashboard state
-> brief / delivery
```

If any link breaks, the item can exist in evidence, but it cannot be promoted as intelligence.

## What The UI Should Read

The UI should read one state payload generated from DB state, not compute meaning in the browser.

Required sections:

- `run`: id, generated_at, cadence, publish status, degradation state
- `stage_ledger`: each stage, status, elapsed time, outputs, failures, retry count
- `argus_read`: verdict, top insight, why now, confidence limits
- `recommendations`: owner, action, why now, urgency, scorecard, evidence refs
- `market_patterns`: pattern type, capability, companies, trend, confidence
- `heatmap`: entity by capability or theme, intensity, materiality, confidence
- `timeline`: product, conversation, demand, and recommendation events across dates
- `entities`: all competitors and partners, status, coverage, source count, recent moves
- `entity_details`: selected entity read, moves, features, gaps, evidence, recommendations
- `feature_matrix`: capabilities by companies, status, evidence, confidence
- `demand_lens`: demand topics, metrics, windows, changes, source labels
- `evidence`: source snapshots, product events, claims, failed sources, suppressed items
- `learning`: consumed instructions, saved learnings, pending improvements

## What Hermes Owns Versus What CI-OS Owns

Hermes core owns:

- scheduling
- runtime profile execution
- Argus session context
- model routing
- memory context injection
- channel routing
- cron output capture
- delivery orchestration
- runtime observability

CI-OS package owns:

- competitor, partner, and source registry
- product surface registry
- source collection contracts
- product muscle extraction
- feature taxonomy
- evidence model
- semantic extraction
- pattern detection
- scoring
- recommendation generation
- quality gates
- learning loop
- dashboard and brief generation
- admin UI and run console

Boundary rule:

CI-OS must be installable into another Hermes instance as a package. It cannot require Hermes core modifications for CI business logic.

## What Must Be Built Next

### P0: Stage Ledger And Run Truth

Add durable run-stage state so Hermes and Argus can explain:

- what ran
- what did not run
- what failed
- what was skipped
- how long each stage took
- which artifacts each stage produced
- which learning instructions were consumed
- why publish was allowed or blocked

Without this, the system cannot be trusted.

Implementation update, 2026-07-11:

- The product-market daily chain now records a structured `stage_ledger` alongside the existing `CIOS_PRODUCT_MARKET_STAGE` Hermes heartbeat lines.
- Each ledger entry records `tenant`, `stage`, `status`, `started_at`, `ended_at`, and `elapsed_s`.
- Failed stages also record `error_type` and `error`.
- The stage ledger is included in `product_market_summary` for successful runs, no-surface-output runs, and failed stage runs.
- The dashboard state contract now exposes `product_market_run.stage_ledger`.
- Published dashboard JSON schema was bumped to v19 for this contract addition.
- The first durable database ledger now exists in Postgres:
  - `run_stage_ledgers`: one parent row per CI-OS package run, scoped by tenant and run id.
  - `run_stage_events`: one ordered child row per stage, with status, timestamps, elapsed seconds, error fields, and metadata.
- The product-market daily run persists its stage ledger through `PgProductMarketRepository.save_run_stage_ledger(...)`.
- The daily summary stores the returned `stage_ledger_id`, so dashboard JSON can point back to durable run truth instead of only embedding ephemeral display state.
- The tenant daily run now also persists a coarse `cios.daily` ledger after dashboard-state persistence. It records registry resolution, source sweep, synthesis, quality review, false-negative audit, delivery, product-market chain, dashboard-state build, and publish-gate status.
- The `cios.daily` ledger metadata points to the product-market `stage_ledger_id` when the product-market subchain ran, so Hermes can explain both the full daily pass and the deeper product-market subtrace.
- The run-stage persistence boundary has been promoted into a generic CI-OS repository, `PgRunStageRepository`, instead of living only inside the product-market repository.
- `run_stage_events` now allows `running` status, which enables a run console to show in-flight work instead of only completed snapshots.
- `PgRunStageRepository` now supports:
  - `start_ledger(...)`
  - `start_stage(...)`
  - `finish_stage(...)`
  - `finish_ledger(...)`
  - `save_run_stage_ledger(...)` for already-completed ledgers
- The coarse `cios.daily` ledger now writes through `PgRunStageRepository`.
- The tenant daily runner now opens the `cios.daily` ledger immediately after creating `run_id`, before registry resolution or source sweep starts.
- When the run finishes, the existing running ledger is backfilled with the coarse stage outcomes and marked terminal instead of creating a duplicate daily-ledger parent.
- Registry resolution now records a live `run_stage_events` row around competitor/source registry resolution, product surface seeding, and active-source count derivation.
- Source sweep now records a live `run_stage_events` row around the collection loop and finishes after fetched/failed/skipped source counts plus fact/delta counts are known.
- Synthesis now records a live `run_stage_events` row around synthesis target selection, per-competitor synthesis, promoted-signal selection, and final synthesis verdict.
- Quality review now records a live `run_stage_events` row around claim construction, daily brief review, one-shot revise pass, final quality status, and required-fix count.
- Delivery now records a live `run_stage_events` row around daily message construction, delivery routing, gated commander execution, and recorded bot delivery outcomes.
- Product-market chain now records a live `run_stage_events` row around current-sweep conversation record derivation, product-market execution, gap-discovery plan enrichment, sub-ledger persistence, and report metadata refresh.
- Learning application now has explicit product-market substage instrumentation:
  - `next_sweep_learning_plan` builds the approved-learning instruction artifact for Hermes.
  - `learning_apply_plan` converts approved instructions into CI-OS package-scoped actions.
  - `learning_apply_execute` runs the safe executor in proposal-only mode by default, writing reviewable package proposals and recording proposal/applied/skipped counts. Approved mutation still requires an explicit approver and remains inside the CI-OS package boundary.
- Dashboard-state build now records a live `run_stage_events` row around dashboard state construction, file publication, and dashboard-state database persistence.
- Publish gate now records a live `run_stage_events` row for the delivered tenant after `run_tenant` returns and around the real public artifact write. The delivered tenant leaves stage order `9` deferred and the daily ledger parent running until the gate either writes cockpit/brief/JSON/entity-brief artifacts or records the blocking reason.
- End-of-run backfill skips stage orders that were already recorded live, so live stage timing is not overwritten by summary backfill.

Remaining gap:

The daily ledger parent is live while the tenant pass runs. Registry, source sweep, synthesis, quality review, delivery, product-market chain, dashboard-state build, and delivered-tenant publish gate now stream as live events locally. Learning application is explicit inside the product-market subledger through next-sweep planning, apply-plan generation, and proposal-only apply execution. The next runner work is to attach retry history, model/tool budgets, and consumed-learning instructions to the relevant stages. These latest run-stage slices still need deployment and live Hermes scheduler verification.

### P0: Inward Demand Plane

Configure real GA4 / Looker import into the daily loop.

Minimum:

- upload or connect Looker exports
- normalize rows into `demand_signals`
- preserve source file, row number, and fingerprint
- map topics to capabilities
- expose import diagnostics
- rerun Argus synthesis from the evidence ledger

Without this, Argus cannot answer whether market movement matters to Algolia's audience.

### P0: Product Muscle Matrix

Make Scout product-surface extraction first-class.

Minimum:

- Algolia plus priority competitors
- changelog/docs/release/pricing/API/integration coverage
- canonical capability taxonomy
- daily product event extraction
- current feature positions
- feature comparison matrix
- evidence for every position

Without this, Argus remains a conversation scanner.

### P1: Pattern And Score Engine

Convert raw evidence into explainable intelligence.

Minimum:

- product versus conversation mismatch detection
- conversation without product proof detection
- audience demand overlap detection
- competitor convergence detection
- false quiet risk detection
- scorecard per recommendation

### P1: Argus Interaction Loop

Make Argus actions mutate durable state.

Minimum:

- challenge read
- explain score
- compare competitors
- save learning
- accept / dismiss recommendation
- rerun stage
- add source candidate
- record operator feedback

### P1: UI As Cockpit, Not Report

The UI must become a cockpit over the intelligence objects:

- run truth first
- current read second
- action board third
- market map fourth
- entity and feature matrix drilldowns fifth
- evidence and learning always inspectable

## Acceptance Test

The system is no longer an empty shell when Argus can answer this with evidence and state:

> In the last 7 and 30 days, what did competitors ship, what did they say, what did Algolia ship, what did Algolia's audience respond to, where is the mismatch, who is moving fastest, what should PMM, Product, Sales, Content, and Executive teams do next, and what did Hermes learn that changes the next run?

Pass conditions:

- every product claim cites product evidence
- every conversation claim cites public-source evidence
- every demand claim cites GA4 / Looker evidence
- every recommendation has an explainable scorecard
- every scorecard shows confidence limits
- every quiet entity has coverage proof
- every failed source reduces confidence
- every stage is visible in the run ledger
- every entity can be selected without cross-entity bleed
- every user challenge creates learning or a rejected-learning audit trail
- the next run consumes approved learning
