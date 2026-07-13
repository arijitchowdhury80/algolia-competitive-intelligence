# Argus Product-Market Intelligence Spine

Date: 2026-07-10
Status: First implementation slice

## Purpose

The UI reset is only useful if Argus has real muscle and brain underneath it.
This spine gives Argus three evidence planes:

1. Awareness: market conversation and competitor narrative.
2. Muscle: product reality from changelogs, docs, release notes, product pages, pricing, API docs, and integration docs.
3. Demand: tenant-side audience response from GA / Looker Studio or equivalent analytics exports.

Argus should not promote a loud conversation as action unless product reality
and/or demand justify it. Conversation without product proof is a watch item,
not a recommended move.
Outward evidence can still create non-actionable watch patterns: if a
competitor both ships and says something, Argus should remember the movement
even when tenant-side demand is missing. Missing demand blocks action
promotion, not pattern memory.

## Architecture: Muscle, Brain, and Memory

Argus is not the UI. The UI is only the readout. The operating system behind
it has four layers:

1. Collection muscle:
   - Scout extracts outward product reality from competitor and Algolia
     changelogs, docs, release notes, product pages, pricing pages, API docs,
     integrations, and other monitored product surfaces.
   - Daily CI scans extract outward market conversation from blogs, landing
     pages, news, social, and GTM pages.
   - Looker / GA exports bring inward demand: what Algolia audiences are
     reading, searching, engaging with, and returning to.
2. Evidence ledger:
   - Every extracted item becomes a tenant-scoped, evidence-backed row:
     `product_change_events`, `conversation_themes`, `demand_signals`,
     `feature_evidence_links`, and source-health rows.
   - No recommendation or published pattern is allowed to stand without proof.
3. Synthesis brain:
   - `ProductMarketIntelligenceWorkflow` joins product reality, conversation,
     and demand into feature positions, pattern observations, scorecards, and
     owner-specific recommendations.
   - The synthesizer separates "what they shipped", "what they said", "what
     the market seems to care about", and "what Algolia should do next".
4. Learning memory:
   - User challenges and rejected reads become `learning_events` and
     `improvement_queue` entries.
   - Approved improvements become a next-sweep learning plan that changes the
     following run's collection priority and action threshold without changing
     Hermes core.
   - Each run writes `product_market_run_intelligence`, an append-only brain
     record containing the actual Argus read, confidence limits, evidence URLs,
     next questions, and learning instructions consumed.

Hermes is the executor and operating loop. CI-OS is the package Hermes runs.
Hermes schedules the sweep, calls the package scripts, routes Scout and Looker
inputs into the payload, invokes Argus synthesis, records the run memory, and
publishes the dashboard only after the package has produced a traceable state.
`deploy/cios-daily.sh` is the Hermes cron wrapper for that boundary: it keeps
the VPS defaults, accepts explicit package/public/env overrides for validation
and portability, enables the product-market spine by default, and refuses to
touch the public site unless the current run produced the cockpit, full brief,
dashboard JSON, and competitor-brief directory.
The package remains portable: another Hermes can install CI-OS and get the
same collection, synthesis, storage, learning, and dashboard contracts without
modifying Hermes core.

## First Implemented Module

Package:

- `cios.intelligence`

Core files:

- `src/cios/intelligence/types.py`
- `src/cios/intelligence/product_market.py`
- `src/cios/intelligence/product_surface_planner.py`
- `src/cios/intelligence/feature_matrix.py`
- `src/cios/intelligence/adapters.py`
- `src/cios/intelligence/inputs.py`
- `src/cios/intelligence/importers.py`
- `src/cios/intelligence/scout_adapter.py`
- `src/cios/intelligence/scout_surface_exporter.py`
- `src/cios/intelligence/ga4_exporter.py`
- `src/cios/intelligence/runner.py`
- `src/cios/intelligence/workflow.py`
- `src/cios/db/repos/product_market.py`
- `src/cios/db/repos/product_surfaces.py`
- `scripts/build_product_market_payload.py`
- `scripts/execute_product_surface_plan.py`
- `scripts/execute_product_muscle_gap_discovery.py`
- `scripts/export_product_surface_with_scout.py`
- `scripts/export_ga4_demand.py`
- `scripts/build_next_sweep_learning_plan.py`
- `scripts/plan_product_surface_exports.py`
- `scripts/promote_product_surface_candidates.py`
- `scripts/record_recommendation_challenge.py`
- `scripts/run_product_market_intelligence.py`
- `scripts/verify_hermes_package_contract.py`
- `deploy/cios-daily.sh`
- `src/cios/dashboard/state_builder.py`
- `src/cios/dashboard/cockpit_renderer.py`
- `src/cios/admin/app.py`
- `src/cios/admin/repository.py`
- `src/cios/admin/types.py`
- `src/cios/learn/recommendation_challenge.py`

Tests:

- `tests/intelligence/test_product_market_synthesizer.py`
- `tests/intelligence/test_product_surface_planner.py`
- `tests/intelligence/test_feature_matrix.py`
- `tests/intelligence/test_product_market_workflow.py`
- `tests/intelligence/test_runner.py`
- `tests/intelligence/test_importers.py`
- `tests/intelligence/test_scout_adapter.py`
- `tests/intelligence/test_scout_surface_exporter.py`
- `tests/intelligence/test_input_batch.py`
- `tests/intelligence/test_adapters.py`
- `tests/db/test_product_market_repo.py`
- `tests/db/test_product_surface_repo.py`
- `tests/db/test_product_market_schema_contract.py`
- `tests/scripts/test_build_product_market_payload.py`
- `tests/scripts/test_execute_product_surface_plan.py`
- `tests/scripts/test_export_product_surface_with_scout.py`
- `tests/scripts/test_build_next_sweep_learning_plan.py`
- `tests/scripts/test_plan_product_surface_exports.py`
- `tests/scripts/test_product_market_runner.py`
- `tests/scripts/test_record_recommendation_challenge.py`
- `tests/scripts/test_verify_hermes_package_contract.py`
- `tests/scripts/test_product_market_dashboard_wiring.py`
- `tests/dashboard/test_state_builder.py`
- `tests/dashboard/test_cockpit_renderer.py`
- `tests/admin/test_app.py`
- `tests/learn/test_feedback.py`
- `tests/integration/test_admin_repository.py`
- `tests/learn/test_recommendation_challenge.py`
- `tests/deploy/test_cios_daily_wrapper.py`

## Value Objects

`ProductChangeEvent`

- Captures shipped or documented product reality.
- Must include evidence.
- Intended upstream source: Scout changelog/docs/product-surface extraction.

`ConversationTheme`

- Captures what the market or a competitor is saying.
- Must include evidence.
- Does not count as product proof.

`DemandSignal`

- Captures tenant-side audience response.
- Must include GA/Looker/export evidence.
- Does not count as competitor movement.

`FeaturePosition`

- Captures one company/capability row in the product muscle matrix.
- Derived from product reality, not from market conversation.
- Current derived statuses:
  - `proven` for release, docs update, pricing change, and integration evidence.
  - `disproven` for deprecation evidence.

`PatternObservation`

- Captures the cross-plane read.
- May also capture outward-evidence watch movement when a competitor has both
  product proof and public positioning but no tenant-side demand evidence yet.
- Current pattern types:
  - `own_narrative_gap`
  - `own_product_gap`
  - `product_without_market_conversation`
  - `conversation_without_product_proof`
  - `competitive_pressure`

`Recommendation`

- Owner-specific action for PMM, Product, Sales, Content, or Executive.
- Must include evidence.
- Must include a backend `RecommendationScorecard` so the UI can show the
  actual scoring rubric Argus used, not a renderer-invented confidence story.

`RecommendationScorecard`

- Captures `total_score`, `verdict`, `summary`, and scored dimensions.
- Current dimensions:
  - `product_reality`
  - `market_conversation`
  - `audience_demand`
  - `own_response_gap`
  - `evidence_breadth`
- The total score must equal the sum of dimension scores.
- Every dimension requires rationale and evidence URLs.

## First Deterministic Reasoning Rules

1. Competitor shipping + competitor saying + rising demand + own product proof + no own narrative:
   - produce `own_narrative_gap`
   - recommend PMM action.

2. Competitor shipping + competitor saying + rising demand + no own product proof:
   - produce `own_product_gap`
   - recommend Product audit.

3. Competitor saying + rising demand + no product proof:
   - produce `conversation_without_product_proof`
   - do not recommend action yet.

4. Own product proof + rising demand + no own narrative:
   - produce `product_without_market_conversation`
   - recommend PMM action. This is the release-to-conversation gap: Algolia
     already has muscle, but the market story is missing.

5. Competitor product proof + rising demand + no own product proof:
   - produce `own_product_gap`
   - recommend Product audit even when the competitor has not turned the release
     into a public campaign yet. Changelogs and docs count as product reality;
     Argus does not wait for a blog post before noticing the gap.

6. Competitor shipping + competitor saying + no captured demand:
   - produce `competitive_pressure`
   - do not recommend action yet. This is an outward-evidence watch pattern:
     Argus remembers that the competitor has both product and narrative proof,
     but the missing demand plane prevents promotion to a PMM/Product/Sales
     action.

## Storage Contract

Added schema tables:

- `product_surfaces`
- `feature_capabilities`
- `product_change_events`
- `company_feature_positions`
- `feature_evidence_links`
- `conversation_themes`
- `demand_signals`
- `pattern_observations`
- `argus_recommendations`
- `product_market_run_intelligence`

All tables are tenant-scoped and included in the schema RLS table list.

Evidence checks:

- `product_change_event_needs_evidence`
- `conversation_theme_needs_evidence`
- `demand_signal_needs_evidence`
- `pattern_observation_needs_evidence`
- `argus_recommendation_needs_evidence`
- `argus_recommendation_needs_scorecard`
- `product_market_run_intelligence_has_brief`
- `product_market_run_intelligence_has_learning_ids`

## Implemented Data Flow

Collector-facing ingestion:

1. Scout-style changelog/docs/product records become `ProductChangeEvent`
   through `scout_record_to_product_change_event`.
2. Web-scan narrative records become `ConversationTheme` through
   `conversation_record_to_conversation_theme`.
3. Looker / GA export rows become `DemandSignal` through
   `looker_row_to_demand_signal`.
4. `build_product_market_input_batch` packages all three planes for one
   tenant run.
5. `build_product_market_payload.py` reads JSON, JSONL, or CSV export files
   and writes the runner payload contract. This lets Hermes assemble a product
   market run from file outputs without hand-written JSON.
6. `ScoutCommandSpec` lets Hermes pass one or more bounded Scout commands as
   JSON argv specs. `run_scout_export` executes the command, requires the
   declared export artifact, and merges those rows into the same Scout record
   stream.
7. `export_product_surface_with_scout.py` is the first executable Scout bridge:
   it builds a Scout `extract` command for one product surface, asks Scout for
   structured product changes, normalizes the response with
   `scout_extract_response_to_product_records`, and writes Argus-ready Scout
   rows.
8. `PgProductSurfaceRepository` reads active `product_surfaces` as
   `ProductSurfaceTarget` objects.
9. `plan_product_surface_exports.py` emits a JSON execution plan with one
   deterministic `export_product_surface_with_scout.py` command and output
   file per active product surface.
10. `execute_product_surface_plan.py` executes that plan with bounded command
    timeouts, verifies each declared output file exists, and emits the list of
    Scout files that should be passed into payload building.
11. `build_product_market_payload.py --scout` is repeatable, so many
    product-surface export files can feed one product-market run.
12. `build_product_market_payload.py --looker` is repeatable, so one or many
    Looker/GA exports can feed the demand plane of the same product-market run.
13. `daily_production_run.py` now has an env-gated
    `CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE=1` chain that plans active
    product surfaces, executes Scout exports, builds the product-market
    payload, runs `run_product_market_intelligence.py`, and only then builds
    the dashboard state.
14. The daily product-market chain accepts
    `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS`, using platform path separators, to
    attach Looker/GA demand exports to the same payload.
    It also auto-discovers tenant demand exports from
    `data/looker/<tenant-slug>/` inside the installed CI-OS package when
    `CIOS_PRODUCT_MARKET_LOOKER_AUTO_DISCOVER` is not disabled.
15. `config/tenants-sources.yaml` now includes `product_surfaces` seed data.
    Daily seeding upserts those defaults into `product_surfaces` without
    reactivating paused/retired rows, and resolves competitor ids from the
    active DB source registry so DB-only competitors can be used.
16. The local-only admin app now lists product surfaces per competitor and
    supports add/pause/retire flows through both HTML forms and JSON API
    endpoints.
17. `RecommendationChallengeRecorder` turns user challenges to an Argus
    recommendation into a `learning_events` row and a gated
    `improvement_queue` item. This is how "why this recommendation?" becomes
    next-sweep learning instead of a disposable chat exchange.
18. The local admin API exposes
    `POST /api/tenants/{tenant}/argus/recommendations/{id}/challenge`, guarded
    by the same local-only/admin-token write boundary as registry changes.
19. `scripts/record_recommendation_challenge.py` is the Hermes-callable command
    wrapper for the same flow. Hermes can call it with tenant,
    recommendation id, challenge text, category, and optional scorecard
    dimension. The script prints machine-readable JSON with learning event,
    improvement, and next-sweep instruction ids.
20. The admin app now exposes open `improvement_queue` items in the Argus
    learning queue, both in HTML and JSON. Operators can approve or reject
    items through the same local-only/admin-token write boundary.
21. `NextSweepPlanner` turns approved, evidence-linked `improvement_queue`
    items into `NextSweepInstruction` artifacts. Open, rejected, applied, or
    evidence-less items do not influence the next run.
22. `scripts/build_next_sweep_learning_plan.py` is the Hermes-callable command
    for that contract. It reads approved queue items, links them back to
    matching `learning_events`, and writes or prints a machine-readable plan
    without mutating source, scoring, taxonomy, prompt, or Hermes core state.
23. The local admin API exposes
    `GET /api/tenants/{tenant}/argus/next-sweep-plan`, so operators and
    run-console clients can inspect the exact next-sweep learning plan before
    Hermes consumes it.
24. The env-gated daily product-market chain now writes
    `next-sweep-learning-plan.json` before product-surface collection and
    includes `next_sweep_plan_path` in the chain summary. The same summary now
    exposes `product_surface_plan_summary`, including target count,
    learning-prioritized count, prioritized company/surface/url, priority, and
    learning reasons, so Hermes run consoles can explain why Argus inspected a
    product surface before Scout executes.
25. The daily runner merges that product-market chain summary back into the
    latest `reports.metadata.product_market_summary` row after the chain runs.
    The local admin app exposes it as
    `GET /api/tenants/{tenant}/argus/run-status` and renders a compact
    "Argus run console" section showing chain status, planned targets,
    learning-prioritized targets, Scout artifact count, runner verdict, and
    any run errors.
26. `DashboardState.product_market_run` now carries the same chain trace into
    the published dashboard JSON: chain status, next-sweep plan path, planned
    surface count, learning-prioritized count, prioritized targets, runner
    verdict, consumed learning ids, Scout artifact count, and errors. The
    cockpit renders this as a compact "Hermes / Argus run trace" in the
    evidence/source-health area so business users can see the operating proof
    behind the read.
27. `build_product_market_payload.py --learning-plan` copies approved
    next-sweep instructions into `ProductMarketRunPayload.learning_instructions`.
    The product-market runner now reports `learning_instruction_count` and
    `learning_instruction_improvement_ids`, so a run summary can prove which
    approved Argus learnings entered the intelligence pass.
28. Coverage-related recommendation challenges now classify as
    `coverage_recheck`. When such an approved instruction enters the
    product-market workflow, Argus preserves the pattern memory but demotes the
    run verdict to `watch` and does not persist actionable recommendations for
    that pass. This prevents a challenged source-coverage read from becoming a
    confident priority recommendation.
29. The synthesizer now treats product reality as first-class intelligence even
    when the conversation plane is quiet. Own release evidence plus rising
    demand creates a `product_without_market_conversation` PMM gap. Competitor
    release evidence plus rising demand and no own proof creates an
    `own_product_gap` Product audit, without requiring competitor narrative
    evidence.
30. `ProductMarketRunSummary` now includes a durable
    `intelligence_brief`: verdict, top insight, primary promoted action when
    one clears the gates, watchlist, evidence URLs, confidence limits, and next
    questions. This is the first brain-readable synthesis envelope Hermes can
    store, publish, and learn from. Counts prove plumbing ran; this brief
    carries what Argus actually learned and what would change the read.
31. The product-market runner persists that envelope to
    `product_market_run_intelligence` through
    `PgProductMarketRepository.save_run_intelligence_summary`. This turns the
    Argus read into append-only memory instead of transient stdout or dashboard
    metadata.
32. `PgProductMarketRepository.get_latest_run_intelligence` and the admin
    repository expose the latest persisted brain record to run-console
    consumers. The public dashboard can still render from report metadata, but
    operator surfaces now have a durable source of truth for "what did Argus
    actually learn in this run?"
33. `DashboardState.product_market_run_history` now exposes recent
    `product_market_run_intelligence` rows as a versioned dashboard contract.
    The cockpit timeline renders this as "Argus run reads", so the UI can show
    how Argus's conclusions changed over time instead of pretending today's
    read is the whole story.
34. The local admin/run-console API now exposes the same persisted run reads
    through `ArgusRunStatus.run_intelligence_history`, and the HTML run
    console renders an "Argus run reads" section. Operators can inspect what
    Hermes/Argus believed over recent runs without reading report metadata or
    public dashboard JSON by hand.
35. The daily dashboard publish gate now blocks public artifact publication
    when the product-market chain reports `failed` or
    `skipped_no_product_surface_outputs`. A disabled chain is still allowed
    for controlled legacy/flag-off runs, but a production launch-readiness run
    must enable the chain and produce Scout/product-surface outputs before the
    public dashboard can be trusted.
36. `deploy/cios-daily.sh` now behaves as a tested Hermes cron package wrapper:
    it can be pointed at arbitrary CI-OS app/public/env paths for validation,
    defaults `CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE=1`, clears stale run
    output before invoking `scripts/daily_production_run.py`, validates all
    required current-run artifacts before publish, and stages copies before
    replacing public `index.html`, `brief.html`, JSON, and competitor briefs.
37. `scripts/verify_hermes_package_contract.py` preflights a deployed CI-OS app
    before live acceptance. It fails fast when the package is missing the
    intelligence/admin brain modules, product-market runner entrypoints, the
    safe Hermes wrapper invariants, or deployed Python imports. This catches the
    exact class of drift where Hermes has a directory named `cios` but not the
    CI-OS package Argus actually needs.
37a. `scripts/audit_learning_policies.py` now gates approved CI-OS learning
    policies before Hermes schema or daily-run work starts. It recomputes each
    approved policy's stable action id, detects post-approval drift or invalid
    policy records, emits rollback guidance, and exits non-zero on unsafe
    policy state. `deploy/cios-daily.sh` runs it immediately after package
    preflight and before schema or dashboard work.
38. Raw GA / Looker page exports are normalized before they enter the demand
    plane. The importer accepts canonical rows with
    `topic, metric, value, change_pct, period_start, period_end, source_label,
    source_url`, and it also accepts common GA page rows such as
    `Page title, Page path, Engaged sessions, Engaged sessions previous
    period, Period start, Period end, Looker Studio URL`. The importer derives
    a capability topic, metric value, change percent, source URL, and evidence
    excerpt. Rows that cannot prove topic, metric, period, and evidence are
    dropped instead of becoming fake demand.
39. The daily runner now writes a demand export manifest before payload build:
    `looker-export-manifest.json` records discovered files, normalized files,
    raw rows, accepted rows, skipped rows, errors, and archive decisions. The
    payload builder receives normalized JSON files, not raw user exports, so
    the run status can distinguish "no demand export", "bad export", and
    "valid demand rows imported".
40. Auto-discovered tenant drop-folder exports are archived after successful
    product-market execution. Valid files move to `_archive/<timestamp>/`;
    empty or invalid files move to `_rejected/<timestamp>/`. Explicit
    `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS` paths are not moved.
41. The local-only admin app now exposes the demand import plane through
    `GET /api/tenants/{tenant}/argus/demand-imports` and
    `POST /api/tenants/{tenant}/argus/demand-imports`. Operators can inspect
    queued files, the latest `looker-export-manifest.json`, archive/rejection
    history, accepted suffixes, and manifest counts, and can safely queue CSV,
    JSON, or JSONL exports into `data/looker/<tenant>/` for the next Hermes
    sweep. Uploads reject path traversal and unsupported suffixes and remain
    behind the existing local-only/admin-token write boundary.
42. `scripts/verify_hermes_package_contract.py` now requires
    `src/cios/admin/demand_imports.py`, so a deployed package cannot pass the
    Hermes preflight while missing the inward-demand operator surface.
43. The local admin/run-console API now exposes the product muscle matrix
    through `GET /api/tenants/{tenant}/argus/feature-matrix`. The endpoint
    reads `company_feature_positions` joined to `feature_capabilities`, so
    operators can inspect which company has which capability, whether the row
    is proven/gap/disproven, what confidence was recorded, and which evidence
    URLs support the position.
44. The HTML admin page now renders "Product muscle matrix" above the registry
    controls. This makes the admin surface show not only who is monitored and
    what Hermes ran, but also what Scout/product-surface evidence says the
    market has actually shipped or documented.
45. `scripts/export_ga4_demand.py` is the first authenticated GA4 Data API
    connector boundary. When explicitly enabled and configured, Hermes can
    call it with a GA4 property id, current/previous date windows, dimensions,
    metric, and optional service-account credential path. It writes canonical
    demand rows that the existing Looker/GA normalizer can ingest. The Google
    client imports are lazy, so the CI-OS package can still be installed and
    tested without shipping Google credentials or analytics dependencies by
    default.
46. `daily_production_run.py` supports an env-gated
    `CIOS_GA4_EXPORT_ENABLED=1` step before product-market payload build. When
    disabled, no private analytics data is accessed. When enabled, the runner
    requires `CIOS_GA4_PROPERTY_ID`, `CIOS_GA4_CURRENT_START`,
    `CIOS_GA4_CURRENT_END`, `CIOS_GA4_PREVIOUS_START`, and
    `CIOS_GA4_PREVIOUS_END`; missing config fails the run instead of silently
    publishing a fake demand read. A successful export is appended to
    `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS`, so API-fetched demand and manual
    Looker files share the same normalization, manifest, archive, storage, and
    synthesis path.
47. The daily runner now derives product surfaces from the active DB source
    registry, not only from the hand-written `product_surfaces` seed block.
    Active source families `docs`, `documentation`, `changelog`,
    `release_notes`, `product`, `pricing`, `api_docs`, `api`, `integration`,
    `integrations`, and `marketplace` are promoted into `ProductSurfaceTarget`
    rows before the Scout plan is built. Conversation-only families such as
    blog, news, RSS, and forum remain outside the product muscle layer. This
    means a newly added competitor with an active docs/changelog/product source
    can enter the feature-matrix acquisition path without waiting for a second
    product-surface seed edit. Existing paused or retired product surfaces are
    still protected by `PgProductSurfaceRepository.upsert_seed_target`, which
    preserves operator lifecycle state on conflict.
48. The product-surface plan summary now records product-muscle coverage as a
    first-class run artifact: `target_company_count`, `target_companies`, and
    `surface_family_counts`. `DashboardState.product_market_run` publishes the
    same fields, and the cockpit run trace compares them with monitored
    competitors so the UI can say which monitored entities still need
    product-surface coverage. This keeps Argus from treating "33 Scout
    artifacts" as the same thing as complete product intelligence.
49. The daily runner now turns the product-muscle coverage gap into a
    machine-readable `product_muscle_gap_plan`. For every monitored competitor
    without product-surface coverage, the plan records the company, domain,
    active source count, and deterministic candidate discovery URLs for docs,
    changelog, product page, pricing, API docs, and integrations. These are
    candidate probes, not evidence claims. The plan is published in
    `DashboardState.product_market_run` and rendered in the cockpit run trace
    so Hermes knows what source discovery should investigate next.
50. `scripts/execute_product_muscle_gap_discovery.py` closes the next
    operational loop: it reads a bare gap plan or the published dashboard JSON,
    validates candidate URLs through the existing source validator boundary,
    and stores accepted URLs as `candidate` `product_surfaces`.
    `PgProductSurfaceRepository.upsert_candidate_target` preserves
    operator-paused and retired rows on conflict, so discovery can expand
    coverage without overriding human lifecycle decisions.
51. `scripts/promote_product_surface_candidates.py` lets Hermes or the run
    console promote validated product-muscle candidates into active Scout
    monitoring. Promotion only affects rows that are still `candidate`, came
    from the expected discovery source, and carry a 2xx validation status in
    metadata. The command records `promoted_by`, `promoted_at`, and
    `promotion_source`, and returns the promoted `ProductSurfaceTarget` rows
    so the next product-surface plan can inspect them.
52. `LearningApplyPlanner` turns ready next-sweep instructions into a gated
    `LearningApplyPlan`: CI-OS package-scoped actions, package policy/config
    targets, evidence ids, improvement ids, and explicit guards that no action
    touches Hermes core or bypasses human approval.
53. `scripts/build_learning_apply_plan.py` is the Hermes-callable artifact
    builder for that contract. It reads `next-sweep-learning-plan.json` and
    writes `learning-apply-plan.json`; it does not mutate source registries,
    scoring rules, taxonomy, prompts, or Hermes runtime state.
54. The daily product-market chain now runs a `learning_apply_plan` stage
    immediately after `next_sweep_learning_plan`. The run summary exposes
    `learning_apply_plan_path` plus action count, skipped count, target names,
    and package paths so run consoles can show what Argus learned should become
    durable package work.
55. The cockpit run trace and admin run console now surface the learning apply
    plan summary. Operators can see whether Argus only learned transiently or
    whether the run produced reviewed CI-OS package work candidates such as
    retry policy, evidence policy, source coverage policy, or scoring policy
    updates.
56. `LearningApplyExecutor` consumes `learning-apply-plan.json` inside the
    CI-OS package boundary. By default it writes review proposals only. With
    explicit human approval, it writes idempotent approved policy records under
    package-local `config/*policy.yaml` files and still refuses manual-review
    or non-config targets.
57. `scripts/execute_learning_apply_plan.py` is the Hermes-callable executor
    wrapper. Omit `--approved-by` for proposal-only review artifacts; provide
    `--approved-by <operator>` only after a human has approved the package
    policy update.
58. `build_next_sweep_learning_plan.py` now loads approved package policies
    from the installed CI-OS package and merges them into the next-sweep plan
    without duplicating matching DB-approved learning items. This is the first
    durable learning path: an approved Argus lesson can influence future
    Hermes sweeps even after the original queue item has been reviewed.
59. The local admin app now exposes the package learning apply state through
    `GET /api/tenants/{tenant}/argus/learning-apply` and an "Argus learning
    apply" HTML section. Operators can inspect pending proposal artifacts and
    approved package policies, including package path, target, approval state,
    evidence ids, and improvement ids, without opening files by hand.

## Demand Input Contract

Demand is the inward signal plane. It tells Argus what Algolia audiences are
actually engaging with, not what competitors are saying or shipping.

Accepted sources:

- Looker Studio / GA4 CSV, JSON, or JSONL exports.
- Canonical demand rows produced by `scripts/export_ga4_demand.py` from the
  GA4 Data API when `CIOS_GA4_EXPORT_ENABLED=1` is explicitly configured.
- Manual exports explicitly supplied through
  `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS`.
- Tenant drop-folder exports under
  `<installed-cios-app>/data/looker/<tenant-slug>/`, for example
  `/root/.hermes/apps/cios/data/looker/algolia/`.

Accepted canonical row fields:

- `topic`: capability, theme, search term, or page-derived subject.
- `metric`: normalized metric such as `engaged_sessions`, `active_users`,
  `views`, `sessions`, or `clicks`.
- `value`: current numeric value.
- `change_pct`: decimal percentage change, for example `0.5` for 50 percent.
- `period_start` and `period_end`: ISO timestamps or parseable dates.
- `source_label`: human-readable provenance, usually `Looker Studio GA4
  export`.
- `source_url`: report URL or local export provenance.
- `excerpt`: row-level evidence text.
- `source_file`: export file that supplied the row.
- `source_row_number`: one-based row number inside that export.
- `source_fingerprint`: stable SHA-256 fingerprint over the canonical demand
  evidence fields.

Accepted raw GA / Looker page fields:

- `Page title`
- `Page path`, `Landing page`, `Landing page + query string`, `URL`, or `Page
  location`
- One metric pair such as `Engaged sessions` plus `Engaged sessions previous
  period`
- `Period start` and `Period end`
- `Looker Studio URL`, `Looker URL`, or `Report URL`

Discovery controls:

- `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS`: platform-path-separated explicit file
  list.
- `CIOS_PRODUCT_MARKET_LOOKER_EXPORT_DIRS`: platform-path-separated explicit
  directory list.
- `CIOS_PRODUCT_MARKET_LOOKER_AUTO_DISCOVER`: defaults on. When enabled, the
  daily runner reads the tenant drop folder plus `data/looker/`.
- `CIOS_GA4_EXPORT_ENABLED`: defaults off. When set to `1`, the daily runner
  fetches GA4 demand rows before payload build.
- `CIOS_GA4_PROPERTY_ID`: GA4 property id, without the `properties/` prefix.
- `CIOS_GA4_CURRENT_START`, `CIOS_GA4_CURRENT_END`,
  `CIOS_GA4_PREVIOUS_START`, `CIOS_GA4_PREVIOUS_END`: current and comparison
  windows passed to the GA4 Data API.
- `CIOS_GA4_TOPIC_DIMENSION`: defaults to `pageTitle`.
- `CIOS_GA4_URL_DIMENSION`: defaults to `pagePath`.
- `CIOS_GA4_METRIC`: defaults to `engagedSessions`.
- `CIOS_GA4_CREDENTIALS_JSON`: optional service-account credential path. The
  value must live outside public/package artifacts and must never be printed.

No-fake-demand rule:

- If no Looker/GA exports exist, `demand_signals` remains empty.
- If demand is empty, Argus may still show product proof and conversation
  awareness, but it must not invent product-market patterns or confident
  recommendations that require audience demand.
- A quiet demand plane is a system limitation to surface, not a gap to hide.
- If a raw export is present but produces zero normalized rows, it is recorded
  in the manifest as `empty` and is not passed to synthesis.
- If an export cannot be parsed, it is recorded in the manifest as `error`;
  the system does not fabricate demand from a broken file.
- Canonical and raw GA / Looker rows are deduped by `source_fingerprint` before
  they reach synthesis. Re-running the same export must update/retain the same
  demand evidence, not inflate demand by inserting duplicate rows.
- The Postgres demand ledger stores the provenance object in
  `demand_signals.metadata`; the repository upserts by
  `metadata->>'source_fingerprint'` for the tenant.

Workflow:

1. `ProductMarketIntelligenceWorkflow` validates all inputs belong to the
   requested tenant.
2. It persists product events, conversation themes, and demand signals through
   the injected product-market ledger.
3. It derives feature matrix positions from product events and persists
   `feature_capabilities`, `company_feature_positions`, and
   `feature_evidence_links`.
4. It runs `ProductMarketSynthesizer`.
5. It persists `PatternObservation` rows and links `Recommendation` rows back
   to the saved pattern row when available.
6. User challenges to recommendations are recorded as
   `recommendation_challenge` learning events with one of these categories:
   `priority`, `evidence`, `scoring`, `coverage`, or `actionability`.
7. Coverage challenges are queued as critical because they may mean Argus
   missed the market. Scoring, evidence, and priority challenges are queued as
   high-priority improvement work and classify into `scoring_review`,
   `evidence_recheck`, or `priority_recheck` next-sweep instructions.
   Actionability challenges are medium and classify as
   `actionability_rewrite`.
8. Open learning items are visible in the admin queue and can be moved to
   approved or rejected. Approval is intentionally not mutation; approved rows
   become next-sweep instructions only when linked learning evidence exists.
9. Next-sweep learning plans are read-only artifacts. Hermes may consume them
   as run instructions, but durable source, scoring, taxonomy, prompt, or code
   changes still require a future gated apply path and must not touch Hermes
   core.
10. When `CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE=1`, the daily runner builds
    the next-sweep learning plan first, then plans product-surface exports,
    executes Scout, builds the product-market payload with `--learning-plan`,
    and runs synthesis.
11. Coverage recheck instructions influence product-surface planning before
    Scout executes. Matching targets are moved to the front of the export plan
    and annotated with `learning_priority` plus `learning_reasons`, so the run
    console can show why Hermes inspected a source first. This does not mutate
    `product_surfaces`; it only changes the next run's execution order.
12. After synthesis, the runner persists `ProductMarketRunSummary` to
    `product_market_run_intelligence`. This lets Hermes compare the latest run
    with prior runs, detect repeated confidence limits, and route future
    learning work from stored intelligence rather than from screen text.

Hermes-callable runner:

1. `scripts/run_product_market_intelligence.py` accepts a JSON payload with
   `scout_records`, `conversation_records`, and `looker_rows`.
2. Hermes can pass `--tenant <slug>` to resolve the tenant id from the DB, so
   collector payloads do not have to know internal DB ids.
3. The script writes no credentials and touches no Hermes core code.
4. It prints a machine-readable summary: verdict, product event count,
   conversation theme count, demand signal count, feature position count,
   pattern count, recommendation count, consumed learning ids, and the
   `intelligence_brief` synthesis envelope.
5. In the daily production chain, the product-market summary also includes
   `next_sweep_plan_path` and `product_surface_plan_summary`, making both the
   learning artifact and its planned product-surface effect visible to the run
   console and later dashboard/status consumers.
6. The local-only admin API exposes the latest persisted run status at
   `/api/tenants/{tenant}/argus/run-status`, sourced from
   `reports.metadata.product_market_summary`; this is the operator-readable
   proof of what Hermes ran and what the CI-OS package planned, not a separate
   mutable control plane.
7. The public dashboard state includes `product_market_run`, sourced from the
   current run dictionary during daily publish, so the cockpit can show the
   product-market execution trace alongside source-health evidence.
8. `ProductMarketRunSummary` includes the number of learning instructions and
   the improvement ids consumed from the learning plan. It also includes the
   `intelligence_brief`, so Hermes and the dashboard can inspect the actual
   read, proof, confidence limits, and next questions instead of inferring
   meaning from counts.
9. `coverage_recheck` gates action promotion until coverage has been
   re-audited, while retaining patterns for history and investigation.
10. `scoring_review`, `evidence_recheck`, and `priority_recheck` tighten the
   next run's action-promotion threshold. By default, recommendations below
   score 80 are withheld as `watch` even if patterns are persisted. A learning
   instruction may set `change.action_threshold` to a different integer, making
   the gate explicit and inspectable rather than hidden in a prompt.
11. `coverage_recheck` also feeds `plan_product_surface_exports.py
   --learning-plan`, so a challenge like "you missed Coveo" moves Coveo's
   product surfaces earlier in the Scout plan and carries the reason into the
   plan artifact.
12. The same run summary is saved to `product_market_run_intelligence`, making
    the brain-readable Argus read durable even if a later report render fails
    or report metadata is stale.
13. The dashboard publish gate treats the product-market run as part of the
    release contract. If the chain failed or produced no product-surface
    outputs, `scripts/daily_production_run.py` aborts publication with a
    diagnostic status instead of letting an older semantic pass produce a
    current-looking but hollow dashboard.
14. Hermes cron should invoke `deploy/cios-daily.sh`, not copy dashboard files
    itself. The wrapper is the package boundary: Hermes supplies scheduling and
    environment; CI-OS owns run execution, artifact validation, and public
    publish staging.
15. Before a live cron acceptance run, run
    `scripts/verify_hermes_package_contract.py --app-dir <installed-cios-app>`.
    A green local test suite is not enough when the live Hermes app directory
    may be stale.

Dashboard publish/read path:

1. `PgProductMarketRepository` reads current patterns, 30-day historical
   pattern memory, Argus recommendations, demand signals, and feature matrix
   rows.
2. `DashboardStateBuilder` emits them in `DashboardState`.
3. `scripts/daily_production_run.py` and `scripts/rerender_dashboard.py` both
   inject `PgProductMarketRepository`, so daily publish and state-first
   rerender use the same ledger.
4. `cockpit_renderer.py` now prefers structured product-market state for the
   semantic layer and falls back to keyword heuristics only when the ledger is
   empty.
5. `DashboardState.product_market_history` exposes historical
   `pattern_observations` for the last 30 days, and the cockpit timeline
   renders them as Product-market memory separate from report archives.
6. `DashboardState.product_market_trends` deterministically aggregates that
   memory by capability, counts 7D/30D patterns, labels direction as
   accelerating, sustained, emerging, or dormant, and carries deduped evidence
   references for the trend.
7. `DashboardState.product_market_heatmap` derives entity x capability heat
   cells from the same memory, with 7D/30D counts, heat level, intensity score,
   confidence, latest summary, and evidence references. This is the first real
   "who is doing what" heatmap contract.
8. `DashboardState.product_market_entity_velocity` rolls those heat cells up
   by entity, labeling each company as accelerating, sustained, emerging, or
   dormant, carrying top capabilities and proof links. The cockpit renders this
   above the heat map so users see who is moving before they inspect cells.
9. `DashboardState.product_market_theme_heatmap` rolls pattern memory up by
   strategic theme, with heat level, direction, intensity, leading entities,
   pattern types, and proof links. The cockpit renders this first in
   Product-market memory so users see what themes are heating up across the
   market before inspecting individual companies.
10. `DashboardState.product_market_window_deltas` compares the current
    seven-day window against the prior seven-day window for both themes and
    entities, labeling movement as new, rising, falling, flat, or inactive.
    The cockpit renders this as Window deltas between theme heat and entity
    velocity so users can see whether a pattern is actually heating up versus
    last week.
11. `DashboardState.argus_recommendations[].scorecard` publishes the backend
    recommendation rubric. The cockpit confidence panel now uses this saved
    scorecard when present and only falls back to the older source-health
    rubric for legacy payloads.
12. `DashboardState.product_market_run.intelligence_brief` preserves the same
    synthesis envelope from the runner summary, and the cockpit run trace
    renders "What Argus learned", promoted action when present, and the first
    confidence limit next to the Hermes/Argus execution proof.
13. The admin run status also exposes `latest_intelligence_brief` from
    `product_market_run_intelligence`, preferring the persisted brain record
    over report metadata when available.
14. `DashboardState.product_market_run_history` exposes the same durable run
    reads to published JSON (`schema_version` 16), and the cockpit renders
    them in the market timeline as a separate run-read lane next to pattern
    memory, theme heat, window deltas, and report history.
15. `GET /api/tenants/{tenant}/argus/run-status` returns
    `run_intelligence_history`, and the admin HTML renders those rows under
    "Argus run reads" in the run console. This makes the same durable Argus
    memory inspectable to Hermes operators before or after a dashboard publish.
16. `GET /api/tenants/{tenant}/argus/recommendations` returns the current
    Argus action ledger: owner, action, why-now, urgency, status, scorecard,
    evidence links, and created time. Operators no longer need to infer the
    action layer from public dashboard JSON or know recommendation ids by hand.
17. `POST /api/tenants/{tenant}/argus/recommendations/{id}/status` and the
    HTML "Argus action workbench" support accept, dismiss, and mark-done
    transitions for `argus_recommendations`. This closes the loop between
    "Argus recommends" and "the operator accepted, rejected, or completed the
    work."
18. The HTML action workbench also exposes per-recommendation challenge forms
    backed by the existing recommendation-challenge recorder, so weak reads can
    become learning events and next-sweep improvements from the same surface.
19. `GET /api/tenants/{tenant}/argus/evidence-ledger` returns the four data
    planes behind the brain: product proof, market conversation, audience
    demand, and pattern observations. The admin HTML renders this as "Argus
    evidence ledger" before the action workbench so operators can see why
    Argus is or is not allowed to recommend action.
20. The evidence-ledger surface includes truthful empty states for each plane.
    In particular, zero audience-demand rows is shown as an input gap, not a
    quiet-market conclusion.
21. `DashboardState.product_market_run` and admin `ArgusRunStatus` now expose
    the inward demand plane as first-class run metadata:
    `demand_plane_status`, Looker export discovery/ready/error counts,
    normalized/skipped row counts, archive count, and manifest path. The
    cockpit run trace and admin run console now say whether demand was
    missing, empty, errored, degraded, or processed instead of burying that
    fact inside a generic confidence note.
22. `ProductMarketIntelligenceBrief.demand_read` is the brain-readable demand
    thesis inside each run. It ranks rising audience-demand topics, shows
    whether each topic matched product proof and market conversation, carries
    source files, row numbers, and evidence URLs, and names the missing plane
    when a demand topic should become a product or narrative investigation
    instead of a recommendation.

## Next Build Slices

1. Product surface registry execution:
   - product-like active DB sources now auto-seed product surfaces for Scout,
     reducing dependence on the initial hand-written seed set.
   - expand source discovery so every monitored competitor has at least one
     high-quality docs/changelog/product/pricing/API/integration source where
     such a source publicly exists.
   - execute `plan_product_surface_exports.py`, then
     `execute_product_surface_plan.py`, then pass every successful
     `scout_paths[]` entry into `build_product_market_payload.py --scout`.

2. Looker/GA import execution:
   - current file importer accepts authorized Looker Studio / GA CSV, JSON,
     or JSONL exports, and the GA4 API connector can produce canonical demand
     rows for the same path when credentials/config are explicitly supplied.
   - the daily runner auto-discovers exports from the installed package's
     tenant drop folder, for example
     `/root/.hermes/apps/cios/data/looker/algolia/`, and passes each file to
     `build_product_market_payload.py --looker`.
   - remaining work: authorize and configure the real GA4 property/credential
     path in the Hermes environment, then run a live acceptance sweep with
     `CIOS_GA4_EXPORT_ENABLED=1`. Do not store credentials in the package
     folder or public dashboard artifacts.

3. Historical pattern memory expansion:
   - current dashboard state exposes 30-day stored pattern observations,
     first-pass capability trend direction, entity x capability heatmap cells,
     entity-level velocity summaries, theme-level market heat cells, and
     current-seven-day versus prior-seven-day deltas.
   - next expansion should add calendar controls backed by query parameters
     and comparison of this week's theme heat against broader prior windows
     such as prior month and quarter.

4. Hermes run wiring:
   - verify the real Hermes cron path is invoking `deploy/cios-daily.sh` with
     the intended app/public/env paths.
   - deploy/synchronize the local CI-OS package to the live Hermes app and run
     `scripts/verify_hermes_package_contract.py` on the VPS before the next
     acceptance run.
   - supply the real Looker/GA export paths through
     `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS` or enable the GA4 connector through
     the Hermes env-only `CIOS_GA4_*` settings.
   - verify source-derived product surfaces appear in the live product-surface
     plan for every monitored competitor with product-like sources.
   - use the published product-muscle coverage gap to drive the next source
     hunter pass: each monitored entity without a product-surface target needs
     an explicit source discovery outcome, such as active docs/changelog found,
     no public product surface found, blocked, needs credentials, or not
     applicable.
   - execute `product_muscle_gap_plan.missing_companies[].candidate_surface_urls`
     through the source validator or Scout discovery, then promote validated
     URLs to `sources` and `product_surfaces` with evidence-backed status.

5. Learning loop expansion:
   - current slice turns approved, evidence-linked improvements into a
     Hermes-readable next-sweep instruction plan, passes that plan into the
     product-market payload, reports consumed improvement ids, lets
     `coverage_recheck` instructions hold action recommendations at watch
     level, prioritizes matching product surfaces before Scout execution, and
     lets approved scoring/evidence/priority challenges tighten the next run's
     action-promotion threshold. The admin action workbench now lets operators
     inspect open recommendations, accept/dismiss/complete them, and challenge
     weak reads from the same surface.
   - current slice also emits `learning-apply-plan.json`, a package-scoped
     apply-plan artifact that names the CI-OS policy/config target for each
     approved learning instruction, keeps evidence/improvement traceability,
     requires human approval, explicitly refuses Hermes-core mutation, and is
     visible in both the cockpit run trace and the admin run console.
   - current slice adds the safe apply executor: proposal-only by default,
     package-local `config/*policy.yaml` writes only with explicit human
     approval, and next-sweep policy loading so approved lessons persist into
     future Hermes runs without touching Hermes core. The admin/run console
     now also surfaces pending proposals and approved package policies.
   - current slice adds local admin execution for the latest Hermes-recorded
     `learning_apply_plan_path`: proposal-only execution prepares review
     artifacts, and explicit `approved_by` execution writes approved CI-OS
     package policy records. The HTML form and JSON API both derive the plan
     path from the latest run status, not from caller-supplied file paths.
   - current slice adds approved-policy impact metadata to
     `next-sweep-learning-plan.json` and rolls it into the daily product-market
     run summary as `next_sweep_plan_summary`, including loaded, duplicate, and
     skipped policy counts plus policy source trace rows. This makes each
     Hermes/Argus run able to explain which package-approved lessons influenced
     the next sweep.
   - current slice adds rollback/drift checks for approved policy records:
     `scripts/audit_learning_policies.py` validates every package-local
     approved policy before live execution, reports drift or invalid records
     with rollback hints, and is enforced by the Hermes cron wrapper before
     schema, daily run, rerender, or publish work can proceed.
   - current slice wires the policy audit result into the local admin learning
     apply surface and API. Operators can see clean/drift/invalid policy counts,
     issue codes, action id mismatches, and rollback hints without reading cron
     logs.
   - remaining work: run the next live Hermes cron acceptance pass against the
     deployed package and publish only after the package preflight, learning
     policy audit, product-market chain, dashboard rerender, and click/data
     assertions all pass against production artifacts.
