# CI-OS Hermes Daily Live Repair - 2026-07-11

## Scope

Repair and validate the production CI-OS daily path as a Hermes-run extension
package, not a standalone app. The repair focused on making the data muscle and
brain real enough for the live dashboard to publish from a current run:

- Scout remains the acquisition layer.
- CI-OS/Argus owns product-change extraction and synthesis.
- Hermes owns scheduling and invokes `/root/.hermes/scripts/cios-daily.sh`.

## Production Release

Latest deployed app release:

- App path: `/root/.hermes/apps/cios`
- Wrapper: `/root/.hermes/scripts/cios-daily.sh`
- Latest release stamp: `20260711T043704Z`
- Backup: `/root/.hermes/backups/cios-app-20260711T043704Z`

Server env changes, without printing secret values:

- Added `SCOUT_API_KEY` to `/root/.hermes/cios-env` from the existing Scout
  container env so CI-OS can authenticate localhost Scout calls.
- Added `SCOUT_HTTP_BASE_URL=http://127.0.0.1:8421`.
- Added `GEMINI_API_KEY` to `/root/.hermes/cios-env` from Hermes root env so
  Argus/CI-OS can extract product-change rows without enabling LLM spend inside
  the public Scout service.

## Fixes Applied

- `scripts/scout_http_shim.py`
  - Sends `X-API-Key` from `SCOUT_HTTP_API_KEY` or `SCOUT_API_KEY`.
  - Supports `scrape` as an acquisition-only command against Scout `/scrape`.

- `scripts/export_product_surface_with_scout.py`
  - Keeps the existing Scout `extract` path.
  - Falls back when Scout reports no LLM key: scrape markdown via Scout, then
    use CI-OS/Argus Gemini extraction to produce normalized product rows.

- `scripts/apply_product_market_schema.py`
  - Adds an idempotent product-market schema applicator for live DBs created
    before the product-market tables existed.
  - Adds RLS/grants for product-market tables.

- `deploy/cios-daily.sh`
  - Runs package preflight.
  - Applies product-market schema.
  - Runs the daily production job.
  - Publishes only current-run artifacts after artifact validation.

- `scripts/execute_product_surface_plan.py`
  - Treats partial product-surface failures as degraded but usable when at
    least one surface succeeds.
  - Zero successful surface exports remains a hard failure.
  - Supports bounded parallel export execution via `--max-workers`.

- `deploy/cios-daily.sh`
  - Defaults `CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS=3` so the product-market
    muscle is cron-safe and no longer fully serial.

- `scripts/daily_production_run.py`
  - Fixes report metadata merge with `metadata = metadata || %s::jsonb`.

## Live Hermes Run Evidence

Command:

```bash
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh
```

Result:

```text
algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=2
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 323.7s. LLM calls used: 2 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live artifact check:

```text
https://ci.chowmes.com/ 200 337860 text/html
https://ci.chowmes.com/data/semantic-dashboard.json 200 75076 application/json
generated_at=2026-07-11T04:30:38.596032Z
competitors=27
source_health=48
briefs=27
```

Follow-up bounded-parallel live run after release `20260711T043704Z`:

```text
algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=2
Run complete in 175.0s. LLM calls used: 2 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
product_surface_summary={"planned":22,"succeeded":20,"failed":2,"max_workers":3}
generated_at=2026-07-11T04:41:20.130696Z
competitors=27
source_health=48
briefs=27
```

Playwright live UI click validation:

```text
PASS structure
PASS nav_targets
PASS timeline
PASS semantic_layer
PASS priority_selection
PASS brief_routing
PASS appendices
PASS viewport_390
PASS viewport_768
PASS viewport_1280
PASS dashboard_click_validation
```

## Cockpit Intelligence Spine UI

Problem addressed:

- The dashboard JSON exposed `intelligence_spine`, but the cockpit still made
  operators infer the brain from scattered product-market sections.
- The screen needed a visible proof chain showing what Argus knows from product
  reality, market conversation, and audience demand before asking a user to
  trust recommendations or blocked-action states.

Package-layer changes:

- `src/cios/dashboard/cockpit_renderer.py`
  - Adds a visible `#intelligence-spine` section directly after Today's read.
  - Adds a `Proof` top-nav target and deep-link handling.
  - Renders evidence planes, actionability, blocked actions, leading entities
    and capabilities, and the next operator action from
    `DashboardState.intelligence_spine`.
- `tests/dashboard/test_cockpit_renderer.py`
  - Adds renderer coverage that the proof chain appears in static HTML.
  - Extends the nav/order contract so Proof sits between Today and Timeline.
- `scripts/validate_dashboard_clicks.py`
  - Adds live E2E checks for the Proof nav target and responsive presence of
    `#intelligence-spine`.
- `docs/workspace/cios-dashboard-intelligence-spine-ui/`
  - Records frontend design thinking, constraints, and local evidence.

Local TDD evidence:

```text
python3 -m pytest tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_intelligence_spine_as_argus_proof_chain -q --tb=short
1 failed before implementation:
- id="intelligence-spine" was not rendered.

python3 -m pytest tests/dashboard/test_cockpit_renderer.py::test_quiet_current_run_does_not_label_rolling_cards_as_todays_moves tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_intelligence_spine_as_argus_proof_chain -q --tb=short
2 passed in 0.11s

python3 -m pytest tests/dashboard/test_cockpit_renderer.py -q --tb=short
23 passed in 0.13s

python3 -m pytest tests/scripts/test_product_market_dashboard_wiring.py tests/dashboard/test_publisher.py tests/dashboard/test_state_builder.py -q --tb=short
60 passed in 0.49s

python3 -m pytest tests/dashboard -q --tb=short
122 passed in 0.39s

python3 -m pytest -q --tb=short
803 passed, 21 deselected in 5.68s

python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied
```

## Dashboard Operator Handoff Publish

Problem addressed:

- Hermes produced an `argus-operator-handoff.json` artifact, but the public
  dashboard JSON and HTML were rendered before that artifact existed. The UI
  could still look like an empty shell because the operating verdict was not
  visible to the reader.

Package-layer changes:

- `src/cios/dashboard/types.py`
  - Added `DashboardOperatorHandoff` and `DashboardOperatorCommand`.
  - Added `DashboardState.operator_handoff`.
- `src/cios/dashboard/cockpit_renderer.py`
  - Renders an `Argus operator handoff` block inside the proof-chain section.
  - Shows readiness, blocker, next operator action, queue count, and command
    label.
  - Does not expose internal admin/API command hrefs in public HTML.
- `scripts/attach_operator_handoff_to_dashboard.py`
  - Reads `argus-dashboard.json` and `argus-operator-handoff.json`.
  - Validates tenant alignment.
  - Rewrites dashboard JSON and re-renders dashboard HTML from typed state.
- `deploy/cios-daily.sh`
  - Runs the attach command after handoff build and before public publish.
- `scripts/verify_hermes_package_contract.py`
  - Requires the attach script and wrapper call.

Local verification:

```text
pytest tests/dashboard/test_cockpit_renderer.py tests/scripts/test_attach_operator_handoff_to_dashboard.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q
54 passed in 4.79s

bash -n deploy/cios-daily.sh

python3 -m py_compile scripts/attach_operator_handoff_to_dashboard.py src/cios/dashboard/types.py src/cios/dashboard/cockpit_renderer.py scripts/verify_hermes_package_contract.py

pytest -q
870 passed, 21 deselected in 9.93s
```

Remote deployment and verification:

```text
backup=/root/.hermes/apps/cios/.codex-backups/operator-handoff-20260711-164234
deployed_operator_handoff_slice=ok

bash -n deploy/cios-daily.sh
PYTHONPYCACHEPREFIX=/tmp/cios-pycache-operator-handoff .venv/bin/python -m py_compile scripts/attach_operator_handoff_to_dashboard.py src/cios/dashboard/types.py src/cios/dashboard/cockpit_renderer.py scripts/verify_hermes_package_contract.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_operator_handoff_as_public_actionability_contract tests/scripts/test_attach_operator_handoff_to_dashboard.py tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_builds_argus_operator_handoff_from_evidence_queue_before_publish tests/scripts/test_verify_hermes_package_contract.py::test_preflight_passes_complete_hermes_package_contract -q -p no:cacheprovider
6 passed in 0.87s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
863 passed, 1 skipped, 21 deselected, 1 warning in 8.93s
```

Live wrapper evidence:

```text
PASS: CI-OS Hermes package contract satisfied
algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=10
Run complete in 638.3s. LLM calls used: 10 / 35
attached operator handoff to dashboard for tenant_id=1
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live public smoke:

```text
json_schema_version 17
generated_at 2026-07-11T20:54:07.482240Z
operator_handoff_status blocked_on_evidence
operator_handoff_readiness not_actionable
operator_handoff_artifact_found True
operator_handoff_next_action Upload GA4 / Looker demand export for the current and previous periods.
operator_handoff_top_blocker argus-evidence:19:demand
html_has_operator_handoff True
html_has_status True
html_leaks_primary_href False
html_size 358293
```

## Demand Intake Wrapper Contract - 2026-07-12

Problem addressed:

- The data-plane manifest could consume a demand-intake artifact, but the live
  Hermes daily wrapper did not yet guarantee that every daily run produced that
  sidecar and passed it into the manifest.
- A failed demand import could still inherit a non-blocking readiness state if
  no explicit evidence work queue existed.

Package-layer changes:

- `deploy/cios-daily.sh`
  - Runs `scripts/run_argus_demand_intake.py` on both successful and blocked
    daily-run paths.
  - Requires `out/argus-demand-intake.json` from the current run.
  - Tolerates the demand-intake command returning non-zero when the sidecar
    artifact exists.
  - Passes `--demand-intake "$OUT/argus-demand-intake.json"` into
    `scripts/export_argus_data_plane_manifest.py`.
- `scripts/verify_hermes_package_contract.py`
  - Rejects wrappers missing the demand-intake coordinator.
  - Rejects wrappers missing the `--demand-intake` manifest input.
- `scripts/export_argus_data_plane_manifest.py`
  - Treats failed or queued demand-intake states with no demand signals as
    action blockers.

Local verification:

```text
bash -n deploy/cios-daily.sh

.venv/bin/pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_export_argus_data_plane_manifest.py -q
49 passed in 6.87s

.venv/bin/pytest -q
1020 passed, 22 deselected, 1 warning in 12.20s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment:

```text
Synced:
- deploy/cios-daily.sh
- scripts/export_argus_data_plane_manifest.py
- scripts/verify_hermes_package_contract.py
- tests/deploy/test_cios_daily_wrapper.py
- tests/scripts/test_export_argus_data_plane_manifest.py
- tests/scripts/test_verify_hermes_package_contract.py

Package path: /root/.hermes/apps/cios
Cron wrapper: /root/.hermes/scripts/cios-daily.sh
```

Remote verification:

```text
bash -n deploy/cios-daily.sh
bash -n /root/.hermes/scripts/cios-daily.sh

.venv/bin/pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_export_argus_data_plane_manifest.py -q
49 passed in 2.61s

.venv/bin/pytest -q
1019 passed, 1 skipped, 22 deselected, 1 warning in 13.03s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Live wrapper smoke:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=10
ABORT: dashboard publish blocked for algolia; quality_status=passed; synth_verdict=quiet
demand_source_status=missing; ga4_export_status=skipped_disabled; looker_ready_count=0; ledger_demand_signal_count=0
```

Live artifact check:

```text
artifact=out/argus-demand-intake.json size=3223
artifact=out/argus-demand-readiness.json size=2786
artifact=out/argus-data-plane-manifest.json size=13003
artifact=out/argus-dashboard.json size=529764
artifact=out/argus-dashboard.html size=390772
artifact=out/brief.html size=57644

manifest_status=blocked_on_evidence
manifest_next=configure_ga4_or_upload_demand_export
manifest_demand_status=blocked_missing_demand_source
manifest_demand_blocks=True
manifest_demand_intake_status=blocked_missing_demand_source
intake_status=blocked_missing_demand_source
intake_exit_code=2
intake_next=configure_ga4_or_upload_demand_export
dashboard_targets=38
dashboard_product_events=500
dashboard_demand_signals=0
```

Interpretation:

- The deployment is verified.
- The live wrapper now exercises the outward-monitoring, product-muscle, demand
  readiness, demand-intake, operator-handoff, and manifest path.
- The current production run is intentionally blocked from action because no
  GA4/Looker demand source is configured or uploaded. The system is now honest
  about that blocker instead of letting the UI imply intelligence confidence
  without inward-demand evidence.

## Demand Plane Operator Commands In Manifest - 2026-07-12

Problem addressed:

- The data-plane manifest could name the missing demand plane and next Hermes
  action, but it did not carry the concrete operator commands from demand
  readiness.
- Raw admin/API hrefs should not be copied into the public-safe manifest data.

Package-layer changes:

- `scripts/export_argus_data_plane_manifest.py`
  - Adds sanitized demand-plane `operator_commands`.
  - Preserves command label, surface, method, and route kind.
  - Strips raw `href` values from the manifest payload.
  - Adds the sanitized commands to demand blockers, so the blocker itself can
    drive the operator action.

Local verification:

```text
.venv/bin/pytest tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_exposes_sanitized_demand_operator_commands_without_admin_hrefs -q
1 failed before implementation: KeyError: 'operator_commands'

.venv/bin/pytest tests/scripts/test_export_argus_data_plane_manifest.py -q
7 passed

.venv/bin/pytest tests/scripts/test_export_argus_data_plane_manifest.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q
50 passed

python3 -m py_compile scripts/export_argus_data_plane_manifest.py

.venv/bin/pytest -q
1021 passed, 22 deselected, 1 warning
```

Remote verification:

```text
PYTHONPYCACHEPREFIX=/tmp/cios-pycache-manifest-commands .venv/bin/python -m py_compile scripts/export_argus_data_plane_manifest.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest tests/scripts/test_export_argus_data_plane_manifest.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q -p no:cacheprovider
50 passed

PYTHONDONTWRITEBYTECODE=1 .venv/bin/pytest -q --tb=short -p no:cacheprovider
1020 passed, 1 skipped, 22 deselected, 1 warning

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Live artifact check after regenerating the manifest from current production
sidecars:

```text
manifest_status=blocked_on_evidence
next_hermes_action=configure_ga4_or_upload_demand_export
demand_status=blocked_missing_demand_source
demand_blocks=True
operator_command_count=3
command_1={"label": "Download demand template", "method": "get", "route_kind": "api", "surface": "Demand imports"}
command_2={"label": "Open demand admin", "method": "get", "route_kind": "admin", "surface": "Admin"}
command_3={"label": "Run GA4 export now", "method": "post", "route_kind": "admin", "surface": "GA4 connector"}
commands_have_href=False
first_blocker_has_commands=True
```

## Product-Surface Repair Runner

Problem addressed:

- The product-muscle queue could classify live surface-export failures, but the
  system still left Hermes/Argus with a passive instruction instead of a
  bounded executable repair step.
- Live artifacts had failed product surfaces for Coveo and Meilisearch, but no
  package-owned runner to retry one failed surface safely, isolate repair
  output, and report whether the issue was extraction settings or a source that
  needs replacement.

Package-layer changes:

- `scripts/run_product_surface_repair.py`
  - Reads `product-surface-plan.json` and
    `product-surface-execution-summary.json`.
  - Selects failed items by company, company id, surface id, and failure
    category.
  - Rewrites the retry command with a repair output path, higher extraction
    timeout, and optional `--js`.
  - Executes only the bounded selected items.
  - Writes a repair summary with selected, succeeded, failed, row count,
    original output path, repair output path, command, category, and concise
    error.
  - Returns `2` when there is no matching failed surface, `1` when selected
    repairs fail, and `0` when at least one selected repair succeeds.
- `scripts/verify_hermes_package_contract.py`
  - Requires `scripts/run_product_surface_repair.py`, so a deployed CI-OS
    package cannot pass preflight while missing the repair runner.

Local TDD evidence:

```text
.venv/bin/pytest tests/scripts/test_run_product_surface_repair.py -q
3 failed before implementation:
- FileNotFoundError for scripts/run_product_surface_repair.py.

.venv/bin/pytest tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_product_surface_repair_runner_missing -q
1 failed before verifier wiring:
- preflight still passed when the repair runner was missing.

.venv/bin/pytest tests/scripts/test_run_product_surface_repair.py tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_product_surface_repair_runner_missing tests/scripts/test_verify_hermes_package_contract.py::test_preflight_passes_complete_hermes_package_contract -q
5 passed in 0.15s

.venv/bin/pytest tests/scripts/test_run_product_surface_repair.py tests/scripts/test_verify_hermes_package_contract.py tests/admin/test_product_muscle_work_queue.py tests/scripts/test_export_product_surface_with_scout.py tests/scripts/test_execute_product_surface_plan.py -q
42 passed in 2.33s

.venv/bin/pytest -q --tb=short
1003 passed, 22 deselected, 1 warning in 11.92s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-product-surface-repair-20260712T080502Z.tgz
deployed_product_surface_repair_runner=ok
-rwxr-xr-x 1 root root 11832 Jul 12 04:02 /root/.hermes/apps/cios/scripts/run_product_surface_repair.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/scripts/test_run_product_surface_repair.py tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_product_surface_repair_runner_missing tests/scripts/test_verify_hermes_package_contract.py::test_preflight_passes_complete_hermes_package_contract -q -p no:cacheprovider
5 passed in 0.28s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
1002 passed, 1 skipped, 22 deselected, 1 warning in 10.40s
```

Live artifact inspection before repair:

```text
plan_exists True summary_exists True
plan_items 38 summary {'planned': 38, 'succeeded': 34, 'failed': 4, 'max_workers': 3}
FAILED surface_id 10 company Coveo family pricing url https://www.coveo.com/en/pricing error RuntimeError: Scout product surface scrape returned no markdown
FAILED surface_id 11 company Coveo family product_page url https://www.coveo.com/en/platform error RuntimeError: Scout product surface scrape returned no markdown
FAILED surface_id 136 company Coveo family product_page url https://www.coveo.com/en/solutions/commerce error RuntimeError: Scout product surface scrape returned no markdown
FAILED surface_id 146 company Meilisearch family changelog url https://github.com/meilisearch/meilisearch/releases error timed out after 120.0 seconds
```

Live bounded repair trial:

```text
repair_rc=1
repair_summary=/tmp/cios-product-market/algolia/product-surface-repairs/20260712T080609Z/repair-summary.json
status failed selected 1 succeeded 0 failed 1
result failed company Coveo surface 10 category no_markdown rows 0 error For more information check: https://developer.mozilla.org/en-US/docs/Web/HTTP/Status/403
output_path /tmp/cios-product-market/algolia/product-surface-repairs/20260712T080609Z/000010-coveo-pricing.repair.json
```

Interpretation:

- The repair runner is now real, deployed, package-required, and verified.
- The specific Coveo retry did not produce product rows. It converted the vague
  no-markdown failure into a concrete HTTP 403 source problem. The next
  operator action is not "rerun harder"; it is to replace or supplement the
  Coveo pricing/product sources with crawlable docs, changelog, release-note,
  API, or integration surfaces.
- This is one small but real layer of muscle: Hermes can now execute a bounded
  repair loop and record the result instead of leaving Argus with a static
  failure label.

## Product-Surface Repair Admin Action

Problem addressed:

- The repair runner existed as a package CLI, but the local admin/run-console
  surface still did not expose it. Operators could see a classified
  product-surface failure, but the next action still behaved like a static
  source-editing task.

Package-layer changes:

- `src/cios/admin/product_surface_repair.py`
  - Adds `ProductSurfaceRepairControl`, a local admin wrapper around
    `scripts/run_product_surface_repair.py`.
  - Reads the same Hermes product-market artifacts under
    `/tmp/cios-product-market/<tenant>/`.
  - Runs the repair script with bounded company/surface/category filters and
    returns the repair summary.
- `src/cios/admin/app.py`
  - Adds `POST /api/tenants/{tenant}/argus/product-surface-repair`.
  - Adds `POST /admin/{tenant}/argus/product-surface-repair`.
  - Keeps the control dependency-injected for tests and local-only operation.
- `src/cios/admin/product_muscle_work_queue.py`
  - Turns classified failed surface exports into a primary `Run repair retry`
    action.
  - Keeps `Open product surfaces` as the secondary source-replacement path.
- `src/cios/admin/types.py`
  - Adds `ProductSurfaceRepairRequest`.
- `scripts/verify_hermes_package_contract.py`
  - Requires the admin repair control in addition to the repair runner.

Local TDD evidence:

```text
.venv/bin/pytest tests/admin/test_product_muscle_work_queue.py::test_product_muscle_queue_limits_confidence_when_surfaces_have_no_extracted_feature_evidence tests/admin/test_product_muscle_work_queue.py::test_product_muscle_queue_classifies_timeout_surface_failures -q
2 failed before queue action wiring:
- expected "Run repair retry", got "Open product surfaces".

.venv/bin/pytest tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs tests/admin/test_app.py::test_admin_form_runs_product_surface_repair_and_redirects tests/admin/test_app.py::test_admin_html_shows_product_surface_repair_action_for_classified_failures -q
3 failed before app wiring:
- create_app() got an unexpected keyword argument product_surface_repair_control.

.venv/bin/pytest tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_product_surface_repair_admin_control_missing -q
1 failed before preflight wiring:
- preflight still passed when src/cios/admin/product_surface_repair.py was missing.

.venv/bin/pytest tests/admin/test_product_muscle_work_queue.py tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs tests/admin/test_app.py::test_admin_form_runs_product_surface_repair_and_redirects tests/admin/test_app.py::test_admin_html_shows_product_surface_repair_action_for_classified_failures tests/scripts/test_run_product_surface_repair.py tests/scripts/test_verify_hermes_package_contract.py -q
39 passed, 1 warning

.venv/bin/pytest tests/admin -q
87 passed, 1 warning

.venv/bin/pytest -q --tb=short
1007 passed, 22 deselected, 1 warning in 11.99s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-admin-product-surface-repair-20260712T081514Z.tgz
deployed_admin_product_surface_repair=ok

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin/test_product_muscle_work_queue.py tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs tests/admin/test_app.py::test_admin_form_runs_product_surface_repair_and_redirects tests/admin/test_app.py::test_admin_html_shows_product_surface_repair_action_for_classified_failures tests/scripts/test_run_product_surface_repair.py tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_product_surface_repair_admin_control_missing tests/scripts/test_verify_hermes_package_contract.py::test_preflight_passes_complete_hermes_package_contract -q -p no:cacheprovider
13 passed, 1 warning

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

systemctl restart cios-admin
systemctl is-active cios-admin
active
PrivateTmp=no
NoNewPrivileges=yes
curl -fsS http://127.0.0.1:8765/health
{"status":"ok"}

html_has_product_surface_repair True
html_has_repair_action True
html_has_product_muscle_queue True

api_status_code 200
api_repair_status no_matching_failed_surface selected 0 command_status failed returncode 2

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
1006 passed, 1 skipped, 22 deselected, 1 warning in 11.99s
```

Interpretation:

- The repair loop is now visible and executable from the local admin operating
  surface, not just available as an internal script.
- A classified failure in the product-muscle work queue now has a concrete
  `Run repair retry` action. If the retry still fails, the operator has a
  source-replacement path directly beside it.
- This still does not make bad external sources good. It makes the system
  operationally honest: Hermes can attempt the bounded repair, persist the
  result, and show whether the issue is extraction settings or source
  accessibility.

## Product-Surface Repair To Argus Refresh

Problem addressed:

- A successful product-surface repair could still become an orphaned JSON file
  under the repair directory. The repair action needed to feed successful
  `scout_paths` back through the existing product-market runner so repaired
  product proof updates the evidence ledger and Argus read.

Package-layer changes:

- `src/cios/admin/app.py`
  - Adds a dependency-injected product-surface repair refresh runner.
  - Default runner calls `build_payload_from_exports(...)` with successful
    repair `scout_paths`, then calls `run_product_market_payload(...)` with
    `PgProductMarketRepository`.
  - `POST /api/tenants/{tenant}/argus/product-surface-repair` now returns:
    repair summary, `argus_refresh`, and `argus_read`.
  - If no repair output succeeded, `argus_refresh` and `argus_read` remain
    `None`; the failed repair summary is still returned.
  - The HTML form path uses the same repair-and-refresh action.

Local TDD evidence:

```text
.venv/bin/pytest tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs tests/admin/test_app.py::test_json_api_skips_argus_refresh_when_product_surface_repair_has_no_successful_paths -q
2 failed before app wiring:
- create_app() got an unexpected keyword argument product_surface_repair_refresh_runner.

.venv/bin/pytest tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs tests/admin/test_app.py::test_json_api_skips_argus_refresh_when_product_surface_repair_has_no_successful_paths -q
2 passed, 1 warning

.venv/bin/pytest tests/admin -q
88 passed, 1 warning

.venv/bin/pytest -q --tb=short
1008 passed, 22 deselected, 1 warning in 12.10s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-admin-repair-refresh-20260712T082133Z.tgz
deployed_admin_repair_refresh=ok

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs tests/admin/test_app.py::test_json_api_skips_argus_refresh_when_product_surface_repair_has_no_successful_paths tests/admin/test_app.py::test_admin_form_runs_product_surface_repair_and_redirects -q -p no:cacheprovider
3 passed, 1 warning

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

systemctl restart cios-admin
systemctl is-active cios-admin
active
curl -fsS http://127.0.0.1:8765/health
{"status":"ok"}

api_status_code 200
repair_status no_matching_failed_surface selected 0 argus_refresh None argus_read None

PrivateTmp=no
NoNewPrivileges=yes

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
1007 passed, 1 skipped, 22 deselected, 1 warning in 11.55s
```

Interpretation:

- The repair loop now has a full path from failed product-surface extraction to
  repaired Scout rows to product-market persistence/synthesis to refreshed
  Argus read.
- The live no-match smoke used a deliberately non-matching company, so it did
  not mutate the product ledger. It proved the deployed route and the
  no-success branch without adding fake evidence.
- The next useful step is dashboard/run-console visibility for the latest
  repair summary, so operators can see the result of the last repair attempt
  without opening `/tmp` artifacts.

## Product Muscle Surface Dedupe Repair - 2026-07-12

Problem addressed:

- Product-muscle gap discovery was using the generic `sources` registry as the
  duplicate gate. That meant a URL already monitored by Hermes could be
  rejected before becoming a first-class `product_surfaces` target for Scout
  product/changelog/docs extraction.
- The correct duplicate boundary for product-muscle discovery is
  `product_surfaces`, not generic monitored sources. A source URL can already
  exist in daily monitoring and still need promotion into the product-muscle
  matrix.

Package-layer changes:

- `scripts/execute_product_muscle_gap_discovery.py`
  - Reuses one `PgProductSurfaceRepository` instance for product-surface
    writes and duplicate checks.
  - Stops checking `PgSourceRepository` for product-muscle candidate
    duplicates.
- `src/cios/db/repos/product_surfaces.py`
  - Adds `get_by_normalized_url(tenant_id, normalized_url)` for product-surface
    scoped dedupe.
- `tests/scripts/test_execute_product_muscle_gap_discovery.py`
  - Adds regression coverage proving a generic source duplicate does not block
    product-surface candidate storage when the product-surface table has no
    matching row.
- `tests/db/test_product_surface_repo.py`
  - Adds repository coverage for product-surface normalized URL lookup.

TDD evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py::test_execute_product_muscle_gap_discovery_dedupes_against_product_surfaces_not_generic_sources -q
1 failed before implementation:
assert summary["validated_count"] == 1
E assert 0 == 1
Captured summary: duplicate_source_count=1, reason=duplicate_normalized_url

.venv/bin/python -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py::test_execute_product_muscle_gap_discovery_dedupes_against_product_surfaces_not_generic_sources tests/db/test_product_surface_repo.py::test_get_by_normalized_url_dedupes_against_product_surfaces_only -q
2 passed in 0.28s

.venv/bin/python -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py tests/intelligence/test_product_muscle_gap_discovery.py tests/deploy/test_cios_daily_wrapper.py -q
28 passed in 5.73s

.venv/bin/python -m pytest -q
988 passed, 22 deselected, 1 warning in 10.76s
```

Remote deployment:

```text
backup_dir=/root/.hermes/apps/cios/backups/codex-product-surface-dedupe-20260712T065215Z
deployed:
- scripts/execute_product_muscle_gap_discovery.py
- src/cios/db/repos/product_surfaces.py
- tests/scripts/test_execute_product_muscle_gap_discovery.py
- tests/db/test_product_surface_repo.py
```

Remote verification:

```text
.venv/bin/python -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py tests/intelligence/test_product_muscle_gap_discovery.py tests/deploy/test_cios_daily_wrapper.py -q
28 passed in 1.37s

.venv/bin/python -m pytest -q
987 passed, 1 skipped, 22 deselected, 1 warning in 10.75s
```

Live DB and artifact evidence after deployment:

```text
product_surface_counts:
- active: 38

active_product_surfaces_by_family:
- changelog: 5
- docs: 14
- pricing: 7
- product_page: 12

product-market payload:
- scout_records: 26
- conversation_records: 80
- looker_rows: 0

product-surface execution:
- planned: 38
- succeeded: 34
- failed: 4
- scout_paths_count: 34

dashboard projection:
- generated_at: 2026-07-12T07:07:47.006105Z
- product_market_status: ran
- target_count: 38
- scout_artifact_count: 34
- product_event_count: 500
- pattern_count: 2
- recommendation_count: 0
- demand_signal_count: 0
- runner_verdict: watch
```

Live Hermes wrapper evidence:

```text
timeout 900 /root/.hermes/scripts/cios-daily.sh
wrapper_rc=2

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=5

CIOS_PRODUCT_MARKET_STAGE next_sweep_learning_plan done elapsed_s=0.353
CIOS_PRODUCT_MARKET_STAGE learning_apply_plan done elapsed_s=0.209
CIOS_PRODUCT_MARKET_STAGE learning_apply_execute done elapsed_s=0.192
CIOS_PRODUCT_MARKET_STAGE product_surface_plan done elapsed_s=0.36
CIOS_PRODUCT_MARKET_STAGE product_surface_export done elapsed_s=212.102
CIOS_PRODUCT_MARKET_STAGE demand_export done elapsed_s=0.0
CIOS_PRODUCT_MARKET_STAGE looker_prepare done elapsed_s=0.0
CIOS_PRODUCT_MARKET_STAGE product_market_payload done elapsed_s=0.208
CIOS_PRODUCT_MARKET_STAGE product_market_synthesis done elapsed_s=0.594
CIOS_PRODUCT_MARKET_STAGE product_market_ledger_refresh done elapsed_s=0.514
CIOS_PRODUCT_MARKET_STAGE looker_archive done elapsed_s=0.0

ABORT: dashboard publish blocked for algolia; quality_status=passed; synth_verdict=signals
demand_source_status=missing; ga4_export_status=skipped_disabled; looker_ready_count=0; ledger_demand_signal_count=0
attached post-run summaries to /root/.hermes/apps/cios/out/argus-dashboard.json
re-rendered cockpit 392729 bytes from live DB state
attached operator handoff to dashboard for tenant_id=1
daily production runner exited with 2; demand source gate exited with 2
```

Post-run process check:

```text
No lingering cios-daily, daily_production_run, execute_product_surface_plan,
export_product_surface_with_scout, run_product_market, or
execute_product_muscle_gap_discovery processes remained after wrapper exit.
```

Current blocker:

- Product-surface acquisition and product-market synthesis are executing.
- Daily source coverage is broad: 48 active sources attempted, 43 fetched, 5
  failed; the failed set is currently Coveo pages returning empty HTTP 202
  responses.
- The production publish gate still exits `2` by design because tenant-side
  demand evidence is missing: GA4 export is disabled, no Looker-ready file was
  available, and ledger demand signal count is `0`.
- Next system work should wire the demand plane: configure GA4 service
  credentials or upload a Looker export into the ready intake path, then rerun
  the wrapper until the demand gate clears or fails with a more specific
  ingestion error.

## Product Muscle Summary Label Cleanup - 2026-07-12

Problem addressed:

- After product-muscle dedupe was corrected to use `product_surfaces`, the
  sidecar summary still reported duplicates as `duplicate_source_count`.
- That label was misleading because the duplicates are now product-surface
  duplicates, not generic monitored source duplicates.

Package-layer changes:

- `src/cios/intelligence/product_muscle_gap_discovery.py`
  - Emits `duplicate_product_surface_count`.
  - Keeps `duplicate_source_count` as a backward-compatible alias for older
    dashboard readers and historical artifacts.
- `scripts/attach_post_run_summaries.py`
  - Prefers `duplicate_product_surface_count`.
  - Falls back to legacy `duplicate_source_count`.

TDD and verification:

```text
red test:
tests/intelligence/test_product_muscle_gap_discovery.py::test_execute_product_muscle_gap_discovery_separates_duplicates_from_new_candidate_failures
KeyError: 'duplicate_product_surface_count'

focused local:
9 passed in 0.32s

affected local:
99 passed in 0.53s

full local:
988 passed, 22 deselected, 1 warning in 11.22s

remote targeted:
99 passed in 0.83s

remote full:
987 passed, 1 skipped, 22 deselected, 1 warning in 10.35s
```

Live sidecar verification:

```text
status=completed
candidate_url_count=47
duplicate_product_surface_count=47
duplicate_source_count_legacy=47
stored_candidate_count=0
new_candidate_rejected_count=0
```

Attached and rerendered package artifact:

```text
generated_at=2026-07-12T07:13:48.947448Z
duplicate_product_surface_count=47
duplicate_source_count_legacy=47
post_run_next_sweep_status=Hermes rechecked 47 already-monitored product surfaces; no new sweepable sources were added for the next sweep.
html_size=392729
```

## Admin Demand Intake Runner Repair - 2026-07-12

Problem addressed:

- The CI-OS admin app already had demand import, GA4 export, registry, and
  product-surface management routes, but `scripts/run_admin.py` did not load
  the Hermes CI-OS env file by itself.
- In production that made the admin runner operationally brittle: a direct
  loopback launch could miss `CIOS_DATABASE_URL`, `CIOS_ADMIN_TOKEN`, Scout,
  GA4, and product-market settings unless the operator remembered to source
  the right file first.

Package-layer changes:

- `scripts/run_admin.py`
  - Adds `--env-file`.
  - Auto-loads `$CIOS_ENV_FILE`, `/opt/data/cios-env`, or
    `/root/.hermes/cios-env` when present.
  - Adds `--no-env-file` for explicit test/dev bypass.
  - Keeps the existing non-negotiable loopback bind guard.
  - Uses a small non-shell parser so values are loaded without printing or
    evaluating secrets.
- `tests/scripts/test_run_admin.py`
  - Proves explicit env-file loading happens before `uvicorn.run`.
  - Proves missing explicit env files fail fast.
  - Cleans up test env variables so admin auth tests remain isolated.

TDD evidence:

```text
red:
tests/scripts/test_run_admin.py
2 failed before implementation:
TypeError: main() takes 0 positional arguments but 1 was given

focused:
2 passed in 0.03s

admin/demand package slice:
89 passed, 1 warning in 3.13s

full local:
990 passed, 22 deselected, 1 warning in 11.72s
```

Remote deployment:

```text
backup_dir=/root/.hermes/apps/cios/backups/codex-run-admin-env-20260712T071947Z
deployed:
- scripts/run_admin.py
- tests/scripts/test_run_admin.py
```

Remote verification:

```text
admin/demand package slice:
89 passed, 1 warning in 6.33s

full remote:
989 passed, 1 skipped, 22 deselected, 1 warning in 10.16s
```

Remote loopback smoke:

```text
command:
.venv/bin/python scripts/run_admin.py --env-file /root/.hermes/cios-env --host 127.0.0.1 --port 18765

health={"status":"ok"}
admin_has_competitor_registry=True
admin_has_demand_section=True
drop_folder=/root/.hermes/apps/cios/data/looker/algolia
inbox_file_count=0
ready_count=0
template_header=Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL
post-smoke lingering admin processes=0
```

Current operational meaning:

- The admin app can now be launched from the deployed CI-OS package without
  manually sourcing secrets.
- The operator path to unblock recommendations is live at the package level:
  download the demand template, upload a Looker/GA export to
  `/root/.hermes/apps/cios/data/looker/algolia`, prepare/import it, and refresh
  Argus.
- No real demand file is currently queued, so the product-market system still
  correctly reports `ready_count=0` and blocks demand-backed recommendations.

## Admin Runner Package Contract Hardening - 2026-07-12

Problem addressed:

- `scripts/run_admin.py` had become required operational plumbing for registry
  management, demand upload, GA4 export, and Argus refresh, but the Hermes
  package preflight did not require it.
- A future deploy could omit the admin runner and still pass
  `verify_hermes_package_contract.py`, leaving operators without the safe
  local control surface needed to unblock demand evidence.

Package-layer changes:

- `scripts/verify_hermes_package_contract.py`
  - Adds `scripts/run_admin.py` to `REQUIRED_PATHS`.
- `tests/scripts/test_verify_hermes_package_contract.py`
  - Adds a red/green regression proving preflight fails when the admin runner
    is absent.

TDD and verification:

```text
red:
test_preflight_fails_when_admin_runner_missing
assert 0 == 2

focused:
24 passed in 1.42s

admin/demand slice:
90 passed, 1 warning in 3.08s

full local:
991 passed, 22 deselected, 1 warning in 11.17s
```

Remote deployment:

```text
backup_dir=/root/.hermes/apps/cios/backups/codex-package-contract-admin-runner-20260712T072533Z
deployed:
- scripts/verify_hermes_package_contract.py
- tests/scripts/test_verify_hermes_package_contract.py
```

Remote verification:

```text
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

contract/admin/demand slice:
90 passed, 1 warning in 6.89s

full remote:
990 passed, 1 skipped, 22 deselected, 1 warning in 10.13s
```

Current operational meaning:

- The deployed package now fails preflight if the safe local admin runner is
  missing.
- This makes the demand-unblock path part of the Hermes package contract,
  rather than an accidental script that could drift out of production.

## Admin Registry Edit Controls

Problem addressed:

- The CI-OS admin registry exposed add and pause/retire actions, but the local
  operator still could not edit competitor metadata, source URL metadata, or
  product-surface URLs from the HTML surface.
- That left the monitored universe only partially manageable and made Argus
  harder to correct when source families, domains, priorities, or product
  surfaces needed operator repair.

Package-layer changes:

- `src/cios/admin/app.py`
  - Adds HTML `POST` update routes for competitors, source URLs, and product
    surfaces.
  - Adds collapsed edit forms beside the existing pause/retire actions.
  - Keeps writes local/admin-only through the existing write-token dependency.
- `tests/admin/test_app.py`
  - Verifies the edit forms are visible in the HTML registry.
  - Verifies competitor, source, and product-surface edit submissions call the
    update repository methods and redirect back to the tenant admin view.

Local verification:

```text
python3 -m py_compile src/cios/admin/app.py

pytest tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms tests/admin/test_app.py::test_html_forms_edit_competitor_source_and_product_surface -q
2 passed in 0.37s

pytest tests/admin/test_app.py -q
54 passed in 1.50s

pytest tests/admin -q
63 passed in 1.48s

pytest -q
876 passed, 21 deselected in 8.84s
```

Remote deployment and verification:

```text
backup=/root/.hermes/apps/cios/.codex-backups/admin-registry-edit-20260711T212804Z
deployed_admin_registry_edit=ok

PYTHONPYCACHEPREFIX=/tmp/cios-pycache-admin-edit .venv/bin/python -m py_compile src/cios/admin/app.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms tests/admin/test_app.py::test_html_forms_edit_competitor_source_and_product_surface -q -p no:cacheprovider
2 passed, 1 warning in 1.27s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin/test_app.py -q -p no:cacheprovider
54 passed, 1 warning in 4.53s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin -q -p no:cacheprovider
60 passed, 1 warning in 4.41s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
869 passed, 1 skipped, 21 deselected, 1 warning in 9.45s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Live public smoke from the local E2E harness:

```text
python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/ --tenant algolia
PASS dashboard_click_validation
```

Note:

- The remote production venv does not currently include Playwright/browser
  dependencies, so the live browser E2E suite was run locally against the
  production URL instead of installing browser dependencies on the server during
  this admin registry slice.

## GA4 Demand Connector Setup Clarity

Live diagnosis:

```text
GA4 connector:
enabled=false
ready=false
status=disabled
property_configured=false
credentials_configured=false
current_start=null
current_end=null
previous_start=null
previous_end=null
output_path=/root/.hermes/apps/cios/data/looker/algolia/ga4-demand.json

Demand inbox:
drop_folder=/root/.hermes/apps/cios/data/looker/algolia
manifest_exists=true
discovered_count=0
ready_count=0
normalized_row_count=0
inbox_files=0
archived=0
rejected=0
```

Problem addressed:

- The live dashboard is correctly blocked on the inward-demand plane, but the
  local admin GA4 connector panel was too polite: when the connector was
  disabled it showed `Missing: None` and still rendered a runnable-looking
  `Run GA4 export now` button.
- That made an empty demand plane feel mysterious instead of operational.

Package-layer changes:

- `src/cios/admin/app.py`
  - The GA4 connector panel now explains the setup gap when disabled or
    incomplete.
  - It lists the required env/config keys:
    `CIOS_GA4_EXPORT_ENABLED`, `CIOS_GA4_PROPERTY_ID`,
    `CIOS_GA4_CURRENT_START`, `CIOS_GA4_CURRENT_END`,
    `CIOS_GA4_PREVIOUS_START`, `CIOS_GA4_PREVIOUS_END`, and
    `CIOS_GA4_CREDENTIALS_JSON` or `GOOGLE_APPLICATION_CREDENTIALS`.
  - The export button is disabled until `Ga4ExportStatus.ready` is true.
- `tests/admin/test_app.py`
  - Adds disabled-connector HTML coverage.
  - Keeps ready-connector HTML coverage.

Local TDD evidence:

```text
pytest tests/admin/test_app.py::test_admin_html_explains_disabled_ga4_connector_setup -q
1 failed before implementation:
- Connector setup needed was not rendered.

pytest tests/admin/test_app.py::test_admin_html_explains_disabled_ga4_connector_setup tests/admin/test_app.py::test_admin_html_shows_ga4_connector_and_form -q
2 passed in 0.42s

pytest tests/admin/test_app.py -q
55 passed in 1.54s

pytest tests/admin -q
64 passed in 1.58s

pytest -q
877 passed, 21 deselected in 9.16s
```

Remote deployment and verification:

```text
backup=/root/.hermes/apps/cios/.codex-backups/ga4-setup-clarity-20260711T213454Z
deployed_ga4_setup_clarity=ok

PYTHONPYCACHEPREFIX=/tmp/cios-pycache-ga4-clarity .venv/bin/python -m py_compile src/cios/admin/app.py

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin/test_app.py::test_admin_html_explains_disabled_ga4_connector_setup tests/admin/test_app.py::test_admin_html_shows_ga4_connector_and_form -q -p no:cacheprovider
2 passed, 1 warning in 1.27s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin/test_app.py -q -p no:cacheprovider
55 passed, 1 warning in 4.51s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/admin -q -p no:cacheprovider
61 passed, 1 warning in 4.43s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
870 passed, 1 skipped, 21 deselected, 1 warning in 9.43s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Live env render check:

```text
has_setup_needed=True
has_required_keys=True
has_disabled_button=True
```

## Demand Import Diagnostics

Problem addressed:

- The live dashboard is correctly blocked on the inward demand plane. That
  means the operator needs to bring GA4 / Looker Studio evidence and know
  whether Argus accepted it. A realistic Looker export should not silently
  normalize to zero rows because headers or date ranges differ from the exact
  template.

Package-layer changes:

- `src/cios/intelligence/importers.py`
  - Added `diagnose_looker_rows`.
  - Added support for `Page title and screen name`, `Landing page + query string`,
    `Engaged sessions (previous period)`, comma-formatted metrics, and
    `Date range` values such as `Jul 1, 2026 - Jul 8, 2026`.
- `src/cios/admin/demand_imports.py`
  - Demand import manifests now include skipped-row diagnostics with row number,
    reason, missing fields, source file, and available columns.

Local verification:

```text
pytest tests/intelligence/test_importers.py::test_normalizes_real_ga4_looker_page_export_with_date_range tests/intelligence/test_importers.py::test_diagnose_looker_rows_reports_skipped_row_reasons tests/admin/test_app.py::test_json_api_prepare_manifest_explains_skipped_demand_rows -q
3 passed in 0.39s

pytest tests/intelligence/test_importers.py tests/admin/test_app.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_import_demand_and_refresh.py -q
74 passed in 1.48s

python3 -m py_compile src/cios/intelligence/importers.py src/cios/admin/demand_imports.py

pytest -q
873 passed, 21 deselected in 8.86s
```

Remote deployment and verification:

```text
backup=/root/.hermes/apps/cios/.codex-backups/demand-import-diagnostics-20260711-170053
demand_import_diagnostics_deployed=ok

PYTHONPYCACHEPREFIX=/tmp/cios-pycache-demand-diagnostics .venv/bin/python -m py_compile src/cios/intelligence/importers.py src/cios/admin/demand_imports.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/intelligence/test_importers.py::test_normalizes_real_ga4_looker_page_export_with_date_range tests/intelligence/test_importers.py::test_diagnose_looker_rows_reports_skipped_row_reasons tests/admin/test_app.py::test_json_api_prepare_manifest_explains_skipped_demand_rows -q -p no:cacheprovider
3 passed, 1 warning in 1.09s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest tests/intelligence/test_importers.py tests/admin/test_app.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_import_demand_and_refresh.py -q -p no:cacheprovider
74 passed, 1 warning in 4.26s

PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q -p no:cacheprovider
866 passed, 1 skipped, 21 deselected, 1 warning in 8.63s
```

Remote prepare-only smoke:

```text
status prepared
ready_count 1
normalized_row_count 1
skipped_row_count 0
manifest_file_status ready
topic AI Shopping Agent
value 1240.0
period_start 2026-07-01T00:00:00+00:00
period_end 2026-07-08T00:00:00+00:00
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T171953Z-cockpit-intelligence-spine-ui.tgz
deployed_cockpit_intelligence_spine_ui=yes

.venv/bin/python -m pytest tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_intelligence_spine_as_argus_proof_chain tests/dashboard/test_cockpit_renderer.py::test_navigation_has_state_contract_and_distinct_section_targets tests/dashboard/test_cockpit_renderer.py::test_information_order_is_read_then_priority_then_roles_then_evidence -q --tb=short
3 passed in 0.30s

.venv/bin/python -m pytest tests/dashboard/test_cockpit_renderer.py -q --tb=short
23 passed in 0.18s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Hermes Argus Operator Handoff Artifact

Problem addressed:

- Argus could expose an evidence work queue, but Hermes still lacked a compact
  machine-readable handoff that says what the agent should do with the run.
- Without this artifact, the UI, admin console, Telegram, and future run console
  each had to infer actionability separately from dashboard data.

Package-layer changes:

- `scripts/build_argus_operator_handoff.py`
  - Consumes `argus-evidence-work-queue.json` and optional
    `argus-dashboard.json`.
  - Emits `argus-operator-handoff.json` with tenant, status, readiness,
    summary, top blocker, next operator action, command links, artifact refs,
    and queue counts.
  - Refuses mismatched tenant slugs so Hermes cannot accidentally mix tenant
    evidence into the wrong run.
- `deploy/cios-daily.sh`
  - Builds the handoff after the evidence work queue export.
  - Validates dashboard, brief, dashboard JSON, evidence queue, handoff, and
    competitor briefs before publish.
  - Syncs the deployed root wrapper from the package wrapper.
- `scripts/verify_hermes_package_contract.py`
  - Requires the handoff builder file.
  - Requires the daily wrapper to invoke `build_argus_operator_handoff.py`.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_build_argus_operator_handoff.py tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_builds_argus_operator_handoff_from_evidence_queue_before_publish tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_requires_argus_operator_handoff_artifact_before_publish tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_operator_handoff_builder_missing tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_wrapper_does_not_enable_product_market_by_default -q --tb=short
9 failed before implementation:
- build_argus_operator_handoff.py was missing.
- daily wrapper did not build the handoff.
- daily wrapper did not block publish when the handoff was absent.
- package contract did not require the handoff builder or wrapper invariant.

.venv/bin/python -m pytest tests/scripts/test_build_argus_operator_handoff.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short
31 passed in 4.35s

.venv/bin/python -m py_compile scripts/build_argus_operator_handoff.py scripts/export_argus_evidence_work_queue.py scripts/verify_hermes_package_contract.py
sh -n deploy/cios-daily.sh
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --skip-python-imports
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
861 passed, 21 deselected, 1 warning in 8.00s
```

Remote deployment and verification:

```text
archive_sha256=e25a1fc35b3066ed67d6b06eacb5b7b117e6661c8756f00eccecea759f8b700a
backup=/root/.hermes/backups/cios-app-20260711T201655Z-operator-handoff.tgz
deployed=operator-handoff

.venv/bin/python -m pytest tests/scripts/test_build_argus_operator_handoff.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short
31 passed in 1.52s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --skip-python-imports
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
854 passed, 1 skipped, 21 deselected, 1 warning in 7.53s

live handoff smoke:
artifact_exists True
tenant_slug algolia
status blocked_on_evidence
argus_readiness not_actionable
next_operator_action Upload GA4 / Looker demand export for the current and previous periods.
top_blocker argus-evidence:17:demand
```

## Admin Run Console Consumes Argus Operator Handoff

Problem addressed:

- Hermes could write `argus-operator-handoff.json`, but the operator/admin
  surface still did not consume it. The brain artifact was on disk, not visible
  where Argus is operated.
- The run console needed a single answer for whether Argus is actionable,
  blocked, or limited, plus the top blocker and next action.

Package-layer changes:

- `src/cios/admin/operator_handoff.py`
  - Added `ArgusOperatorHandoffStore`.
  - Reads `argus-operator-handoff.json` from the configured output directory,
    explicit `CIOS_OPERATOR_HANDOFF_PATH`, or the product-market workdir.
  - Returns safe `not_recorded` / `artifact_error` states when the artifact is
    absent or invalid.
- `src/cios/admin/types.py`
  - Added typed `ArgusOperatorCommand` and `ArgusOperatorHandoff` admin models.
- `src/cios/admin/app.py`
  - Added `/api/tenants/{tenant_slug}/argus/operator-handoff`.
  - Embedded the handoff in the Argus run console with status, readiness,
    blocking evidence count, top blocker, operator brief, command links, and
    artifact path.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/admin/test_operator_handoff.py tests/admin/test_app.py::test_json_api_returns_argus_operator_handoff_from_hermes_artifact tests/admin/test_app.py::test_admin_html_embeds_argus_operator_handoff_in_run_console -q --tb=short
Initial RED:
- No module named cios.admin.operator_handoff.
- create_app did not accept operator_handoff_store.

.venv/bin/python -m pytest tests/admin/test_operator_handoff.py tests/admin/test_app.py::test_json_api_returns_argus_operator_handoff_from_hermes_artifact tests/admin/test_app.py::test_admin_html_embeds_argus_operator_handoff_in_run_console -q --tb=short
4 passed, 1 warning

.venv/bin/python -m pytest tests/admin -q --tb=short
59 passed, 1 warning

.venv/bin/python -m pytest -q
865 passed, 21 deselected, 1 warning in 8.25s
```

Remote deployment and verification:

```text
archive_sha256=9e68bdaec7ef2545cee539be563a2b167e32b8354a00cd8e6498355db32ffdc3
backup=/root/.hermes/backups/cios-app-20260711T202543Z-admin-handoff-consumption.tgz

Remote focused first found a real bug:
- Explicit `out_dir` tests still fell back to `/tmp/cios-product-market/algolia`
  and saw the live artifact.
- Fixed `ArgusOperatorHandoffStore` so an explicit `out_dir` or artifact path
  is isolated before global fallbacks.

.venv/bin/python -m pytest tests/admin/test_operator_handoff.py tests/admin/test_app.py::test_json_api_returns_argus_operator_handoff_from_hermes_artifact tests/admin/test_app.py::test_admin_html_embeds_argus_operator_handoff_in_run_console -q --tb=short
4 passed, 1 warning

.venv/bin/python -m pytest tests/admin -q --tb=short
56 passed, 1 warning

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --skip-python-imports
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
858 passed, 1 skipped, 21 deselected, 1 warning in 8.03s

Live admin endpoint smoke:
status_code 200
tenant_slug algolia
handoff_status blocked_on_evidence
argus_readiness not_actionable
artifact_found True
next_operator_action Upload GA4 / Looker demand export for the current and previous periods.
top_blocker argus-evidence:17:demand
```

## 2026-07-11 19:53 UTC - Argus evidence work queue admin control plane

Problem addressed:

- Argus could explain that a recommendation was withheld because an evidence
  plane was missing, but that gap was still mostly dashboard prose.
- A CI operating system needs a control-plane queue: what evidence is missing,
  why it blocks action, what observed state proves the gap, and what exact
  operator action resolves it.

Package-layer changes:

- `src/cios/admin/evidence_work_queue.py`
  - Added a pure builder that converts latest `ArgusRunStatus` plus
    `EvidenceLedgerState` into typed operator work items.
  - Current work item planes cover demand, product proof, conversation, and
    pattern synthesis gaps.
- `src/cios/admin/types.py`
  - Added `ArgusEvidenceWorkItem` with stable id, evidence plane, severity,
    blocked outcomes, next step, operator surface, action links/forms, required
    input schema, observed state, and run-intelligence trace.
- `src/cios/admin/app.py`
  - Added local-admin JSON endpoint:
    `GET /api/tenants/{tenant_slug}/argus/evidence-work-queue`.
  - Added `Argus evidence work queue` to the admin page near the run console.
  - Added admin anchors for source and product-surface repair actions.
- `tests/admin/test_app.py`
  - Added RED/GREEN tests proving missing demand becomes a concrete operator
    work item and renders with demand-template plus refresh actions.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/admin/test_app.py::test_json_api_returns_argus_evidence_work_queue_for_missing_demand tests/admin/test_app.py::test_admin_html_shows_argus_evidence_work_queue_actions -q --tb=short
2 failed before implementation:
- JSON endpoint returned 404.
- Admin HTML did not render "Argus evidence work queue".

.venv/bin/python -m pytest tests/admin/test_app.py::test_json_api_returns_argus_evidence_work_queue_for_missing_demand tests/admin/test_app.py::test_admin_html_shows_argus_evidence_work_queue_actions -q --tb=short
2 passed, 1 warning in 0.38s

.venv/bin/python -m py_compile src/cios/admin/evidence_work_queue.py src/cios/admin/app.py src/cios/admin/types.py
.venv/bin/python -m pytest tests/admin/test_app.py tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing -q --tb=short
49 passed, 1 warning in 1.73s

.venv/bin/python -m pytest -q
846 passed, 21 deselected, 1 warning in 7.00s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment and verification:

```text
archive=/tmp/cios-evidence-work-queue/cios-evidence-work-queue.tgz
sha256=4dcc5583fdea769d3cdb0c54ec386ed33f140c6f69e33912c159490117fc0ba7
backup=/root/.hermes/backups/cios-app-20260711T195031Z-evidence-work-queue.tgz

.venv/bin/python -m py_compile src/cios/admin/evidence_work_queue.py src/cios/admin/app.py src/cios/admin/types.py
.venv/bin/python -m pytest tests/admin/test_app.py::test_json_api_returns_argus_evidence_work_queue_for_missing_demand tests/admin/test_app.py::test_admin_html_shows_argus_evidence_work_queue_actions -q --tb=short
2 passed, 1 warning in 1.03s

.venv/bin/python -m pytest tests/admin/test_app.py -q --tb=short
48 passed, 1 warning in 3.85s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
839 passed, 1 skipped, 21 deselected, 1 warning in 7.43s
```

Live DB-backed admin smoke:

```text
queue_status 200
queue_count 1
first_work_item argus-evidence:17:demand
first_plane demand
first_action Download demand template
admin_status 200
has_queue_section True
has_demand_template_action True
```

## 2026-07-11 20:02 UTC - Hermes evidence work queue export artifact

Problem addressed:

- The local admin endpoint made Argus evidence gaps visible, but Hermes cron
  still did not produce a durable operator artifact from the run.
- The system now needs a file that Hermes, Argus, Telegram, or a future run
  console can consume without scraping local-admin HTML.

Package-layer changes:

- `scripts/export_argus_evidence_work_queue.py`
  - Added Hermes-callable CLI:
    `--tenant algolia --output <path>/argus-evidence-work-queue.json`.
  - Reads the live DB through the CI-OS package repository layer.
  - Emits tenant id, generation timestamp, work item counts, blocking/limiting
    counts, and typed work items with action links and observed state.
- `deploy/cios-daily.sh`
  - Runs the exporter after post-run dashboard rerender.
  - Blocks publish if `$OUT/argus-evidence-work-queue.json` is missing.
  - Synced to `/root/.hermes/scripts/cios-daily.sh` for Hermes cron.
- `scripts/verify_hermes_package_contract.py`
  - Package preflight now requires the exporter and wrapper invariant.
- Tests added/updated:
  - `tests/scripts/test_export_argus_evidence_work_queue.py`
  - `tests/deploy/test_cios_daily_wrapper.py`
  - `tests/scripts/test_verify_hermes_package_contract.py`

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_export_argus_evidence_work_queue.py tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_applies_product_market_schema_before_daily_runner tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_executes_product_muscle_gap_discovery_before_publish tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_requires_evidence_work_queue_artifact_before_publish tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_evidence_work_queue_export_missing tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_wrapper_does_not_enable_product_market_by_default -q --tb=short
9 failed before implementation:
- exporter script missing
- wrapper did not invoke exporter
- wrapper did not require artifact before publish
- package preflight did not require exporter/invariant

.venv/bin/python -m pytest tests/scripts/test_export_argus_evidence_work_queue.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short
27 passed in 4.40s

.venv/bin/python -m py_compile scripts/export_argus_evidence_work_queue.py src/cios/admin/evidence_work_queue.py src/cios/admin/app.py src/cios/admin/types.py
sh -n deploy/cios-daily.sh
.venv/bin/python -m pytest -q
852 passed, 21 deselected, 1 warning in 7.37s
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Live DB bug found and fixed:

```text
First live export failed:
KeyError: 0 in PgAdminRepository._tenant_id

Root cause:
- Export script opened the connection with dict_row.
- PgAdminRepository._tenant_id expects tuple rows for its own default cursor.

Regression:
.venv/bin/python -m pytest tests/scripts/test_export_argus_evidence_work_queue.py::test_export_argus_evidence_work_queue_resolves_tenant_slug_from_tuple_rows -q --tb=short
1 failed before fix: TypeError tuple indices must be integers or slices, not str

Fix:
- `resolve_tenant_id` accepts dict or tuple rows.
- Script opens psycopg with default row behavior so PgAdminRepository remains compatible.

.venv/bin/python -m pytest tests/scripts/test_export_argus_evidence_work_queue.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short
28 passed in 4.13s
.venv/bin/python -m pytest -q
853 passed, 21 deselected, 1 warning in 7.10s
```

Remote deployment and verification:

```text
archive=/tmp/cios-evidence-work-queue/cios-evidence-work-queue-export.tgz
sha256=b7caa73a91f540c17bf77737f3abf7c12965d441e6029ba1f8bc6dd0712e5538
backup=/root/.hermes/backups/cios-app-20260711T200018Z-evidence-work-queue-export.tgz

sh -n /root/.hermes/apps/cios/deploy/cios-daily.sh
sh -n /root/.hermes/scripts/cios-daily.sh
cmp -s /root/.hermes/apps/cios/deploy/cios-daily.sh /root/.hermes/scripts/cios-daily.sh

.venv/bin/python -m pytest tests/scripts/test_export_argus_evidence_work_queue.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short
27 passed in 1.97s
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

Remote tuple-row repair:
sha256=11b80d79b9bed0561bd02184567d08cbace9d3f60d20fd57f6f4ef1dbd09b3ba
.venv/bin/python -m pytest tests/scripts/test_export_argus_evidence_work_queue.py -q --tb=short
5 passed in 0.69s

.venv/bin/python -m pytest -q
846 passed, 1 skipped, 21 deselected, 1 warning in 7.42s
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Live artifact proof:

```text
artifact_path /tmp/cios-product-market/algolia/argus-evidence-work-queue.json
artifact_exists True
tenant_slug algolia
work_item_count 1
blocking_count 1
first_work_item argus-evidence:17:demand
first_plane demand
first_action Download demand template
```

## Demand Ledger Run Trace Repair

Problem addressed:

- After a GA / Looker import and ledger refresh, the dashboard could render
  current demand evidence from the product-market ledger while the operator
  run trace still preserved the stale pre-import dashboard state and read
  `demand_plane_status = missing`.
- This made the screen internally contradictory: the intelligence spine could
  show audience-demand evidence, while the Hermes/Argus run trace still claimed
  no demand proof was processed.

Package-layer changes:

- `src/cios/dashboard/state_builder.py`
  - Builds product-market run history and current demand signals before the
    run trace.
  - Lets `ProductMarketRunStatus` fall back to latest durable
    `product_market_run_intelligence.demand_signal_count` and current
    `demand_signals` rows when the saved dashboard trace has stale zero Looker
    counts.
  - Keeps raw export-file discovery counts separate from durable demand-row
    proof, so operator diagnostics do not invent files that were not observed.
- `tests/dashboard/test_state_builder.py`
  - Added regression coverage for stale saved traces after ledger replay:
    saved run says zero Looker rows, but current ledger run intelligence and
    demand rows must make the demand plane read as processed/present.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_uses_current_ledger_demand_when_saved_trace_is_stale -q
RED before implementation:
- AssertionError: expected processed, got missing

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_uses_current_ledger_demand_when_saved_trace_is_stale -q
1 passed in 0.09s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/scripts/test_product_market_dashboard_wiring.py -q
54 passed in 0.19s

.venv/bin/python -m pytest tests/scripts/test_import_demand_and_refresh.py tests/admin/test_app.py -q
53 passed, 1 warning in 1.47s

.venv/bin/python -m pytest tests/db/test_product_market_repo.py tests/db/test_product_market_schema_contract.py tests/intelligence tests/scripts/test_product_market_runner.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_daily_run.py -q
172 passed in 0.92s

.venv/bin/python -m pytest tests/dashboard tests/admin -q
176 passed, 1 warning in 1.59s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
841 passed, 21 deselected, 1 warning in 7.08s
```

Remote deployment and verification:

```text
uploaded=/tmp/cios-demand-trace-repair.tgz
sha256=4abe3102b661f968dddff85d63285fdda6a1506aedd20d73a1f8f8c568ad0e46
backup=/root/.hermes/backups/cios-app-20260711T192621Z-demand-trace-repair.tgz

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_uses_current_ledger_demand_when_saved_trace_is_stale -q
1 passed in 0.36s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/scripts/test_product_market_dashboard_wiring.py tests/scripts/test_import_demand_and_refresh.py tests/admin/test_app.py -q
107 passed, 1 warning in 3.75s

.venv/bin/python -m pytest tests/db/test_product_market_repo.py tests/db/test_product_market_schema_contract.py tests/intelligence tests/scripts/test_product_market_runner.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py -q
165 passed in 0.86s

.venv/bin/python -m pytest -q
834 passed, 1 skipped, 21 deselected, 1 warning in 7.66s

.venv/bin/python scripts/rerender_dashboard.py --tenant algolia --out-dir /root/.hermes/apps/cios/out
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 356292 bytes from live DB state

Live lightweight contract:
- https://ci.chowmes.com/ returned 355846 bytes.
- `schema_version` is 17.
- Monitored competitors: 27.
- Competitor brief hrefs: 27 total, 27 unique.
- Sampled competitor brief URLs returned HTTP/2 200.
- Production still has zero real demand rows, so the live demand plane remains
  correctly `missing`; this repair is proven by regression tests rather than
  injected fake production data.
```

Validation gap discovered:

- `scripts/validate_dashboard_clicks.py` cannot currently run in either the
  local or production venv because `playwright` is not installed.
- The VPS also has no existing Chromium / Chrome binary on PATH.
- Next validation-infrastructure slice should make Playwright/browser tooling
  an explicit dev/test dependency or provide a containerized click-suite runner.

## Dashboard Click-Suite Dependency Repair

Problem addressed:

- The public dashboard click validator existed, but failed at import time when
  `playwright` was missing. That meant even a dependency preflight could not
  run, and operators got a raw `ModuleNotFoundError` instead of a clear
  bootstrap path.
- The production command path also passed `--tenant algolia`, but the validator
  parser did not accept `--tenant`; after fixing the import, the next failure
  would have been an argument error.

Package-layer changes:

- `pyproject.toml`
  - Added an explicit `e2e` optional dependency group with `playwright>=1.45`.
  - Added `cios[e2e]` to the `dev` extra so developer installs carry the click
    validator dependencies.
- `scripts/validate_dashboard_clicks.py`
  - Moved Playwright import behind a dependency preflight instead of importing
    at module load.
  - Added `--check-dependencies`.
  - Accepts `--tenant` as a compatibility no-op for Hermes/operator wrappers.
  - Prints actionable bootstrap commands:
    `python -m pip install -e '.[e2e]'` and
    `python -m playwright install chromium`.
- `tests/scripts/test_validate_dashboard_clicks_dependencies.py`
  - Added dependency-contract coverage for the e2e extra, missing-dependency
    help, and `--tenant` compatibility.

Local TDD and validation evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_validate_dashboard_clicks_dependencies.py -q
RED before implementation:
- e2e optional dependency missing from pyproject.
- validate_dashboard_clicks.py crashed with ModuleNotFoundError before preflight.

.venv/bin/python -m pytest tests/scripts/test_validate_dashboard_clicks_dependencies.py -q
3 passed in 0.06s

.venv/bin/python scripts/validate_dashboard_clicks.py --check-dependencies --tenant algolia
dashboard click validation dependencies missing
- Python package `playwright` is not installed.
Install with:
  python -m pip install -e '.[e2e]'
  python -m playwright install chromium

.venv/bin/python -m pip install -e '.[e2e]'
Successfully installed cios-0.1.0 greenlet-3.5.3 playwright-1.61.0 pyee-13.0.1

.venv/bin/python -m playwright install chromium
exit 0

.venv/bin/python scripts/validate_dashboard_clicks.py --check-dependencies --tenant algolia
PASS dashboard_click_dependencies

.venv/bin/python scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/ --tenant algolia
PASS structure
PASS nav_targets
PASS timeline
PASS semantic_layer
PASS priority_selection
PASS brief_routing
PASS appendices
PASS viewport_390
PASS viewport_768
PASS viewport_1280
PASS dashboard_click_validation

.venv/bin/python -m pytest -q
844 passed, 21 deselected, 1 warning in 6.81s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment and verification:

```text
uploaded=/tmp/cios-click-validator-deps.tgz
sha256=fba42a7fe6038441841a7fc3f0eed6439694c3203cd02cfa971dafe22bd89072
backup=/root/.hermes/backups/cios-app-20260711T193551Z-click-validator-deps.tgz

.venv/bin/python -m pytest tests/scripts/test_validate_dashboard_clicks_dependencies.py -q
3 passed in 0.11s

.venv/bin/python -m py_compile scripts/validate_dashboard_clicks.py
exit 0

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python scripts/validate_dashboard_clicks.py --check-dependencies --tenant algolia
dashboard click validation dependencies missing
- Python package `playwright` is not installed.
Install with:
  python -m pip install -e '.[e2e]'
  python -m playwright install chromium
exit=2

.venv/bin/python -m pytest -q
837 passed, 1 skipped, 21 deselected, 1 warning in 7.33s
```

Production note:

- The VPS has the package/script repair and clear preflight now.
- The real browser click suite was intentionally not enabled on the VPS in
  this slice because installing Playwright plus Chromium is environment setup,
  not a no-risk code deploy. Local live browser validation passed against
  `https://ci.chowmes.com/`.

## Demand Evidence Observed-State Contract

Problem addressed:

- The cockpit could correctly say Argus was blocked by missing demand evidence,
  but the evidence request did not expose what the Hermes / CI-OS demand plane
  actually observed.
- That made the UI feel like another generic instruction instead of a runtime
  truth: whether Looker files were discovered, ready, errored, normalized, or
  only absent.

Package-layer changes:

- `ArgusEvidenceNeedSummary` now carries additive `observed_state` JSON.
- Demand-plane evidence needs now copy observed demand diagnostics from
  `ProductMarketRunStatus`: demand plane status, Looker discovered / ready /
  error counts, normalized row count, skipped / archived counts, and manifest
  path when available.
- The cockpit renders those diagnostics as a compact proof line under
  `What Argus needs next`.

Local TDD evidence:

```text
python3 -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions -q --tb=short
2 failed before implementation:
- ArgusEvidenceNeedSummary had no observed_state field.
- The cockpit did not render "Demand checked: missing".

python3 -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions -q --tb=short
2 passed in 0.26s

python3 -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag -q --tb=short
3 passed in 0.09s

python3 -m pytest tests/dashboard -q --tb=short
122 passed in 0.29s

python3 -m pytest -q --tb=short
838 passed, 21 deselected in 6.47s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment and validation:

```text
backup=/root/.hermes/backups/cios-app-20260711T191504Z-demand-ledger-persist.tgz

.venv/bin/python -m pytest tests/admin/test_demand_imports.py::test_demand_import_ledger_persister_saves_prepared_rows_as_demand_signals tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_persists_prepared_demand_before_refresh -q --tb=short
4 passed, 1 warning in 1.16s

.venv/bin/python -m pytest tests/admin tests/intelligence tests/db/test_product_market_repo.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_daily_run.py::test_product_market_chain_passes_discovered_looker_drop_folder_exports tests/scripts/test_daily_run.py::test_product_market_chain_can_export_ga4_demand_before_payload_build tests/scripts/test_daily_run.py::test_product_market_chain_refreshes_ledger_with_learning_plan_after_synthesis -q --tb=short
138 passed, 1 warning in 3.76s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q --tb=short
833 passed, 1 skipped, 21 deselected, 1 warning in 7.19s

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS dashboard_click_validation

curl https://ci.chowmes.com/data/semantic-dashboard.json
schema_version 17
generated_at 2026-07-11T19:04:04.160264Z
argus_evidence_needs 1
demand_signals 0
```

Production note:

- No synthetic GA / Looker row was inserted into the live Algolia tenant during
  validation. The persistence bridge is verified by tests against the same
  repository boundary, but production demand remains absent until a real export
  is provided or the GA4 connector is configured with real credentials.

Remote deployment and live validation:

```text
backup=/root/.hermes/backups/cios-app-20260711T190251Z-demand-observed-state.tgz

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag -q --tb=short
3 passed in 0.53s

.venv/bin/python -m pytest tests/dashboard -q --tb=short
122 passed in 0.69s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q --tb=short
831 passed, 1 skipped, 21 deselected, 1 warning in 7.56s

.venv/bin/python scripts/rerender_dashboard.py --tenant algolia --out-dir /root/.hermes/apps/cios/out
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 356292 bytes from live DB state

publish_dashboard_artifacts(...)
status=published
json=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public/data/semantic-dashboard.json
briefs=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public/briefs

curl https://ci.chowmes.com/data/semantic-dashboard.json
schema_version 17
generated_at 2026-07-11T19:04:04.160264Z
evidence_need_count 1
demand_plane_status missing
looker_discovered_count 0
looker_ready_count 0
looker_error_count 0
looker_normalized_row_count 0
looker_manifest_path /tmp/cios-product-market/algolia/looker-export-manifest.json

curl https://ci.chowmes.com/
Demand checked: missing True
0 files discovered True
0 accepted rows True
looker-export-manifest.json True

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS dashboard_click_validation
```

## Demand Import Ledger Persistence Bridge

Problem addressed:

- The local admin and CLI demand-import fast lanes could normalize uploaded
  GA / Looker exports and then ask Argus to refresh from the evidence ledger.
- But a fast-lane upload was not guaranteed to enter the `demand_signals`
  ledger before the replay. That meant the operator button could look like it
  refreshed Argus while Argus was still reading the old ledger.

Package-layer changes:

- Added `DemandImportLedgerPersistResult`.
- Added `DemandImportLedgerPersister`, which reads prepared normalized Looker
  payloads, maps rows through `looker_row_to_demand_signal`, and persists them
  with the existing product-market repository `save_demand_signal` boundary.
- Wired the JSON admin action
  `/api/tenants/{tenant}/argus/demand-imports/refresh` to:
  prepare demand -> persist demand ledger rows -> replay Argus ledger ->
  refresh dashboard.
- Wired the HTML admin form to the same order.
- Updated `scripts/import_demand_and_refresh.py` so the Hermes-callable CLI also
  persists demand rows by default before running ledger refresh. It keeps
  `--skip-ledger-persist` for tests or deliberate dry orchestration.

Local TDD evidence:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_persists_prepared_demand_before_refresh -q --tb=short
3 failed before implementation:
- create_app() had no demand_import_ledger_persister dependency.
- import_demand_exports() had no tenant_id / demand-ledger persistence support.

python3 -m pytest tests/admin/test_demand_imports.py::test_demand_import_ledger_persister_saves_prepared_rows_as_demand_signals tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_persists_prepared_demand_before_refresh -q --tb=short
4 passed in 0.49s

python3 -m pytest tests/admin tests/scripts/test_import_demand_and_refresh.py -q --tb=short
60 passed in 1.28s

python3 -m pytest tests/admin tests/intelligence tests/db/test_product_market_repo.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_daily_run.py::test_product_market_chain_passes_discovered_looker_drop_folder_exports tests/scripts/test_daily_run.py::test_product_market_chain_can_export_ga4_demand_before_payload_build tests/scripts/test_daily_run.py::test_product_market_chain_refreshes_ledger_with_learning_plan_after_synthesis -q --tb=short
141 passed in 1.55s

python3 -m pytest -q --tb=short
840 passed, 21 deselected in 6.82s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

## Demand Refresh Operator Read

Problem addressed:

- The demand import fast lane could copy a GA / Looker export, normalize it,
  replay Argus from the evidence ledger, and rerender artifacts.
- The operator summary still mostly exposed command plumbing. The refreshed
  Argus read was buried in `refresh.stdout`, so an admin or Hermes console
  could not directly show what Argus learned after inward demand arrived.

Package-layer changes:

- `scripts/import_demand_and_refresh.py`
  - Parses the JSON emitted by `refresh_product_market_from_ledger.py`.
  - Adds top-level `argus_read` to the demand refresh summary when refresh
    succeeds.
  - Exposes verdict, top insight, primary action, demand summary, conversion
    summary, and product/conversation/demand/pattern/recommendation counts.
  - Ignores non-JSON refresh output safely instead of failing unrelated
    rerender/publish flows.

Local TDD evidence:

```text
python3 -m pytest tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_surfaces_refreshed_argus_read -q --tb=short
1 failed before implementation:
- KeyError: 'argus_read'

python3 -m pytest tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_surfaces_refreshed_argus_read -q --tb=short
1 passed in 0.33s

python3 -m pytest tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_product_market_runner.py tests/intelligence/test_runner.py -q --tb=short
23 passed in 0.37s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Remote package verification:

```text
Remote package probe before deploy:
import_script=present
has_argus_read_parser=no
has_argus_read_token=no

Remote deploy:
backup=/root/.hermes/backups/cios-demand-argus-read-post-20260711T183544Z.tgz
deployed_argus_read_parser=yes

sudo bash -lc 'cd /root/.hermes/apps/cios && .venv/bin/python -m pytest tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_product_market_runner.py tests/intelligence/test_runner.py -q --tb=short'
23 passed in 1.29s

sudo bash -lc 'cd /root/.hermes/apps/cios && .venv/bin/python -m py_compile scripts/import_demand_and_refresh.py && .venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim'
PASS: CI-OS Hermes package contract satisfied
```

## Admin Demand Refresh Argus Read

Problem addressed:

- The CLI demand fast lane now exposes `argus_read`, but the local-admin
  one-click action still returned the refreshed intelligence buried inside
  `ledger_refresh`.
- That meant an admin UI or run console had to understand the raw runner shape
  before it could answer "what did Argus learn after this demand refresh?"

Package-layer changes:

- `src/cios/admin/app.py`
  - Added `_argus_read_from_ledger_refresh`.
  - `POST /api/tenants/{tenant}/argus/demand-imports/refresh` now returns a
    top-level `argus_read` with verdict, top insight, primary action, demand
    summary, conversion summary, and counts.
  - Existing `ledger_refresh` remains unchanged for lower-level debugging.

Local TDD evidence:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action -q --tb=short
1 failed before implementation:
- KeyError: 'argus_read'

python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action -q --tb=short
1 passed in 0.49s

python3 -m pytest tests/admin/test_app.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_product_market_runner.py tests/intelligence/test_runner.py -q --tb=short
69 passed in 1.45s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q --tb=short
838 passed, 21 deselected in 6.48s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-admin-argus-read-20260711T184002Z.tgz
deployed_admin_argus_read=yes

Initial remote preflight failed because the deployed package was skewed:
- missing `cios.admin.learning_apply`
- then stale `cios.admin.types`
- then missing `cios.learn.apply`
- then root/app wrappers lacked `audit_learning_policies.py`

Package skew repaired by syncing:
- `src/cios/admin/`
- `src/cios/learn/`
- learning/audit scripts and tests
- tested `deploy/cios-daily.sh` into both app wrapper and `/root/.hermes/scripts/cios-daily.sh`

sh -n /root/.hermes/apps/cios/deploy/cios-daily.sh
sh -n /root/.hermes/scripts/cios-daily.sh
wrappers_have_audit=yes

sudo bash -lc 'cd /root/.hermes/apps/cios && .venv/bin/python -m pytest tests/admin tests/learn tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_build_learning_apply_plan.py tests/scripts/test_execute_learning_apply_plan.py tests/scripts/test_audit_learning_policies.py tests/scripts/test_verify_hermes_package_contract.py tests/deploy/test_cios_daily_wrapper.py -q --tb=short'
118 passed, 1 warning in 5.32s

sudo bash -lc 'cd /root/.hermes/apps/cios && .venv/bin/python scripts/audit_learning_policies.py --package-root /root/.hermes/apps/cios --json'
issue_count=0

sudo bash -lc 'cd /root/.hermes/apps/cios && .venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim'
PASS: CI-OS Hermes package contract satisfied
```

Live Hermes wrapper acceptance after wrapper/package skew repair:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

PASS: CI-OS Hermes package contract satisfied
PASS: CI-OS learning policy audit clean policies=0 ok=0
product-market schema ready

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 411.6s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Public artifact verification:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=17
generated_at=2026-07-11T18:50:51.267626Z
competitors=27
source_health=48
product_market_status=ran
demand_plane_status=missing
scout_artifact_count=35
argus_evidence_needs=1

https://ci.chowmes.com/
status=200
last_modified=Sat, 11 Jul 2026 18:50:51 GMT

https://ci.chowmes.com/brief.html
status=200
last_modified=Sat, 11 Jul 2026 18:50:51 GMT
```

Live click validation:

```text
python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS structure
PASS nav_targets
PASS timeline
PASS semantic_layer
PASS priority_selection
PASS brief_routing
PASS appendices
PASS viewport_390
PASS viewport_768
PASS viewport_1280
PASS dashboard_click_validation
```

Publish and live validation:

```text
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 355197 bytes from live DB state
publish_status published
has_spine_section True
has_proof_nav True
has_argus_proof_title True
has_next_operator_action True

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS structure: Read, timeline, semantic layer, priority moves, selected competitor, role implications, evidence sections, and Argus assets present
PASS nav_targets: Top nav updates hash/current state and lands on distinct sections
PASS timeline: History controls, holistic coverage, and priority rationale are visible
PASS semantic_layer: Selector, heat map, recommendation, and confidence rubric validated with Google Vertex AI Search
PASS priority_selection: Quiet current run has no priority buttons and shows the no-new-material-moves state
PASS brief_routing: Checked Constructor, Elastic, Algonomy
PASS appendices: Coverage and evidence appendices open and expose brief/source details
PASS viewport_390: 390x844 loaded rebuilt dashboard
PASS viewport_768: 768x1024 loaded rebuilt dashboard
PASS viewport_1280: 1280x900 loaded rebuilt dashboard
PASS dashboard_click_validation

https://ci.chowmes.com/
HTTP/2 200
last-modified: Sat, 11 Jul 2026 17:20:37 GMT
content-length: 355197

curl -fsS https://ci.chowmes.com/
has_spine_section True
has_proof_nav True
has_argus_proof_title True
has_next_operator_action True
```

## Demand Import Fast Lane

Problem addressed:

- The live dashboard correctly reports `demand_plane_status=missing` because no
  GA / Looker evidence is present on the server. The system should not invent
  demand.
- Operators needed a package-owned one-command path to take a GA / Looker
  export file, normalize it into the demand plane, replay Argus from existing
  ledgers, and rerender the dashboard without rerunning the full outward crawl.

Package-layer changes:

- `scripts/import_demand_and_refresh.py`
  - Copies provided CSV/JSON/JSONL exports into
    `data/looker/<tenant>/`.
  - Reuses `DemandImportStore.prepare()` to normalize rows into the
    product-market workdir.
  - In full mode calls the existing
    `refresh_product_market_from_ledger.py` and `rerender_dashboard.py`.
  - Supports `--prepare-only` for safe validation without DB refresh or
    publish.
- `scripts/verify_hermes_package_contract.py`
  - Now requires the demand fast-lane script in the installed CI-OS package.
- `tests/scripts/test_import_demand_and_refresh.py`
  - Added fast-lane import, prepare, refresh, and rerender command tests.
- `tests/scripts/test_verify_hermes_package_contract.py`
  - Added a negative preflight test proving packages without the demand fast
    lane fail.

Local TDD evidence:

```text
python3 -m pytest tests/scripts/test_import_demand_and_refresh.py -q
3 failed before implementation:
- scripts/import_demand_and_refresh.py did not exist.

python3 -m pytest tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_demand_fast_lane_missing -q
1 failed before implementation:
- preflight incorrectly passed without scripts/import_demand_and_refresh.py.

python3 -m pytest tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_verify_hermes_package_contract.py tests/admin/test_app.py::test_json_api_prepares_queued_demand_exports_without_archiving tests/admin/test_app.py::test_admin_html_can_prepare_queued_demand_exports -q
13 passed in 0.71s

python3 -m pytest -q
792 passed, 21 deselected in 4.98s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T163458Z-demand-import-fast-lane.tgz

.venv/bin/python -m pytest tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_verify_hermes_package_contract.py -q
11 passed in 0.90s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python scripts/import_demand_and_refresh.py --tenant algolia --app-dir /tmp/cios-demand-fastlane.../app --work-root /tmp/cios-demand-fastlane.../work --input /tmp/cios-demand-fastlane.../ga-pages.csv --prepare-only --output /tmp/cios-demand-fastlane.../summary.json
status prepared
discovered_count 1
ready_count 1
normalized_row_count 1
normalized_exists yes
```

## Demand Fast Lane Staged Publish

Problem addressed:

- The demand fast lane could normalize demand exports and rerender dashboard
  artifacts, but it stopped short of a safe optional public promotion.
- An operator needed an explicit way to publish refreshed demand-backed Argus
  artifacts without rerunning the full outward sweep, while preserving the same
  artifact validation and staged-copy discipline used by the Hermes daily
  wrapper.

Package-layer changes:

- `scripts/import_demand_and_refresh.py`
  - Added `publish_dashboard_artifacts(out_dir, public_dir)`.
  - Validates `argus-dashboard.html`, `brief.html`,
    `argus-dashboard.json`, and `briefs/` before any public copy.
  - Publishes through a `.argus-publish.<pid>` staging directory.
  - Supports explicit `--publish --public-dir <path>` after refresh/rerender.
  - Leaves publish disabled by default.
- `tests/scripts/test_import_demand_and_refresh.py`
  - Added staged public-copy coverage.
  - Added CLI coverage for `--publish --public-dir`.

Local TDD evidence:

```text
python3 -m pytest tests/scripts/test_import_demand_and_refresh.py::test_publish_dashboard_artifacts_uses_staged_public_copy tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_can_publish_after_rerender -q
2 failed before implementation:
- publish_dashboard_artifacts did not exist.
- --publish and --public-dir were unrecognized arguments.

python3 -m pytest tests/scripts/test_import_demand_and_refresh.py -q
5 passed in 0.28s

python3 -m pytest tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_verify_hermes_package_contract.py tests/deploy/test_cios_daily_wrapper.py -q
21 passed in 3.25s

python3 -m pytest -q
794 passed, 21 deselected in 5.39s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T163933Z-demand-fastlane-staged-publish.tgz

.venv/bin/python -m pytest tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_verify_hermes_package_contract.py -q
13 passed in 1.08s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

scratch publish dry run:
status published
prepare.ready_count 1
prepare.normalized_row_count 1
publish.status published
scratch_publish_ok yes
```

Local regression suite:

```text
679 passed, 18 deselected in 3.14s
```

## Remaining Caveats

- Source coverage is degraded: 9 of 48 source fetches failed. They are now
  explicit source-health facts, not hidden absences.
- Product-surface coverage is degraded when individual pages scrape empty
  markdown. The run is allowed when other product surfaces succeed, but the UI
  must continue to show degraded source/surface coverage honestly.
- Product-surface execution is serial and took several minutes. Before this is
  considered operationally mature, expose product-surface success/failure
  counts directly in the dashboard. The execution itself is now bounded
  parallel with `max_workers=3`.
- The UI is validated for click routing and data freshness, but the deeper IA
  and semantic product direction still need the larger Argus redesign work.

## Addendum: Quality Gate Repair And Republish - 2026-07-11 05:18 UTC

Root cause from the blocked live run:

- The real Hermes wrapper generated current artifacts but blocked publication
  because `quality_status=failed`.
- The latest `quality_reviews` row for `daily-algolia-1783745979` rejected the
  Constructor read because the reviewer saw unsourced strategic-intent language
  and unrelated evidence excerpts from Doofinder, Klevu, Luigi's Box, MCP, and
  GitHub A2A.
- This was a CI-OS package bug, not a Hermes-core bug. The quality reviewer was
  receiving a broad fetched-source evidence block instead of only evidence for
  the cited reviewed claim. The reviewed claim text also carried too little of
  the reader-facing signal body.

Package fixes:

- `scripts/daily_production_run.py`
  - `ClaudeQualityReviewer._build_evidence_block()` now filters evidence to the
    URLs cited by the claims being reviewed.
  - Added `review_claim_for_signal()` so quality review evaluates headline,
    what changed, why it matters, and implication, not only the headline.
- `src/cios/brain/prompts.py`
  - Tightened the daily synthesis rule against inferred competitor intent and
    uncited category-shift claims. Observable positioning is allowed; motive
    claims require explicit source support.

Regression evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_quality_evidence_block_only_includes_cited_claim_sources tests/scripts/test_daily_run.py::test_quality_review_claim_text_includes_signal_body_not_only_headline -q
2 passed in 0.24s

.venv/bin/python -m pytest tests/brain/test_prompts.py::test_daily_synthesis_prompt_bans_uncited_intent_and_category_shift_claims tests/scripts/test_daily_run.py::test_quality_evidence_block_only_includes_cited_claim_sources tests/scripts/test_daily_run.py::test_quality_review_claim_text_includes_signal_body_not_only_headline -q
3 passed in 0.18s

.venv/bin/python -m pytest tests/brain/test_prompts.py tests/brain/test_quality.py tests/brain/test_synthesizer.py tests/scripts/test_daily_run.py -q
84 passed in 0.22s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Live deployed package evidence:

```text
Backup: /root/.hermes/backups/cios-app-20260711T051442Z-quality-gate-fix

bash -n deploy/cios-daily.sh scripts/daily_production_run.py scripts/verify_hermes_package_contract.py
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_quality_evidence_block_only_includes_cited_claim_sources tests/scripts/test_daily_run.py::test_quality_review_claim_text_includes_signal_body_not_only_headline tests/brain/test_prompts.py::test_daily_synthesis_prompt_bans_uncited_intent_and_category_shift_claims -q
3 passed in 0.50s
```

Live Hermes wrapper acceptance:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=38 failed=10 skipped=0 facts=429 deltas=429 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=2
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 194.9s. LLM calls used: 2 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live production artifact check:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
HTTP/2 200
last-modified: Sat, 11 Jul 2026 05:18:30 GMT
schema 12
generated_at 2026-07-11T05:18:30.810161Z
cards 15
monitored 27
product_market_run ran quiet
scout_artifact_count 20

https://ci.chowmes.com/
HTTP/2 200
last-modified: Sat, 11 Jul 2026 05:18:30 GMT
content-length: 339134

https://ci.chowmes.com/brief.html
HTTP/2 200
last-modified: Sat, 11 Jul 2026 05:18:30 GMT
content-length: 58509
```

Live browser smoke:

```text
PASS live_browser_smoke sections/nav/selector/briefs Constructor:200,Elastic:200,Algonomy:200
```

New caveats from this run:

- The current run is genuinely quiet after quality review: `signals=0`,
  `verdict=quiet`, `quality=passed`.
- The public dashboard still exposes 15 rolling-window material cards, so the
  UI can still blur today's quiet read with historical material cards. This is
  an IA/data-contract issue to fix next, not a Hermes execution failure.
- Product-market execution ran and produced 20 Scout artifacts, but this run's
  product-market verdict was quiet and the published movement map says no
  movement map is available. The next backend slice should make the product
  muscle explain why product-surface artifacts did or did not become patterns.

## Addendum: Current Run Vs Rolling Memory Fix

Time: 2026-07-11 05:42 UTC

Problem:

- The live dashboard correctly completed a quiet Hermes/Argus run, but the UI
  still used rolling 14-day `competitor_cards` as if they were current-day
  promoted moves.
- This made a quiet run look actionable and preserved the exact confusion the
  user raised: "today" and historical/recent memory were visually blended.

Package changes:

- `RunHealth` now publishes separate current and rolling counts:
  `current_material_delta_count`, `rolling_material_delta_count`, and
  `material_delta_count`.
- `scripts/daily_production_run.py` writes current-run
  `material_delta_count` from `len(promoted)`.
- `DashboardStateBuilder` keeps rolling cards available while setting
  run-health current count from the current run dictionary.
- `cockpit_renderer.py` now uses current-run count for:
  - hero/deck action framing;
  - decision strip;
  - "Today" timeline card;
  - "Why this priority";
  - semantic recommendation action gating.
- Rolling cards remain inspectable as recent memory/watchlist and in the
  partner selector, but they no longer become today's action when the current
  run is quiet.
- `DASHBOARD_STATE_SCHEMA_VERSION` was bumped from `12` to `13`.
- `scripts/validate_dashboard_clicks.py` now treats quiet current runs as a
  valid E2E state: no priority buttons is acceptable only when the page
  explicitly explains the quiet run and does not show the stale action label.

Local verification:

```text
.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_run_health_separates_current_run_material_count_from_rolling_cards tests/dashboard/test_cockpit_renderer.py::test_quiet_current_run_does_not_label_rolling_cards_as_todays_moves -q
2 passed in 0.09s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py -q
66 passed in 0.18s

.venv/bin/python -m pytest tests/scripts/test_daily_run.py tests/brain/test_prompts.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q
62 passed in 2.10s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m py_compile scripts/validate_dashboard_clicks.py
.venv/bin/python -m pytest -q
688 passed, 18 deselected, 1 warning in 3.26s
```

VPS deployed package evidence:

```text
Backup: /root/.hermes/backups/cios-app-20260711T053444Z-current-vs-rolling-fix
Backup: /root/.hermes/backups/cios-app-20260711T054148Z-quiet-validator-fix

bash -n deploy/cios-daily.sh scripts/daily_production_run.py scripts/verify_hermes_package_contract.py
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_run_health_separates_current_run_material_count_from_rolling_cards tests/dashboard/test_cockpit_renderer.py::test_quiet_current_run_does_not_label_rolling_cards_as_todays_moves tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_publisher.py::test_default_filename_is_versioned_and_tenant_scoped -q
4 passed in 0.39s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py -q
66 passed in 0.25s

.venv/bin/python -m py_compile scripts/validate_dashboard_clicks.py
```

Live Hermes wrapper acceptance:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=38 failed=10 skipped=0 facts=421 deltas=421 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=2
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 217.3s. LLM calls used: 2 / 35
algolia: delivered=True quality=passed errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0']
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live production artifact check:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
HTTP 200
schema_version=13
generated_at=2026-07-11T05:39:07.259936Z
run_material_delta_count=0
current_material_delta_count=0
rolling_material_delta_count=34
competitor_cards=15
monitored_competitors=27
product_market_status=ran runner=quiet scout_artifact_count=20

https://ci.chowmes.com/
HTTP 200
contains "No new material moves were promoted today." = true
contains "0 promoted moves" = true
contains "recent material cards" = true
contains "Act on the top signal" = false
```

Live browser smoke:

```text
PASS live_playwright_quiet_dashboard title=Argus Competitive Intelligence Cockpit sections=7 selector_options=27 checked_briefs=8 selected=Google Vertex AI Search
PASS live_mobile_quiet_smoke
```

Remaining caveat:

- Product-market still ran quiet after producing 20 Scout artifacts. The next
  build slice should explain why product-surface artifacts did or did not
  become feature positions, pattern observations, movement-map cells, or
  recommendations.

## Addendum: Product-Market Conversion Diagnostics

Time: 2026-07-11 05:59 UTC

Problem:

- The product-market chain previously reported `product_market=ran` and
  `scout_artifact_count=20`, but the business read still had no explanation
  for why product-surface artifacts did or did not become product-market
  patterns.
- This preserved the "empty shell" failure mode: the UI showed machinery
  running without exposing the intelligence conversion path.

Package changes:

- Added `ProductMarketConversionDiagnostics` to the product-market runner.
- `run_product_market_payload` now reports:
  - Scout/product record count;
  - converted product event count;
  - derived feature-position count;
  - conversation and demand counts;
  - rising-demand capability count;
  - matched capability count;
  - pattern and recommendation counts;
  - blockers and capability gaps.
- `ProductMarketIntelligenceBrief` persists the same diagnostics inside the
  brain-readable run brief JSON, so the explanation survives DB persistence
  and report metadata rendering.
- `ProductMarketRunStatus` now exposes `conversion_diagnostics` in the
  dashboard contract.
- `cockpit_renderer.py` renders a "Conversion diagnostics" line in the
  Hermes / Argus run trace.
- `DASHBOARD_STATE_SCHEMA_VERSION` was bumped from `13` to `14`.

Local verification:

```text
.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_payload_explains_product_artifacts_without_demand_or_patterns tests/dashboard/test_state_builder.py::test_product_market_run_status_includes_conversion_diagnostics tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area -q
3 passed in 0.12s

.venv/bin/python -m pytest tests/intelligence tests/scripts/test_product_market_runner.py tests/scripts/test_build_product_market_payload.py tests/db/test_product_market_repo.py -q
68 passed in 0.35s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py -q
67 passed in 0.15s

.venv/bin/python -m pytest -q
690 passed, 18 deselected, 1 warning in 3.36s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

VPS deployed package evidence:

```text
Backup: /root/.hermes/backups/cios-app-20260711T054943Z-conversion-diagnostics

bash -n deploy/cios-daily.sh scripts/daily_production_run.py scripts/run_product_market_intelligence.py scripts/verify_hermes_package_contract.py
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_payload_explains_product_artifacts_without_demand_or_patterns tests/dashboard/test_state_builder.py::test_product_market_run_status_includes_conversion_diagnostics tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_publisher.py::test_default_filename_is_versioned_and_tenant_scoped -q
5 passed in 0.44s

.venv/bin/python -m pytest tests/intelligence tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py -q
116 passed in 0.49s
```

Live Hermes wrapper acceptance:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=2
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 274.6s. LLM calls used: 2 / 35
algolia: delivered=True quality=passed errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0', 'prescriptions: skipped by CIOS_ENABLE_PRESCRIPTIONS=0']
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live production artifact check:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
HTTP 200
schema_version=14
generated_at=2026-07-11T05:55:16.933988Z
current_material_delta_count=1
rolling_material_delta_count=35
competitor_cards=15
product_market_status=ran
runner_verdict=quiet
scout_artifact_count=20
conversion_summary=12 Scout/product records converted to 12 product events and 12 feature positions; 0 product-market patterns qualified.
conversion_product_event_count=12
conversion_feature_position_count=12
conversion_pattern_count=0
conversion_blockers=[
  'No tenant-side demand evidence was captured, so product proof could not become a product-market pattern.',
  '12 product capabilities had product proof but no rising demand signal.',
  'No market-conversation evidence was captured for the product artifacts in this run.',
  'Product artifacts did not become patterns because each capability was missing at least one required evidence plane.'
]

https://ci.chowmes.com/
HTTP 200
contains "Conversion diagnostics" = true
```

Live browser smoke:

```text
PASS live_conversion_diagnostics_smoke sections=7 selector_options=27
```

New reading:

- The product muscle is now visible: Scout/product surfaces are producing
  product evidence and feature positions.
- The current product-market reason for `quiet` is no longer mysterious:
  product proof exists, but demand and market-conversation planes are missing
  from the payload, so no cross-plane pattern can qualify.
- The next slice should connect Looker/GA demand exports and/or conversation
  exports into the same daily product-market payload so Argus can produce
  movement patterns when product reality aligns with demand or narrative.

## 2026-07-11 06:44Z -- Conversation Plane Wiring and Synthesis Breadth Repair

Problem found:

- Product-market payloads were built from Scout/product exports and optional
  Looker rows, but the daily sweep's public market conversation evidence was
  not passed into `build_product_market_payload.py`.
- A first fix exported only promoted signals as conversation records. The live
  run passed, but when the day had zero promoted signals, the product-market
  brain still had no conversation plane.
- A second fix exported the current sweep's evidence-backed semantic deltas as
  bounded conversation records. That worked, but it exposed a separate quality
  defect: the daily synthesizer still defaulted to one competitor, allowing a
  quiet brief while the quality reviewer saw apparent AI/conversational signals
  from other competitors in the fetched evidence.
- Increasing synthesis to eight competitors made the job exceed the production
  wrapper's 900 second timeout. The production-safe default was set to four
  competitors, with per-competitor prompt caps unchanged.

Local validation:

```text
python3 -m pytest tests/scripts/test_daily_run.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_build_product_market_payload.py tests/intelligence/test_runner.py -q
70 passed

python3 -m pytest -q
692 passed, 18 deselected

python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T170921Z-dashboard-intelligence-spine.tgz
deployed_dashboard_intelligence_spine=yes

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_intelligence_spine_summarizes_product_conversation_demand_and_actionability tests/dashboard/test_state_builder.py::test_intelligence_spine_exposes_demand_blocker_when_action_is_withheld tests/dashboard/test_publisher.py::test_to_json_dict_serializes_intelligence_spine_contract -q
3 passed in 0.35s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py -q --tb=short
55 passed in 0.20s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Publish and live validation:

```text
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 351351 bytes from live DB state
publish_status published
publish_json /root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public/data/semantic-dashboard.json
published_generated_at 2026-07-11T17:10:48.789830Z
has_intelligence_spine True
spine_planes ['product_reality', 'market_conversation', 'audience_demand']
spine_next_action Upload GA4 / Looker demand export for the current and previous periods.
spine_evidence_count 10

https://ci.chowmes.com/data/semantic-dashboard.json
generated_at 2026-07-11T17:10:48.789830Z
has_intelligence_spine True
planes ['product_reality', 'market_conversation', 'audience_demand']
next_operator_action Upload GA4 / Looker demand export for the current and previous periods.
evidence_count 10

https://ci.chowmes.com/
HTTP/2 200
last-modified: Sat, 11 Jul 2026 17:10:48 GMT
content-length: 351351

https://ci.chowmes.com/data/semantic-dashboard.json
HTTP/2 200
last-modified: Sat, 11 Jul 2026 17:10:48 GMT
content-length: 271349

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS structure: Read, timeline, semantic layer, priority moves, selected competitor, role implications, evidence sections, and Argus assets present
PASS nav_targets: Top nav updates hash/current state and lands on distinct sections
PASS timeline: History controls, holistic coverage, and priority rationale are visible
PASS semantic_layer: Selector, heat map, recommendation, and confidence rubric validated with Google Vertex AI Search
PASS priority_selection: Quiet current run has no priority buttons and shows the no-new-material-moves state
PASS brief_routing: Checked Constructor, Elastic, Algonomy
PASS appendices: Coverage and evidence appendices open and expose brief/source details
PASS viewport_390: 390x844 loaded rebuilt dashboard
PASS viewport_768: 768x1024 loaded rebuilt dashboard
PASS viewport_1280: 1280x900 loaded rebuilt dashboard
PASS dashboard_click_validation
```

VPS deployed package evidence:

```text
Backups:
/root/.hermes/backups/cios-app-20260711T061216Z-current-sweep-conversation
/root/.hermes/backups/cios-app-20260711T063801Z-synthesis-four

/root/.hermes/apps/cios/scripts/daily_production_run.py:212:
  competitors = int(env.get("CIOS_MAX_SYNTH_COMPETITORS", "4"))

/root/.hermes/scripts/cios-daily.sh:49:
  export CIOS_MAX_SYNTH_COMPETITORS="${CIOS_MAX_SYNTH_COMPETITORS:-4}"

.venv/bin/python -m pytest \
  tests/scripts/test_daily_run.py::test_synthesis_settings_are_prompt_bounded_by_default \
  tests/scripts/test_daily_run.py::test_current_sweep_deltas_become_product_market_conversation_records \
  tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_enables_product_market_spine_by_default_and_publishes_same_run_artifacts -q
3 passed in 0.57s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Rejected live attempts and root cause:

```text
Attempt with promoted-signal-only conversation export:
algolia: active_sources=48 attempted=48 fetched=38 failed=10 skipped=0 facts=429 deltas=429 signals=0 verdict=quiet quality=failed fn=clean delivered=False product_market=ran llm=2
ABORT: dashboard publish blocked for algolia; quality_status=failed; synth_verdict=quiet

Quality finding:
Brief claimed "nothing material" while evidence contained apparent Doofinder
AI Assistant and Luigi's Box Conversational Agent narratives. The reviewer
required either window proof or explicit immateriality reasoning.

Attempt with eight synthesis competitors:
exit 124 from `sudo timeout 900 /root/.hermes/scripts/cios-daily.sh`
```

Accepted live Hermes wrapper run:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=421 deltas=421 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 303.3s. LLM calls used: 5 / 35
algolia: delivered=True quality=passed errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0']
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live production artifact check:

```text
https://ci.chowmes.com/
HTTP 200
Last-Modified: Sat, 11 Jul 2026 06:43:37 GMT
contains "Conversion diagnostics" = true
contains "Product-market" = true

https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=14
generated_at=2026-07-11T06:43:37.031444Z
current_material_delta_count=0
rolling_material_delta_count=38
quality_review_status=passed
delivery_status=sent
source_family_count=48
product_market_status=ran
conversation_record_count=80
conversation_theme_count=80
conversation_capability_count=2
product_event_count=16
demand_signal_count=0
matched_capability_count=0
competitor_cards=18
monitored_competitors=27
```

## 2026-07-11 10:55Z -- Demand Export Provenance And Dedupe

Problem:

- Looker / GA demand exports were accepted into the inward-demand plane, but
  canonical rows could enter without row-level provenance.
- Re-running the same export could make demand look stronger than it was if
  identical rows were inserted again.
- That would make Argus recommendations feel more confident than the evidence
  justified.

Package changes:

- `normalize_looker_rows` now adds `source_file`, `source_row_number`, and
  `source_fingerprint` to canonical and raw GA / Looker rows.
- The importer dedupes normalized demand rows by `source_fingerprint` before
  synthesis.
- `DemandSignal` now carries a `metadata` object for row provenance.
- `looker_row_to_demand_signal` copies demand provenance into signal metadata.
- `PgProductMarketRepository.save_demand_signal` updates an existing tenant
  demand row when `metadata->>'source_fingerprint'` matches, instead of blindly
  inserting duplicates.

Local validation:

```text
python3 -m pytest tests/intelligence/test_importers.py::test_build_payload_from_exports_combines_scout_conversation_and_looker_files -q
1 passed

python3 -m pytest tests/intelligence/test_importers.py tests/intelligence/test_adapters.py tests/intelligence/test_input_batch.py tests/intelligence/test_runner.py -q
25 passed

python3 -m pytest tests/db/test_product_market_repo.py tests/db/test_product_market_schema_contract.py -q
19 passed

python3 -m pytest tests/scripts/test_daily_run.py -k "looker or product_market_chain" tests/scripts/test_build_product_market_payload.py tests/scripts/test_product_market_runner.py -q
9 passed, 60 deselected

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
730 passed, 21 deselected
```

VPS verification and live acceptance:

```text
Backup: /root/.hermes/backups/cios-app-20260711T105240Z-demand-read-v16

.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_payload_embeds_demand_read_with_matches_and_provenance tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_publisher.py::test_default_filename_is_versioned_and_tenant_scoped -q
4 passed

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
729 passed, 1 skipped, 21 deselected

sudo timeout 900 /root/.hermes/scripts/cios-daily.sh
algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Run complete in 344.3s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios

https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=16
generated_at=2026-07-11T10:59:08.733399Z
product_market_status=ran
runner_verdict=watch
demand_plane_status=missing
looker_discovered_count=0
looker_normalized_row_count=0
demand_read_summary=No tenant-side demand evidence was captured.
has_demand_read=True
competitors=27
briefs=27

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS dashboard_click_validation
```

## Demand Read Contract

Problem:

- Inward demand was visible as counts and status, but not yet interpreted as
  an Argus read.
- Operators still needed to infer which GA / Looker topics were rising,
  whether those topics matched product proof, and which missing plane blocked
  recommendation promotion.

Package changes:

- `ProductMarketDemandRead` now ranks rising demand topics from normalized
  Looker/GA rows.
- `ProductMarketIntelligenceBrief.demand_read` now records:
  - summary;
  - demand signal count;
  - rising topic count;
  - matched product-topic count;
  - matched conversation-topic count;
  - unmatched demand-topic count;
  - top ranked topics;
  - missing planes per topic;
  - source files, row numbers, and evidence URLs.
- The cockpit run trace renders a compact "Demand read" line from that backend
  contract, including the first demand gap such as a topic needing product
  proof or market conversation.
- `DASHBOARD_STATE_SCHEMA_VERSION` was bumped from `15` to `16`.

Local verification:

```text
python3 -m pytest tests/intelligence/test_runner.py::test_run_product_market_payload_embeds_demand_read_with_matches_and_provenance tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area -q
2 passed

python3 -m pytest tests/intelligence/test_runner.py tests/scripts/test_product_market_runner.py tests/scripts/test_build_product_market_payload.py -q
19 passed

python3 -m pytest tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py -q
70 passed

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

## Product-Market Hermes Stage Heartbeats

The Hermes daily wrapper still had one black-box section: after the normal
daily source sweep, operators could not tell whether the product-market spine
was planning sources, running Scout, preparing demand exports, building the
payload, synthesizing, or archiving input files.

Implemented fix:

- `scripts/daily_production_run.py` now emits flushed structured stage events
  with prefix `CIOS_PRODUCT_MARKET_STAGE`.
- Events include `tenant`, `stage`, `event`, `timestamp`, and `elapsed_s` on
  completed or failed stages.
- Covered stages:
  - `next_sweep_learning_plan`
  - `product_surface_plan`
  - `product_surface_export`
  - `demand_export`
  - `looker_prepare`
  - `product_market_payload`
  - `product_market_synthesis`
  - `looker_archive`
- This is a CI-OS package change only. Hermes core was not modified.

Local RED evidence:

```text
python3 -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats -q
FAILED tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats
AssertionError: assert [] == ['next_sweep_learning_plan', ...]
```

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats -q
1 passed in 0.25s

python3 -m pytest tests/scripts/test_daily_run.py -q -k "product_market_chain or looker or ga4 or product_surface_plan_summary"
10 passed, 55 deselected in 0.26s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest tests/scripts/test_daily_run.py tests/intelligence tests/scripts/test_build_product_market_payload.py tests/scripts/test_product_market_runner.py tests/scripts/test_verify_hermes_package_contract.py -q
139 passed in 0.82s

python3 -m pytest -q
744 passed, 21 deselected in 3.67s
```

VPS deployment:

```text
backup=/root/.hermes/backups/cios-app-20260711T124923Z-product-market-heartbeats

cd /root/.hermes/apps/cios
.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats -q
1 passed in 0.70s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest tests/scripts/test_daily_run.py tests/intelligence tests/scripts/test_build_product_market_payload.py tests/scripts/test_product_market_runner.py tests/scripts/test_verify_hermes_package_contract.py -q
139 passed in 1.15s

.venv/bin/python -m pytest -q
743 passed, 1 skipped, 21 deselected, 1 warning in 4.68s
```

Live Hermes wrapper acceptance:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "next_sweep_learning_plan", "tenant": "algolia", "timestamp": "2026-07-11T12:55:12.123879Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.32, "event": "done", "stage": "next_sweep_learning_plan", "tenant": "algolia", "timestamp": "2026-07-11T12:55:12.443803Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "product_surface_plan", "tenant": "algolia", "timestamp": "2026-07-11T12:55:12.444384Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.4, "event": "done", "stage": "product_surface_plan", "tenant": "algolia", "timestamp": "2026-07-11T12:55:12.843971Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "product_surface_export", "tenant": "algolia", "timestamp": "2026-07-11T12:55:12.844189Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 146.909, "event": "done", "stage": "product_surface_export", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.752955Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "demand_export", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.754192Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.0, "event": "done", "stage": "demand_export", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.754247Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "looker_prepare", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.754324Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.001, "event": "done", "stage": "looker_prepare", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.754938Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "product_market_payload", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.755056Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.19, "event": "done", "stage": "product_market_payload", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.945556Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "product_market_synthesis", "tenant": "algolia", "timestamp": "2026-07-11T12:57:39.946499Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.643, "event": "done", "stage": "product_market_synthesis", "tenant": "algolia", "timestamp": "2026-07-11T12:57:40.589418Z"}
CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "looker_archive", "tenant": "algolia", "timestamp": "2026-07-11T12:57:40.589601Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.0, "event": "done", "stage": "looker_archive", "tenant": "algolia", "timestamp": "2026-07-11T12:57:40.589670Z"}

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 443.5s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Public artifact verification:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
generated_at=2026-07-11T12:57:40.643941Z
schema_version=16
monitored_competitors=27
source_health=48
competitor_cards=4
product_market_status=ran
demand_signals=0
```

Live click validation:

```text
python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS structure
PASS nav_targets
PASS timeline
PASS semantic_layer
PASS priority_selection
PASS brief_routing
PASS appendices
PASS viewport_390
PASS viewport_768
PASS viewport_1280
PASS dashboard_click_validation
```

Remaining gap:

- This does not solve inward demand. Production still has `demand_signals=0`
  because no real GA / Looker export or authenticated analytics connector is
  loaded for the tenant. The next intelligence slice needs to connect a real
  demand feed, then verify that product proof plus market conversation plus
  audience demand can produce a scored recommendation.

## Demand Import Inbox Preview

The demand import path existed, but queued files were blind until the next
Hermes sweep. Operators could upload a GA / Looker export and still not know
whether it was parseable, whether rows normalized into demand signals, or
which topics Argus would see.

Implemented fix:

- `DemandImportStatus` now includes `inbox_previews`.
- Each queued demand file is validated with the same canonical importer used by
  the Hermes product-market runner.
- Preview fields:
  - `status`: `ready`, `empty`, or `error`;
  - `raw_row_count`;
  - `normalized_row_count`;
  - `skipped_row_count`;
  - normalized `topics`;
  - parse error when present.
- Admin HTML now shows a "Queued demand preview" table and a queued-valid-rows
  summary before the next sweep.
- This still does not fake production demand. It only makes the real upload
  inbox auditable before Hermes consumes it.

Local RED evidence:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_returns_argus_demand_import_status tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms -q
FAILED tests/admin/test_app.py::test_json_api_returns_argus_demand_import_status
KeyError: 'inbox_previews'
FAILED tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms
assert 'Queued demand preview' in response.text
```

Local verification:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_returns_argus_demand_import_status tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms tests/admin/test_app.py::test_admin_html_previews_queued_demand_export -q
3 passed in 0.34s

python3 -m pytest tests/admin tests/scripts/test_verify_hermes_package_contract.py -q
32 passed in 1.02s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
745 passed, 21 deselected in 3.90s
```

VPS deployment:

```text
backup=/root/.hermes/backups/cios-app-20260711T130341Z-demand-preview

cd /root/.hermes/apps/cios
.venv/bin/python -m pytest tests/admin tests/scripts/test_verify_hermes_package_contract.py -q
32 passed, 1 warning in 2.24s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
744 passed, 1 skipped, 21 deselected, 1 warning in 4.09s
```

Live demand preview smoke:

```text
# Temporary file created in /root/.hermes/apps/cios/data/looker/algolia/
smoke_preview_present=True
smoke_preview_status=ready
smoke_preview_normalized_rows=1
smoke_preview_topics=['AI Shopping Agent']

smoke_file_removed
```

Remaining gap:

- The tenant still needs a real GA / Looker export or authenticated analytics
  connector. The system can now validate the inbox before the next sweep, but
  no real demand file is currently queued for production ingestion.

## Demand Import Operator Prepare Action

The previous demand-import slice made queued GA / Looker files previewable, but
operators still had to wait for the next Hermes sweep before the files became
normalized product-market artifacts. The next slice adds an explicit prepare
action.

Implemented fix:

- `DemandImportStore.prepare(tenant_slug)` normalizes queued files into the
  product-market workdir.
- The prepare operation writes:
  - `looker-export-manifest.json`;
  - normalized payload files under `looker-normalized/`;
  - per-file statuses: `ready`, `empty`, or `error`.
- It deliberately does **not** archive or delete inbox files. Archiving remains
  owned by the full Hermes product-market run after synthesis succeeds.
- Added JSON endpoint:
  - `POST /api/tenants/{tenant_slug}/argus/demand-imports/prepare`
- Added local admin form action:
  - `POST /admin/{tenant_slug}/argus/demand-imports/prepare`
- This is still a CI-OS package feature. Hermes core was not modified.

Local RED evidence:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_queued_demand_exports_without_archiving tests/admin/test_app.py::test_admin_html_can_prepare_queued_demand_exports -q
FAILED ... assert 404 == 200
FAILED ... assert 404 == 303
```

Local verification:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_queued_demand_exports_without_archiving tests/admin/test_app.py::test_admin_html_can_prepare_queued_demand_exports -q
2 passed in 0.34s

python3 -m pytest tests/admin tests/scripts/test_verify_hermes_package_contract.py -q
34 passed in 1.07s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
747 passed, 21 deselected in 3.61s
```

VPS deployment:

```text
backup=/root/.hermes/backups/cios-app-20260711T130931Z-demand-prepare

cd /root/.hermes/apps/cios
.venv/bin/python -m pytest tests/admin tests/scripts/test_verify_hermes_package_contract.py -q
34 passed, 1 warning in 2.19s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
746 passed, 1 skipped, 21 deselected, 1 warning in 5.49s
```

Live isolated smoke:

```text
prepare_ready_count=1
prepare_error_count=0
prepare_normalized_rows=1
prepare_payload_paths=['/tmp/cios-demand-prepare-smoke-work/algolia/looker-normalized/ga-pages.normalized.json']
prepare_manifest_path=/tmp/cios-demand-prepare-smoke-work/algolia/looker-export-manifest.json
normalized_created=true
raw_file_still_queued=true
isolated_smoke_removed=true
```

Safety correction:

- An earlier smoke used the default `/tmp/cios-product-market` workdir and
  temporarily overwrote the production demand manifest with the smoke manifest.
- Because the real production inbox was empty, the manifest was restored to the
  empty-demand state.

Post-smoke production cleanliness:

```text
production_manifest_discovered=0
production_manifest_ready=0
production_manifest_rows=0
production_inbox_count=0
```

Remaining gap:

- Operators can now upload, preview, and prepare real GA / Looker demand files
  without waiting for the daily sweep. The system still needs either a real
  tenant export in the inbox or authenticated GA4 credentials before Argus can
  produce demand-backed recommendations in production.

## GA4 Demand Export Connector Boundary

Problem:

- The inward demand plane could ingest manual Looker/GA files, but Hermes did
  not yet have a tested package-level command that could fetch GA4 demand rows
  from the Google Analytics Data API.
- Without that boundary, the dashboard could truthfully say "demand missing",
  but it could not become self-feeding from authorized analytics.

Implemented fix:

- Added `src/cios/intelligence/ga4_exporter.py`.
- Added `scripts/export_ga4_demand.py`.
- Added optional package extra `ga4` for `google-analytics-data` and
  `google-auth`.
- Added an env-gated `CIOS_GA4_EXPORT_ENABLED=1` step in
  `scripts/daily_production_run.py`.
- The GA4 export runs before product-market payload build and writes canonical
  demand rows to the same Looker/GA normalization path already used by manual
  exports.
- Google imports and credentials are lazy. The package can still install,
  test, and run with GA4 disabled. No private GA data is fetched unless the
  Hermes environment explicitly supplies the GA4 property, date windows, and
  credentials.

Required live activation settings:

- `CIOS_GA4_EXPORT_ENABLED=1`
- `CIOS_GA4_PROPERTY_ID`
- `CIOS_GA4_CURRENT_START`
- `CIOS_GA4_CURRENT_END`
- `CIOS_GA4_PREVIOUS_START`
- `CIOS_GA4_PREVIOUS_END`
- optional `CIOS_GA4_TOPIC_DIMENSION`
- optional `CIOS_GA4_URL_DIMENSION`
- optional `CIOS_GA4_METRIC`
- optional `CIOS_GA4_CREDENTIALS_JSON`

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_can_export_ga4_demand_before_payload_build -q
1 passed in 0.23s

python3 -m pytest tests/intelligence/test_ga4_exporter.py tests/scripts/test_export_ga4_demand.py tests/scripts/test_verify_hermes_package_contract.py -q
10 passed in 0.42s
```

Remaining boundary:

- Do not enable GA4 live until Arijit explicitly authorizes private analytics
  access and the Hermes env contains the real property id, date windows, and
  credential path outside package/public artifacts.

VPS deploy and live verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T111259Z-ga4-demand-export

VPS focused gate:
.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_can_export_ga4_demand_before_payload_build tests/intelligence/test_ga4_exporter.py tests/scripts/test_export_ga4_demand.py tests/scripts/test_verify_hermes_package_contract.py -q
11 passed in 0.90s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

VPS full suite:
.venv/bin/python -m pytest -q
734 passed, 1 skipped, 21 deselected, 1 warning in 3.66s

GA4 env check:
ga4_enabled=no

Hermes wrapper:
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=5
Competitor briefs written: 27
Run complete in 351.8s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios

Public dashboard JSON:
schema_version=16
generated_at=2026-07-11T11:20:07.871277Z
monitored_competitors=27
source_health=48
product_market_status=ran
demand_plane_status=missing
demand_signal_count=0
run_history_count=5

Live click validation:
PASS dashboard_click_validation

Competitor brief routing:
constructor contains_constructor=yes contains_elastic=no
elastic contains_constructor=no contains_elastic=yes
```

## Active Source To Product Surface Bridge

Problem:

- Product-market muscle still depended too much on the hand-written
  `product_surfaces` seed list.
- The source registry already knew about active docs, changelog, product,
  pricing, API, and integration URLs, but those URLs did not automatically feed
  the Scout product-surface acquisition plan.

Implemented fix:

- Added `product_surface_targets_from_active_sources`.
- Added `seed_product_surfaces_from_active_sources`.
- `run_tenant` now promotes active product-like source rows into
  `product_surfaces` before the Scout plan is built.
- Conversation-only source families such as blog, news, RSS, and forum stay
  out of the product muscle layer.
- Existing operator lifecycle state remains protected because product-surface
  upsert still preserves paused/retired status on conflict.

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py::test_seed_product_surfaces_from_active_sources_promotes_product_like_families -q
1 passed in 0.23s

python3 -m pytest tests/scripts/test_daily_run.py -k "product_surface or product_market_chain or ga4 or looker" -q
13 passed, 50 deselected in 0.21s

python3 -m pytest tests/db/test_product_surface_repo.py tests/scripts/test_plan_product_surface_exports.py tests/scripts/test_execute_product_surface_plan.py tests/scripts/test_export_product_surface_with_scout.py -q
10 passed in 0.51s
```

VPS deploy and live verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T112528Z-product-surface-source-bridge

VPS focused gate:
.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_seed_product_surfaces_from_active_sources_promotes_product_like_families tests/scripts/test_daily_run.py -k "product_surface or product_market_chain or ga4 or looker" -q
13 passed, 50 deselected in 0.61s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

VPS full suite:
.venv/bin/python -m pytest -q
735 passed, 1 skipped, 21 deselected, 1 warning in 3.87s

Hermes wrapper:
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=2 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=5
Competitor briefs written: 27
Run complete in 446.0s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios

Product-surface plan after source-derived seeding:
target_count=36
company_count=14
families={"changelog": 5, "docs": 14, "pricing": 5, "product_page": 12}

Public dashboard JSON:
schema_version=16
generated_at=2026-07-11T11:33:42.542425Z
monitored_competitors=27
source_health=48
product_market_status=ran
target_count=36
scout_artifact_count=33
demand_plane_status=missing
run_history_count=6

Live click validation:
PASS dashboard_click_validation
```

## Product-Muscle Gap Discovery Plan

Problem:

- The dashboard could say 14 of 27 monitored entities had product-muscle
  coverage, but Hermes still needed a machine-readable next action for the
  missing 13.
- A human-readable gap is useful, but it does not tell the next sweep which
  URLs or source families to probe.

Implemented fix:

- Added `build_product_muscle_gap_discovery_plan`.
- After product-market execution, the daily runner now enriches
  `product_market_summary` with `product_muscle_gap_plan`.
- For each monitored competitor without product-surface coverage, the plan
  records:
  - competitor id;
  - company name;
  - domain;
  - active source count;
  - deterministic candidate product-surface URLs for docs, changelog, product,
    pricing, developer/API docs, and integrations.
- The plan is candidate discovery only. Candidate URLs are not evidence until
  validated by the source hunter / Scout path.
- `DashboardState.product_market_run` publishes the plan.
- `rerender_dashboard.py` preserves it when rebuilding from saved dashboard
  JSON.
- The cockpit run trace renders "Product surface discovery plan" with company
  and candidate URL counts.

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py::test_product_muscle_gap_discovery_plan_names_missing_companies_and_candidate_urls -q
1 passed in 0.23s

python3 -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_preserves_last_product_market_run_trace -q
4 passed in 0.15s
```

Full local verification and package contract:

```text
python3 -m pytest tests/scripts/test_daily_run.py -k "product_muscle or product_surface or product_market_chain or ga4 or looker" tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py tests/dashboard/test_cockpit_renderer.py tests/scripts/test_product_market_dashboard_wiring.py -q
14 passed, 124 deselected in 0.29s

python3 -m pytest -q
737 passed, 21 deselected in 3.66s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

VPS deploy and live verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T120040Z-product-muscle-gap-plan
deploy=ok

.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_muscle_gap_discovery_plan_names_missing_companies_and_candidate_urls tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_preserves_last_product_market_run_trace -q
5 passed in 0.91s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
736 passed, 1 skipped, 21 deselected, 1 warning in 3.76s

sudo timeout 900 /root/.hermes/scripts/cios-daily.sh
algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=11
Competitor briefs written: 27
Run complete in 791.5s. LLM calls used: 11 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Public artifact verification:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=16
generated_at=2026-07-11T12:15:06.037692Z
monitored_competitors=27
source_health_rows=48
product_market_status=ran
product_market_runner_verdict=watch
target_count=36
target_company_count=14
target_companies_count=14
surface_family_counts={"changelog": 5, "docs": 14, "pricing": 5, "product_page": 12}
scout_artifact_count=33
demand_plane_status=missing
product_muscle_gap_missing_company_count=13
product_muscle_gap_candidate_url_count=12
product_muscle_gap_candidate_surface_family_counts={"api_docs": 2, "changelog": 2, "docs": 2, "integration": 2, "pricing": 2, "product_page": 2}
product_muscle_gap_first_missing=["Athos Commerce", "Searchspring", "AI Agent Ecosystem", "AWS OpenSearch / CloudSearch", "Algonomy"]

https://ci.chowmes.com/
HTTP/2 200
last-modified: Sat, 11 Jul 2026 12:15:06 GMT
Product surface discovery plan=yes
companies queued=yes
candidate URLs=yes
Hermes / Argus run trace=yes

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS structure
PASS nav_targets
PASS timeline
PASS semantic_layer
PASS priority_selection
PASS brief_routing: Checked Constructor, Elastic, Algonomy
PASS appendices
PASS viewport_390
PASS viewport_768
PASS viewport_1280
PASS dashboard_click_validation
```

## Product-Muscle Gap Discovery Executor

Problem:

- The product-muscle gap plan could name missing companies and candidate URLs,
  but Hermes still needed a package command that could validate those
  candidates and store accepted ones for future Scout acquisition.
- The write path also had to respect operator lifecycle state. Candidate
  discovery must not reactivate a surface that an operator paused or retired.

Implemented fix:

- Added `cios.intelligence.product_muscle_gap_discovery`.
- Added `scripts/execute_product_muscle_gap_discovery.py`.
- Added `PgProductSurfaceRepository.upsert_candidate_target`.
- The command reads either a bare `product_muscle_gap_plan` JSON object or the
  published dashboard JSON shape at
  `product_market_run.product_muscle_gap_plan`.
- Each candidate URL is validated through the existing `SourceValidator`
  boundary. Accepted URLs become `candidate` `product_surfaces`; rejected URLs
  are recorded in the machine-readable summary.
- On conflict, existing `paused` or `retired` product surfaces keep their
  status. Discovery expands coverage proposals; it does not override operator
  decisions.
- The package preflight now requires
  `scripts/execute_product_muscle_gap_discovery.py`.

Red verification:

```text
python3 -m pytest tests/intelligence/test_product_muscle_gap_discovery.py -q
ModuleNotFoundError: No module named 'cios.intelligence.product_muscle_gap_discovery'

python3 -m pytest tests/db/test_product_surface_repo.py::test_upsert_candidate_target_writes_candidate_without_reactivating_operator_paused_rows -q
AttributeError: 'PgProductSurfaceRepository' object has no attribute 'upsert_candidate_target'

python3 -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py -q
FileNotFoundError: scripts/execute_product_muscle_gap_discovery.py
```

Green verification:

```text
python3 -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py tests/intelligence/test_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
11 passed in 0.46s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
740 passed, 21 deselected in 3.56s
```

VPS deploy and live executor verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T122254Z-product-muscle-gap-executor
deploy=ok

.venv/bin/python -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py tests/intelligence/test_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
11 passed in 0.59s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
739 passed, 1 skipped, 21 deselected, 1 warning in 3.88s

.venv/bin/python scripts/execute_product_muscle_gap_discovery.py --tenant-id 1 --gap-plan /root/.hermes/apps/cios/out/argus-dashboard.json --output /root/.hermes/apps/cios/out/product-muscle-gap-discovery-summary.json --fetch-timeout-seconds 8 --fetch-retries 0
candidate_url_count=12
validated_count=2
stored_candidate_count=2
rejected_count=10
stored_candidates=[
  {"surface_id": 222, "company_name": "Athos Commerce", "surface_family": "pricing", "url": "https://athoscommerce.com/pricing", "http_status": 200},
  {"surface_id": 223, "company_name": "Searchspring", "surface_family": "pricing", "url": "https://searchspring.com/pricing", "http_status": 200}
]

DB confirmation:
row=(222, 'Athos Commerce', 'pricing', 'https://athoscommerce.com/pricing', 'candidate', 'product_muscle_gap_plan')
row=(223, 'Searchspring', 'pricing', 'https://searchspring.com/pricing', 'candidate', 'product_muscle_gap_plan')
```

## Product-Muscle Candidate Promotion

Problem:

- The discovery executor could validate missing product-surface URLs and store
  accepted rows as `candidate`, but the next Scout product-surface plan only
  reads `active` rows.
- Without a promotion command, validated candidates stayed stuck between
  discovery and monitoring. The system knew more, but Hermes could not use it
  in the next sweep without manual SQL.

Implemented fix:

- Added `PgProductSurfaceRepository.promote_validated_candidates`.
- Added `scripts/promote_product_surface_candidates.py`.
- Promotion is deliberately narrow:
  - same tenant;
  - `status = 'candidate'`;
  - `metadata.discovered_by` equals the expected discovery source;
  - `metadata.validation.http_status` is 2xx.
- Promotion records `promoted_by`, `promoted_at`, and `promotion_source` in
  metadata.
- The package preflight now requires
  `scripts/promote_product_surface_candidates.py`.

Red verification:

```text
python3 -m pytest tests/db/test_product_surface_repo.py::test_promote_validated_candidates_activates_only_discovery_candidates -q
AttributeError: 'PgProductSurfaceRepository' object has no attribute 'promote_validated_candidates'

python3 -m pytest tests/scripts/test_promote_product_surface_candidates.py -q
FileNotFoundError: scripts/promote_product_surface_candidates.py

python3 -m pytest tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_candidate_promotion_command_missing -q
AssertionError: assert 0 == 2
```

Green verification:

```text
python3 -m pytest tests/scripts/test_promote_product_surface_candidates.py tests/db/test_product_surface_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
12 passed in 0.57s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
743 passed, 21 deselected in 3.85s
```

VPS deploy, bug fix, and live verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T123042Z-product-surface-candidate-promotion
deploy=ok

.venv/bin/python -m pytest tests/scripts/test_promote_product_surface_candidates.py tests/db/test_product_surface_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
12 passed in 0.79s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
742 passed, 1 skipped, 21 deselected, 1 warning in 3.66s

First live promotion attempt:
psycopg.errors.UndefinedFunction: operator does not exist: jsonb || json
LINE 15: metadata = product_surfaces.metadata || $3

Root cause:
promotion metadata was passed as psycopg JSON and merged directly into a jsonb
column. The SQL needed an explicit `::jsonb` cast.

Regression/fix verification:
python3 -m pytest tests/scripts/test_promote_product_surface_candidates.py tests/db/test_product_surface_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
12 passed in 0.49s

python3 -m pytest -q
743 passed, 21 deselected in 3.70s

backup=/root/.hermes/backups/cios-app-20260711T123247Z-candidate-promotion-jsonb-cast
deploy=ok

.venv/bin/python -m pytest tests/scripts/test_promote_product_surface_candidates.py tests/db/test_product_surface_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
12 passed in 0.67s

.venv/bin/python scripts/promote_product_surface_candidates.py --tenant-id 1 --discovery-source product_muscle_gap_plan --promoted-by hermes --output /root/.hermes/apps/cios/out/product-surface-candidate-promotion-summary.json
promoted_count=2
promoted_surfaces=[
  {"surface_id": 222, "company_name": "Athos Commerce", "surface_family": "pricing", "url": "https://athoscommerce.com/pricing"},
  {"surface_id": 223, "company_name": "Searchspring", "surface_family": "pricing", "url": "https://searchspring.com/pricing"}
]

DB confirmation:
row=(222, 'Athos Commerce', 'pricing', 'https://athoscommerce.com/pricing', 'active', 'hermes', 'product_muscle_gap_plan')
row=(223, 'Searchspring', 'pricing', 'https://searchspring.com/pricing', 'active', 'hermes', 'product_muscle_gap_plan')

Post-promotion product-surface plan:
target_count=38
promoted_target={'surface_id': 222, 'company_name': 'Athos Commerce', 'surface_family': 'pricing', 'url': 'https://athoscommerce.com/pricing'}
promoted_target={'surface_id': 223, 'company_name': 'Searchspring', 'surface_family': 'pricing', 'url': 'https://searchspring.com/pricing'}

Hermes wrapper after promotion:
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh
algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Run complete in 380.8s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios

Public artifact after promotion:
generated_at=2026-07-11T12:40:56.200254Z
product_market_status=ran
product_market_runner_verdict=watch
target_count=38
target_company_count=16
target_companies_has_athos=True
target_companies_has_searchspring=True
surface_family_counts={"changelog": 5, "docs": 14, "pricing": 7, "product_page": 12}
product_muscle_gap_missing_company_count=11
product_muscle_gap_candidate_url_count=0

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS dashboard_click_validation
```

## Product-Muscle Coverage Contract

Problem:

- The run summary exposed `target_count` and `scout_artifact_count`, but not
  which monitored companies actually had product-muscle coverage.
- That made `33 Scout artifacts` look stronger than it really was: the live
  product-surface plan covered 14 companies, while the monitored universe had
  27 entities.

Implemented fix:

- `summarize_product_surface_plan` now records:
  - `target_company_count`;
  - `target_companies`;
  - `surface_family_counts`.
- `DashboardState.product_market_run` publishes the same fields in
  `semantic-dashboard.json`.
- The cockpit Hermes/Argus run trace now renders product-muscle coverage
  against the monitored universe and names the first missing entities.

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py::test_product_surface_plan_summary_extracts_learning_prioritized_targets -q
1 passed in 0.31s

python3 -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area -q
3 passed in 0.11s
```

VPS deploy and live verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T114106Z-product-muscle-coverage-contract

VPS focused gate:
.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_surface_plan_summary_extracts_learning_prioritized_targets tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area -q
4 passed in 0.88s

VPS full suite:
.venv/bin/python -m pytest -q
735 passed, 1 skipped, 21 deselected, 1 warning in 3.75s

Hermes wrapper:
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Competitor briefs written: 27
Run complete in 367.4s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios

Public dashboard JSON:
schema_version=16
generated_at=2026-07-11T11:47:58.303377Z
monitored_competitors=27
source_health=48
product_market_status=ran
target_count=36
target_company_count=14
target_companies=["Algolia","Bloomreach","Constructor","Coveo","Doofinder","Elastic","Google Vertex AI Search","Klevu","Lucidworks","Luigi's Box","Meilisearch","Nosto","Typesense","Yext"]
surface_family_counts={"changelog":5,"docs":14,"pricing":5,"product_page":12}
scout_artifact_count=33
demand_plane_status=missing
run_history_count=7

Live page renders:
Product muscle coverage: 14 of 27 monitored entities have product muscle targets.
AI Agent Ecosystem, Algonomy, Athos Commerce, AWS OpenSearch / CloudSearch,
CMSWire Digital Experience, +8 more need product-surface coverage.

Live click validation:
PASS dashboard_click_validation
```

Current honest limitation:

- The product-market brain now receives public conversation evidence and product
  evidence in the same Hermes-run payload.
- It still cannot produce a valid cross-plane product-market recommendation
  because there is no tenant-side demand plane loaded yet:
  `demand_signal_count=0`, `matched_capability_count=0`.
- The next real intelligence layer is Looker/GA demand ingestion plus capability
  normalization, so conversation themes like shopping agents can match product
  capabilities like conversational shopping agent instead of only coexisting in
  the payload.

## Quality-Gate Persistence Repair - 2026-07-11 07:47 UTC

Problem found:

- The daily runner persisted promoted semantic deltas before the quality review
  reached a final verdict.
- The revision loop only applied a revised signal set when the revision
  returned at least one signal. If the correct editorial answer was "drop all
  rejected signals," the original rejected signals could remain in memory.
- A state-only rerender could also lose the current product-market trace
  because it rebuilt from `run_health` without carrying the latest
  `product_market_summary`.

Package changes:

- `scripts/daily_production_run.py`
  - Added `should_apply_quality_revision_result`.
  - Finalizes quality review before persisting published semantic deltas or
    claims.
  - Allows a failed quality review's revision pass to replace the original
    promoted set with an empty set.
  - Blocks prescriptions and thesis updates from rejected promoted signals.
- `scripts/rerender_dashboard.py`
  - Preserves product-market trace from saved dashboard JSON.
  - Falls back to the latest report metadata product-market summary when saved
    JSON has already lost the run trace.
  - Reads that fallback inside `tenant_context` so app-DSN RLS does not hide the
    report metadata.
- Quarantined two pre-fix rows from the failed 07:07 UTC run:
  - `semantic_deltas.id=26311` -> `quality_status='rejected'`
  - `semantic_deltas.id=26312` -> `quality_status='rejected'`
  - `claims.id=51` -> `algolia_response_status='rejected_quality_failed'`

Local validation:

```text
python3 -m pytest tests/scripts/test_daily_run.py -q
54 passed in 0.25s

python3 -m pytest tests/scripts/test_product_market_dashboard_wiring.py -q
4 passed in 0.16s

python3 -m pytest -q
700 passed, 18 deselected in 3.32s

python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied
```

Remote validation:

```text
.venv/bin/python -m pytest tests/scripts/test_product_market_dashboard_wiring.py tests/scripts/test_daily_run.py -q -k 'product_market_summary_from_report_metadata or product_market_run_trace or quality_revision or quality_review_finalizes'
5 passed, 53 deselected in 0.50s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Dashboard Intelligence Spine Contract

Problem addressed:

- Product muscle, market conversation, demand proof, recommendations, and
  evidence gaps were present as separate payload fields, but the UI and Argus
  Command had no single contract explaining the actual brain of the system.
- The dashboard could still become a scatterplot of fields unless the backend
  exposed a coherent `intelligence_spine`: what planes ran, what each plane
  proved, what is actionable, what is blocked, and which evidence URLs support
  the read.

Package-layer changes:

- `src/cios/dashboard/types.py`
  - Added `IntelligencePlaneSummary` and `IntelligenceSpine`.
  - Added `DashboardState.intelligence_spine`.
- `src/cios/dashboard/state_builder.py`
  - Builds the spine from product-market run status, patterns, run history,
    recommendations, demand signals, evidence needs, and feature matrix.
  - Separates product reality, market conversation, audience demand,
    synthesis, and actionability into explicit plane summaries.
  - Marks demand as `missing` when the demand evidence need blocks action.
  - Emits leading entities, leading capabilities, blocked actions, evidence
    URLs, and the next operator action.
- `src/cios/dashboard/__init__.py`
  - Exports the new spine types for package consumers.
- `tests/dashboard/test_state_builder.py`
  - Covers actionable spine construction and demand-blocked spine state.
- `tests/dashboard/test_publisher.py`
  - Covers JSON serialization of the public `intelligence_spine` contract.

Local TDD evidence:

```text
python3 -m pytest tests/dashboard/test_state_builder.py::test_intelligence_spine_summarizes_product_conversation_demand_and_actionability tests/dashboard/test_state_builder.py::test_intelligence_spine_exposes_demand_blocker_when_action_is_withheld -q
2 failed before implementation:
- DashboardState had no intelligence_spine.

python3 -m pytest tests/dashboard/test_state_builder.py::test_intelligence_spine_summarizes_product_conversation_demand_and_actionability tests/dashboard/test_state_builder.py::test_intelligence_spine_exposes_demand_blocker_when_action_is_withheld tests/dashboard/test_publisher.py::test_to_json_dict_serializes_intelligence_spine_contract -q
3 passed in 0.08s

python3 -m pytest tests/dashboard -q --tb=short
121 passed in 0.36s

python3 -m pytest -q --tb=short
802 passed, 21 deselected in 5.39s

python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied
```

## Operator Demand Refresh Action

Problem addressed:

- Demand import and ledger refresh were exposed as two separate admin actions.
  That forced the operator to understand plumbing instead of giving them the
  actual workflow: queue or import inward demand evidence, then ask Argus to
  recompute the product-market read from the evidence ledger.
- The CLI fast lane existed, but the local admin/operator surface did not have
  a single safe action for "prepare demand and refresh Argus."

Package-layer changes:

- `src/cios/admin/app.py`
  - Added JSON action
    `/api/tenants/{tenant_slug}/argus/demand-imports/refresh`.
  - Added HTML action
    `/admin/{tenant_slug}/argus/demand-imports/refresh`.
  - The action prepares queued GA / Looker demand exports, then runs the
    ledger-refresh runner with tenant id, own company name, day window, and
    record limit.
  - The API response returns both the demand import result and the Argus ledger
    refresh summary.
  - The demand import section now exposes `Prepare demand and refresh Argus` as
    the primary operator action, while keeping the lower-level prepare-only and
    ledger-refresh-only controls for debugging.
- `tests/admin/test_app.py`
  - Added JSON and HTML regression coverage for the combined operator action.
  - Extended the admin-page test to require the combined action form.

Local TDD evidence:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_links_to_demand_import_template -q
3 failed before implementation:
- JSON combined action returned 404.
- HTML combined action returned 404.
- Admin page lacked /admin/algolia/argus/demand-imports/refresh and button text.

python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_links_to_demand_import_template -q
3 passed in 0.40s

python3 -m pytest tests/admin/test_app.py tests/scripts/test_import_demand_and_refresh.py -q
44 passed in 1.03s

python3 -m pytest -q
796 passed, 21 deselected in 5.57s

python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T165032Z-admin-demand-refresh.tgz
deployed_admin_demand_refresh=yes

.venv/bin/python -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_links_to_demand_import_template -q
3 passed, 1 warning in 1.01s

.venv/bin/python -m pytest tests/admin/test_app.py tests/scripts/test_import_demand_and_refresh.py -q
44 passed, 1 warning in 2.74s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Admin Demand Refresh Dashboard Publish Hook

Problem addressed:

- The combined demand refresh action prepared inward demand evidence and replayed
  Argus ledgers, but it still stopped before rebuilding and publishing the
  dashboard artifacts. That left a subtle stale-UI failure mode: the backend
  could have fresher intelligence than the screen.
- Dashboard publication logic was duplicated inside
  `scripts/import_demand_and_refresh.py`, which made it awkward for the admin
  package to reuse without importing script code.

Package-layer changes:

- `src/cios/dashboard/artifacts.py`
  - Added shared artifact validation and staged dashboard publication helper.
  - Publishes the same artifact set as the Hermes daily wrapper:
    `index.html`, `brief.html`, `data/semantic-dashboard.json`, `briefs/`, and
    the `/v2` mirror.
- `src/cios/admin/dashboard_refresh.py`
  - Added `AdminDashboardRefreshRunner`.
  - Runs `scripts/rerender_dashboard.py --tenant ... --out-dir ...`.
  - Publishes with `CIOS_PUBLIC_DIR` when configured.
  - Raises a runtime error when rerender fails so the operator action cannot
    claim success against a stale dashboard.
- `src/cios/admin/app.py`
  - The combined JSON and HTML demand refresh actions now call the dashboard
    refresh runner after ledger replay.
  - The JSON response includes `dashboard_refresh`.
  - Failed dashboard refresh returns HTTP 502.
- `scripts/import_demand_and_refresh.py`
  - Reuses the package-level dashboard artifact publisher.
- `tests/admin/test_dashboard_refresh.py`
  - Added runner coverage for rerender+publish and failed rerender.
- `tests/admin/test_app.py`
  - Added coverage that the combined operator action calls the dashboard refresh
    runner and blocks on refresh failure.

Local TDD evidence:

```text
python3 -m pytest tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/admin/test_app.py::test_json_api_blocks_operator_action_when_dashboard_refresh_fails -q
3 failed before implementation:
- create_app() did not accept dashboard_refresh_runner.

python3 -m pytest tests/admin/test_dashboard_refresh.py -q
1 import error before implementation:
- No module named cios.admin.dashboard_refresh.

python3 -m pytest tests/admin/test_dashboard_refresh.py tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/admin/test_app.py::test_json_api_blocks_operator_action_when_dashboard_refresh_fails -q
5 passed in 0.46s

python3 -m pytest tests/admin/test_app.py tests/admin/test_dashboard_refresh.py tests/scripts/test_import_demand_and_refresh.py -q
47 passed in 1.11s

python3 -m pytest -q
799 passed, 21 deselected in 5.68s

python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T165737Z-admin-dashboard-publish-hook.tgz
deployed_admin_dashboard_publish_hook=yes

.venv/bin/python -m pytest tests/admin/test_dashboard_refresh.py tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action tests/admin/test_app.py::test_admin_html_can_prepare_demand_and_refresh_argus_in_one_operator_action tests/admin/test_app.py::test_json_api_blocks_operator_action_when_dashboard_refresh_fails tests/scripts/test_import_demand_and_refresh.py -q
10 passed, 1 warning in 1.12s

.venv/bin/python -m pytest tests/admin/test_app.py tests/admin/test_dashboard_refresh.py tests/scripts/test_import_demand_and_refresh.py -q
47 passed, 1 warning in 3.15s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Fresh Hermes Production Run With Ledger Replay Publish

Problem addressed:

- The deployed dashboard builder could prefer `ledger_refresh_summary`, but the
  latest production report still predated the ledger refresh stage.
- `scripts/rerender_dashboard.py` also preserved the previous public
  `product_market_run` when it existed, which meant a screen-only rerender
  could keep stale public JSON instead of using the reports table as source of
  truth.

Package-layer changes:

- `scripts/rerender_dashboard.py`
  - `run_dict_from_saved_dashboard` now accepts
    `latest_product_market_summary`.
  - The rerender path fetches the latest report metadata and uses it as the
    product-market run source of truth when available.
- `tests/scripts/test_product_market_dashboard_wiring.py`
  - Added a regression test proving rerender prefers the latest report
    `product_market_summary` over a stale saved dashboard trace.

Local TDD evidence:

```text
python3 -m pytest tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_prefers_latest_report_product_market_summary_over_saved_trace -q
1 failed before implementation:
- run_dict_from_saved_dashboard() got an unexpected keyword argument 'latest_product_market_summary'

python3 -m pytest tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_prefers_latest_report_product_market_summary_over_saved_trace -q
1 passed in 0.16s

python3 -m pytest tests/scripts/test_product_market_dashboard_wiring.py tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py -q
57 passed in 0.20s

python3 -m pytest -q
788 passed, 21 deselected in 5.39s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T161813Z-rerender-prefers-report-summary.tgz

.venv/bin/python -m pytest tests/scripts/test_product_market_dashboard_wiring.py tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py -q
57 passed in 0.40s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Fresh Hermes production wrapper run:

```text
PASS: CI-OS Hermes package contract satisfied
product-market schema ready
telegram configured: True
claude-shim health: True (None)

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5

CIOS_PRODUCT_MARKET_STAGE {"event": "start", "stage": "product_market_ledger_refresh", "tenant": "algolia", "timestamp": "2026-07-11T16:27:12.766602Z"}
CIOS_PRODUCT_MARKET_STAGE {"elapsed_s": 0.468, "event": "done", "stage": "product_market_ledger_refresh", "tenant": "algolia", "timestamp": "2026-07-11T16:27:13.234606Z"}

Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 456.2s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Report metadata validation:

```text
report_id 14
report_date 2026-07-11
report_created_at 2026-07-11 16:24:43.217819+00:00
summary_status ran
ledger_refresh_status ran
runner_verdict watch
ledger_verdict watch
ledger_top_insight Doofinder has product proof and public positioning around AI Assistant, but Argus has no tenant-side demand evidence in this run; watch the movement, do not promote action yet.
ledger_learning_ids []
ledger_demand_signal_count 0
```

Live public validation:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
generated_at 2026-07-11T16:27:14.895785Z
schema_version 17
status ran
runner_verdict watch
demand_plane_status missing
top_insight Doofinder has product proof and public positioning around AI Assistant, but Argus has no tenant-side demand evidence in this run; watch the movement, do not promote action yet.
learning_ids []
demand_signal_count 0
conversion_summary 281 Scout/product records converted to 281 product events and 124 feature positions; 2 product-market patterns qualified.
monitored_competitors 27
product_market_history 13
patterns 13

https://ci.chowmes.com/
contains Doofinder: True
contains AI Assistant: True
html_bytes 350920

https://ci.chowmes.com/briefs/algolia/doofinder-2026-07-11.html
status_content_doofinder True
elastic_bleed False
bytes 52322

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS structure: Read, timeline, semantic layer, priority moves, selected competitor, role implications, evidence sections, and Argus assets present
PASS nav_targets: Top nav updates hash/current state and lands on distinct sections
PASS timeline: History controls, holistic coverage, and priority rationale are visible
PASS semantic_layer: Selector, heat map, recommendation, and confidence rubric validated with Google Vertex AI Search
PASS priority_selection: Quiet current run has no priority buttons and shows the no-new-material-moves state
PASS brief_routing: Checked Constructor, Elastic, Algonomy
PASS appendices: Coverage and evidence appendices open and expose brief/source details
PASS viewport_390: 390x844 loaded rebuilt dashboard
PASS viewport_768: 768x1024 loaded rebuilt dashboard
PASS viewport_1280: 1280x900 loaded rebuilt dashboard
PASS dashboard_click_validation
```

## Dashboard Uses Final Ledger Replay Read

Problem addressed:

- The public dashboard state could still prefer `runner_summary`, which is the
  first product-market runner output, even after the Hermes daily loop completed
  a final `ledger_refresh_summary` over durable product, conversation, and
  demand ledgers.
- That made the UI vulnerable to showing an import-only or stale brain read
  instead of the final Argus replay read.

Package-layer changes:

- `src/cios/dashboard/state_builder.py`
  - `_build_product_market_run` now selects the final product-market summary
    from `ledger_refresh_summary` when `ledger_refresh_status` is `ran` or
    `completed`.
  - Falls back to `runner_summary` when ledger replay has not run.
- `tests/dashboard/test_state_builder.py`
  - Added a regression test proving the dashboard uses the ledger replay
    verdict, learning ids, demand count, movement map, intelligence brief, and
    conversion diagnostics.

Local TDD evidence:

```text
python3 -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_prefers_final_ledger_replay_summary -q
1 failed before implementation:
- expected final ledger replay verdict `watch`, got stale runner verdict `actionable`.

python3 -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_prefers_final_ledger_replay_summary -q
1 passed in 0.08s

python3 -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py -q
52 passed in 0.13s

python3 -m pytest -q
787 passed, 21 deselected in 6.09s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T161233Z-dashboard-ledger-refresh-preference.tgz

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_prefers_final_ledger_replay_summary -q
1 passed in 0.31s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py -q
52 passed in 0.20s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Admin Run Console Shows Ledger Replay

Problem addressed:

- Hermes daily execution now runs `product_market_ledger_refresh`, but the
  local admin run-status contract and run console still exposed only the
  first `runner_summary`.
- Operators could not distinguish the import/synthesis verdict from the
  holistic ledger replay verdict without reading raw report metadata.

Package-layer changes:

- `src/cios/admin/types.py`
  - Added `ledger_refresh_status` and `ledger_refresh_summary` to
    `ArgusRunStatus`.
- `src/cios/admin/repository.py`
  - Extracts `ledger_refresh_status` and `ledger_refresh_summary` from the
    latest report's `metadata.product_market_summary`.
- `src/cios/admin/app.py`
  - Run console now displays the ledger replay verdict and top replay insight
    beside the import runner verdict.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/admin/test_repository.py::test_latest_run_status_reads_product_market_summary_from_latest_report_metadata tests/admin/test_app.py::test_json_api_returns_latest_argus_run_status tests/admin/test_app.py::test_admin_page_renders_argus_run_intelligence_history -q
3 failed before implementation:
- ArgusRunStatus had no ledger_refresh_status.
- JSON run-status omitted ledger_refresh_status.
- Admin run console did not render Ledger replay.

.venv/bin/python -m pytest tests/admin/test_repository.py::test_latest_run_status_reads_product_market_summary_from_latest_report_metadata tests/admin/test_app.py::test_json_api_returns_latest_argus_run_status tests/admin/test_app.py::test_admin_page_renders_argus_run_intelligence_history -q
3 passed, 1 warning in 0.40s

.venv/bin/python -m pytest tests/admin -q
38 passed, 1 warning in 0.95s

.venv/bin/python -m pytest -q
786 passed, 21 deselected, 1 warning in 5.13s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T160301Z-admin-ledger-refresh-status.tgz

.venv/bin/python -m pytest tests/admin/test_repository.py::test_latest_run_status_reads_product_market_summary_from_latest_report_metadata tests/admin/test_app.py::test_json_api_returns_latest_argus_run_status tests/admin/test_app.py::test_admin_page_renders_argus_run_intelligence_history -q
3 passed, 1 warning in 0.92s

.venv/bin/python -m pytest tests/admin -q
38 passed, 1 warning in 2.31s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Hermes Daily Ledger Refresh Stage

Problem addressed:

- The ledger refresh brain path existed as a CLI and admin control, but Hermes'
  daily product-market chain did not call it.
- The refresh CLI also needed to consume the same next-sweep learning plan as
  the payload importer, otherwise Argus could learn from a challenged
  recommendation and then ignore that learning during holistic ledger replay.

Package-layer changes:

- `scripts/refresh_product_market_from_ledger.py`
  - Added `--learning-plan`.
  - Added `load_learning_instructions` to read approved next-sweep
    instructions from JSON and pass them into `run_product_market_ledger_refresh`.
- `scripts/daily_production_run.py`
  - Added `product_market_ledger_refresh` Hermes heartbeat stage after
    `product_market_synthesis` and before `looker_archive`.
  - Calls `refresh_product_market_from_ledger.py` with tenant slug, own company
    name, configurable lookback/limit, and the generated learning plan.
  - Returns `ledger_refresh_status` and `ledger_refresh_summary` in the
    product-market run summary.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_product_market_runner.py::test_product_market_ledger_refresh_script_loads_learning_plan_instructions -q
1 failed before implementation:
- refresh_product_market_from_ledger had no load_learning_instructions.

.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_refreshes_ledger_with_learning_plan_after_synthesis -q
1 failed before implementation:
- daily_production_run went from product_market_synthesis to looker_archive.

.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_passes_discovered_looker_drop_folder_exports tests/scripts/test_daily_run.py::test_product_market_chain_runs_plan_execute_payload_and_runner tests/scripts/test_daily_run.py::test_product_market_chain_refreshes_ledger_with_learning_plan_after_synthesis tests/scripts/test_daily_run.py::test_product_market_chain_can_export_ga4_demand_before_payload_build tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats tests/scripts/test_product_market_runner.py::test_product_market_ledger_refresh_script_loads_learning_plan_instructions -q
6 passed in 0.28s

.venv/bin/python -m pytest tests/scripts/test_daily_run.py tests/scripts/test_product_market_runner.py -q
74 passed in 0.24s

.venv/bin/python -m pytest -q
786 passed, 21 deselected, 1 warning in 5.56s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T155843Z-daily-ledger-refresh-stage.tgz

.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_refreshes_ledger_with_learning_plan_after_synthesis tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats tests/scripts/test_product_market_runner.py::test_product_market_ledger_refresh_script_loads_learning_plan_instructions -q
3 passed in 0.70s

.venv/bin/python -m pytest tests/scripts/test_daily_run.py tests/scripts/test_product_market_runner.py -q
74 passed in 0.55s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Live Hermes wrapper acceptance:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=11
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 626.6s. LLM calls used: 11 / 35
algolia: delivered=True quality=passed errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0', 'quality revise pass applied', 'prescriptions: skipped by CIOS_ENABLE_PRESCRIPTIONS=0']
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Final public artifact check after DB cleanup and state-only republish:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=14
generated_at=2026-07-11T07:47:23.172765Z
quality_review_status=passed
delivery_status=sent
current_material_delta_count=1
rolling_material_delta_count=40
monitored_competitors=27
competitor_cards=17
source_health=48
product_market_status=ran
conversation_record_count=80
product_event_count=21
demand_signal_count=0
matched_capability_count=0
run_id=daily-algolia-1783754599
report_id=66

https://ci.chowmes.com/
HTTP/2 200
Last-Modified: Sat, 11 Jul 2026 07:47:23 GMT
contains Argus=true
contains Product-market=true
contains Constructor=true
contains Elastic=true
contains Evidence=true

https://ci.chowmes.com/briefs/algolia/elastic-2026-07-11.html
HTTP/2 200
contains Elastic=true
contains Constructor=false

https://ci.chowmes.com/briefs/algolia/constructor-2026-07-11.html
HTTP/2 200
contains Constructor=true
contains Elastic=false

semantic_deltas:
26311 rejected
26312 rejected
26744 published

latest quality reviews:
daily-algolia-1783754599 passed fix_count=0
daily-algolia-1783754599 failed fix_count=2
```

Remaining honest limitation:

- The system now runs through Hermes, covers all active sources, applies the
  quality revision loop, publishes only quality-passed current signals, and
  preserves product-market trace through state-only rerenders.
- It still has no tenant-side demand plane loaded, so product-market cannot yet
  produce a cross-plane recommendation:
  `demand_signal_count=0`, `matched_capability_count=0`.

## Demand Ingestion Patch

Implemented and deployed a tenant-side demand import path for the
product-market spine.

What changed:

- `src/cios/intelligence/importers.py` now normalizes raw GA / Looker page
  exports into canonical `looker_rows`.
- `scripts/daily_production_run.py` now discovers tenant demand exports from:
  - `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS`
  - `CIOS_PRODUCT_MARKET_LOOKER_EXPORT_DIRS`
  - `<installed-cios-app>/data/looker/<tenant-slug>/`
- The product-market chain now passes every discovered demand export into
  `build_product_market_payload.py --looker` and exposes
  `looker_export_count` plus `looker_paths` in the chain summary.

Accepted raw GA / Looker row shape:

```text
Page title, Page path, Engaged sessions, Engaged sessions previous period,
Period start, Period end, Looker Studio URL
```

Local verification:

```text
python3 -m pytest tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py -q -k "looker or product_market_chain_passes_discovered"
7 passed, 62 deselected in 0.37s

python3 -m pytest tests/intelligence tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py tests/scripts/test_product_market_runner.py -q
116 passed in 0.49s

python3 -m pytest -q
704 passed, 18 deselected in 3.33s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Live deployment evidence:

```text
Backup: /root/.hermes/backups/cios-app-20260711T103248Z-demand-plane-v15

.venv/bin/python -m pytest [focused demand-plane/admin/rerender checks] -q
7 passed, 1 warning in 1.14s

.venv/bin/python -m pytest -q
727 passed, 1 skipped, 21 deselected, 1 warning in 4.55s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python scripts/rerender_dashboard.py --tenant algolia --out-dir /root/.hermes/apps/cios/out
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 320982 bytes from live DB state

https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=15
generated_at=2026-07-11T10:33:46.706365Z
demand_plane_status=missing
looker_discovered_count=0
looker_normalized_row_count=0
product_market_status=ran
runner_verdict=watch
competitors=27
briefs=27

https://ci.chowmes.com/
status=200
has_inward_demand=True
has_looker_prompt=True

python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS dashboard_click_validation
```

## Inward Demand Plane Run Contract

Problem:

- The production brain can already ingest Looker/GA demand exports, but the
  published run contract did not make the inward-demand plane explicit enough.
- A run with zero demand rows could show product-market watch patterns without
  clearly telling the operator whether analytics were missing, empty, errored,
  degraded, or processed.

Package changes:

- `DashboardState.product_market_run` now publishes:
  - `demand_plane_status`
  - `looker_discovered_count`
  - `looker_ready_count`
  - `looker_error_count`
  - `looker_normalized_row_count`
  - `looker_skipped_row_count`
  - `looker_archived_count`
  - `looker_manifest_path`
- `DASHBOARD_STATE_SCHEMA_VERSION` was bumped from `14` to `15`.
- The cockpit run trace now shows `Inward demand: <status>` with normalized
  demand row count and a direct operator prompt when exports are missing.
- Admin `ArgusRunStatus` exposes the same fields, and the admin run console now
  shows inward-demand status next to Product-market chain, Scout artifacts, and
  runner verdict.
- `scripts/rerender_dashboard.py` preserves the same Looker/demand metadata
  when refreshing the screen from saved dashboard state, so a no-fetch rerender
  cannot erase the demand-plane status produced by the full Hermes run.

Local verification:

```text
python3 -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_exposes_demand_plane_readiness tests/dashboard/test_state_builder.py::test_product_market_run_status_marks_processed_demand_plane_when_rows_are_ready tests/dashboard/test_cockpit_renderer.py::test_cockpit_run_trace_shows_missing_demand_plane_as_operator_blocker tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace -q
4 passed in 0.10s

python3 -m pytest tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms tests/admin/test_app.py::test_json_api_returns_latest_argus_run_status -q
2 passed in 0.36s

python3 -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py -q
70 passed in 0.17s

python3 -m pytest tests/admin/test_app.py tests/admin/test_repository.py -q
24 passed in 0.75s

python3 -m pytest tests/scripts/test_daily_run.py -k "looker or product_market_chain" tests/intelligence/test_importers.py tests/intelligence/test_runner.py tests/intelligence/test_product_market_synthesizer.py -q
10 passed, 77 deselected in 0.29s

python3 -m pytest tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_preserves_last_product_market_run_trace -q
1 passed in 0.15s

python3 -m pytest -q
728 passed, 21 deselected in 3.33s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

## Admin Demand Import Surface

The manifest/archive contract made the inward-demand plane real, but operators
still had no usable surface to inspect or feed it. Implemented the local admin
surface for that plane:

- Added `src/cios/admin/demand_imports.py`, a filesystem-backed local admin
  service that reads tenant demand drops under `data/looker/<tenant>/`, latest
  manifest state under `CIOS_PRODUCT_MARKET_WORKDIR` or
  `CIOS_PRODUCT_MARKET_WORK_DIR`, and `_archive` / `_rejected` history.
- Added local-only/admin-token guarded endpoints:
  - `GET /api/tenants/{tenant}/argus/demand-imports`
  - `POST /api/tenants/{tenant}/argus/demand-imports`
- Added the "Demand imports" section to the HTML admin page: upload form,
  queued files, processed files, latest manifest path, ready/error counts,
  normalized row counts, and accepted suffixes.
- Uploads accept only safe `.csv`, `.json`, and `.jsonl` basenames. Path
  traversal and unsupported suffixes are rejected before writing.
- Updated `scripts/verify_hermes_package_contract.py` so a deployed package
  cannot pass Hermes preflight if the admin demand-import module is missing.
- Deployed to `/root/.hermes/apps/cios` with backup:
  `/root/.hermes/apps/cios/.codex-backups/20260711T091009Z-demand-import-admin`.

Local verification:

```text
python3 -m pytest tests/admin/test_app.py tests/scripts/test_verify_hermes_package_contract.py -q
22 passed in 0.70s

python3 -m pytest tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py -q -k "looker or product_market_chain_passes_discovered"
8 passed, 66 deselected in 0.25s

python3 -m pytest tests/admin tests/scripts/test_verify_hermes_package_contract.py tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py -q
97 passed in 0.82s

python3 -m pytest -q
713 passed, 18 deselected in 3.55s
```

VPS verification:

```text
PASS: CI-OS Hermes package contract satisfied
22 passed, 1 warning in 1.37s
status_code 200
drop_folder /root/.hermes/apps/cios/data/looker/algolia
manifest_exists True
ready_count 0
normalized_row_count 0
queued_files 0
```

## Admin Product Muscle Matrix Surface

The product-market spine already persisted `company_feature_positions`, but
the local operator surface did not expose the matrix. Implemented the admin
readout for "who has what" product proof:

- Added `FeatureMatrixAdminRecord` to the local admin typed boundary.
- Added `PgAdminRepository.feature_matrix`, reading
  `company_feature_positions` joined to `feature_capabilities`.
- Added `GET /api/tenants/{tenant}/argus/feature-matrix`.
- Added "Product muscle matrix" to the HTML admin page with capability,
  company, role, position status, confidence, evidence link count, first proof
  URL, and updated timestamp.
- Deployed to `/root/.hermes/apps/cios` with backup:
  `/root/.hermes/apps/cios/.codex-backups/20260711T091719Z-feature-matrix-admin`.

Local verification:

```text
python3 -m pytest tests/admin/test_app.py -q
18 passed in 0.46s

python3 -m pytest tests/admin/test_app.py tests/scripts/test_verify_hermes_package_contract.py tests/db/test_product_market_repo.py tests/dashboard/test_state_builder.py -q
78 passed in 0.87s

python3 scripts/verify_hermes_package_contract.py --app-dir . --skip-python-imports
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
715 passed, 19 deselected in 3.38s
```

Local integration was skipped because the local shell had no database DSN:

```text
CIOS_DATABASE_URL is not set
3 skipped in 0.18s
```

VPS verification:

```text
PASS: CI-OS Hermes package contract satisfied
18 passed, 1 warning in 1.20s

status_code 200
matrix_rows 95
first_capability AI Agent Documentation Access
first_company Constructor
first_status proven

python -m pytest -m integration tests/integration/test_admin_repository.py -q
3 passed in 2.05s
```

## Admin Argus Action Workbench

The product-market spine could persist `argus_recommendations`, and the public
dashboard could render recommendation summaries, but the local operator surface
still did not let an operator work the action ledger directly.

Implemented the admin action-workbench slice:

- Added `RecommendationAdminRecord` and `RecommendationStatusUpdate` to the
  admin typed boundary.
- Added `PgAdminRepository.list_recommendations` and
  `PgAdminRepository.update_recommendation_status`, reading and updating
  `argus_recommendations`.
- Added local-only/admin-token guarded endpoints:
  - `GET /api/tenants/{tenant}/argus/recommendations`
  - `POST /api/tenants/{tenant}/argus/recommendations/{id}/status`
- Added "Argus action workbench" to the HTML admin page with owner, action,
  why-now, scorecard total/summary, first evidence link, status, and action
  controls.
- HTML operators can now accept, mark done, dismiss, or challenge an Argus
  recommendation from the same surface. Challenge forms reuse the existing
  recommendation-challenge recorder so weak reads can enter the learning queue.

Local verification:

```text
python3 -m pytest tests/admin/test_app.py -q
21 passed in 0.58s

python3 -m pytest tests/integration/test_integration_safety.py tests/integration/test_admin_repository.py -q
3 passed, 4 deselected in 0.16s

python3 -m pytest -q
721 passed, 20 deselected in 3.60s
```

VPS deployment and verification:

```text
backup=.codex-backups/20260711T095235Z-argus-action-workbench

.venv/bin/python -m pytest tests/admin/test_app.py tests/integration/test_integration_safety.py -q
24 passed, 1 warning in 1.30s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

Live DB read-only shape check through cios-postgres:
argus_recommendations total=0
argus_recommendations open=0
scorecard/evidence_refs/status columns present=3
```

## Admin Argus Evidence Ledger

The action workbench made recommendations operable, but an empty action ledger
still needed an explanation surface. Implemented the read-only evidence ledger
so operators can inspect the inputs Argus used before a recommendation is
allowed:

- Added typed admin records for product events, conversation themes, demand
  signals, and pattern observations.
- Added `PgAdminRepository.evidence_ledger`, reading:
  - `product_change_events`
  - `conversation_themes`
  - `demand_signals`
  - `pattern_observations`
- Added `GET /api/tenants/{tenant}/argus/evidence-ledger`.
- Added "Argus evidence ledger" to the admin page before the action workbench.
  The section shows product proof, market conversation, audience demand, and
  pattern memory with summaries, weights, observed timestamps, and proof links.
- Each evidence plane has its own empty state, so "no demand rows" is visible
  as an input gap rather than misread as a quiet market.

Local verification:

```text
python3 -m pytest tests/admin/test_app.py -q
23 passed in 0.63s

python3 -m pytest tests/integration/test_integration_safety.py tests/integration/test_admin_repository.py -q
3 passed, 5 deselected in 0.18s

python3 -m pytest -q
723 passed, 21 deselected in 3.87s
```

VPS deployment and verification:

```text
backup=.codex-backups/20260711T100217Z-argus-evidence-ledger

.venv/bin/python -m pytest tests/admin/test_app.py tests/integration/test_integration_safety.py -q
26 passed, 1 warning in 1.44s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

Live DB read-only evidence-plane counts through cios-postgres:
product_change_events=30
conversation_themes=129
demand_signals=0
pattern_observations=0
```

## Outward-Evidence Watch Patterns

The live evidence ledger proved a structural problem: production had product
proof and market conversation rows, but no demand rows and no pattern memory.
The previous synthesizer treated missing demand as a full stop, so outward
evidence disappeared into "quiet" even when a competitor had both product
proof and public positioning.

Implemented a conservative brain change:

- Competitor product proof plus competitor conversation now creates a
  `competitive_pressure` watch pattern when tenant-side demand is missing.
- The watch pattern includes only product/conversation evidence and explicitly
  says that no tenant-side demand was captured.
- No recommendation is created from this condition. Missing demand still
  blocks PMM/Product/Sales action promotion.
- The workflow persists the watch pattern to `pattern_observations`, so Argus
  can remember outward market movement while waiting for GA/Looker demand.

Local verification:

```text
python3 -m pytest tests/intelligence/test_product_market_synthesizer.py tests/intelligence/test_product_market_workflow.py -q
15 passed in 0.08s

python3 -m pytest tests/intelligence/test_product_market_synthesizer.py tests/intelligence/test_product_market_workflow.py tests/scripts/test_product_market_runner.py tests/scripts/test_daily_run.py tests/admin/test_app.py -q
101 passed in 0.74s

python3 -m pytest -q
725 passed, 21 deselected in 3.65s
```

VPS deployment and verification:

```text
backup=.codex-backups/20260711T100613Z-outward-watch-patterns

.venv/bin/python -m pytest tests/intelligence/test_product_market_synthesizer.py tests/intelligence/test_product_market_workflow.py tests/scripts/test_product_market_runner.py -q
17 passed in 0.34s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied

Direct deployed synthesizer smoke:
verdict watch
pattern_count 1
pattern_type competitive_pressure
recommendation_count 0
summary_has_no_demand True
```

### Incident: Unsafe Integration Fixture Ran Against VPS Env

While verifying the feature-matrix repository on the VPS, the integration
fixture was run with the production `CIOS_DATABASE_URL`. That fixture is for
local Docker only and performs `DROP SCHEMA public CASCADE`; it reset the live
CI-OS DB to seed schema and changed the `cios_app` role password to the local
test password.

Root cause:

- `tests/integration/conftest.py` trusted any `CIOS_DATABASE_URL`.
- The fixture documentation said the DSN must be a superuser, but the code did
  not require an explicit test-only opt-in before schema reset.

Recovery:

- Restored `cios_app` role password from the production `CIOS_APP_PASSWORD`
  env without printing the secret.
- Ran the production Hermes wrapper once. It restored the YAML/seed baseline
  but only reached 12 active sources because the DB-only source registry had
  been reset.
- Recovered the active competitor/source registry from the pre-reset dashboard
  artifact:
  `/root/.hermes/backups/cios-app-20260711T050000Z-pre-movement-map/out/argus-dashboard.json`
  which contained 27 monitored competitors and 48 source-health rows.
- Wrote a snapshot of the damaged DB state before source-registry recovery:
  `/root/.hermes/apps/cios/.codex-backups/20260711T093039Z-source-registry-recovery/db-snapshot-before-source-registry-recovery.json`
- Upserted recovered competitors and sources, retired the synthetic integration
  competitors `Admin Test Competitor` and `Feature Matrix Test`, and reran the
  production wrapper.

Guard added:

- `tests/integration/conftest.py` now requires
  `CIOS_ALLOW_SCHEMA_RESET_FOR_TESTS=1` before the schema reset fixture can
  run.
- It also refuses non-loopback database hosts.
- Added `tests/integration/test_integration_safety.py`.
- Deployed the guard to `/root/.hermes/apps/cios` with backup:
  `/root/.hermes/apps/cios/.codex-backups/20260711T093829Z-integration-safety-guard`.

Guard verification on VPS with production env loaded and no opt-in:

```text
tests/integration/test_integration_safety.py
3 passed in 0.02s

python -m pytest -m integration tests/integration/test_admin_repository.py -q -rs
SKIPPED: integration schema reset requires CIOS_ALLOW_SCHEMA_RESET_FOR_TESTS=1
3 skipped in 0.30s
```

Final recovery verification:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh
algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=5
Competitor briefs written: 27
Run complete in 353.9s.
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios

public_generated_at=2026-07-11T09:36:53.776207Z
public_source_health=48
public_monitored_competitors=27
public_competitor_cards=2
public_feature_matrix=28
public_product_market_status=ran

active_competitors=27
active_sources=48
reports=2
source_health_events=60
semantic_deltas=481
feature_positions=28
run_intelligence=2
synthetic_competitors=[
  {"name": "Admin Test Competitor", "status": "retired"},
  {"name": "Feature Matrix Test", "status": "retired"}
]

python3 -m pytest -q
718 passed, 19 deselected in 3.78s
```

VPS verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T084832Z-demand-manifest-archive/changed-files.tgz

.venv/bin/python -m pytest tests/scripts/test_daily_run.py tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_product_market_runner.py -q
76 passed in 0.67s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Production empty-inbox manifest smoke:

```text
manifest_path=/tmp/cios-demand-manifest-smoke/algolia/looker-export-manifest.json
discovered_count=0
ready_count=0
normalized_row_count=0
skipped_row_count=0
payload_paths=[]
manifest={
  "discovered_count": 0,
  "error_count": 0,
  "files": [],
  "normalized_row_count": 0,
  "ready_count": 0,
  "skipped_row_count": 0,
  "tenant": "algolia"
}
```

Live Hermes wrapper acceptance after manifest/archive deployment:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=6
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 464.5s. LLM calls used: 6 / 35
algolia: delivered=True quality=passed errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0', 'prescriptions: skipped by CIOS_ENABLE_PRESCRIPTIONS=0']
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Public artifact verification after the full wrapper run:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
generated_at=2026-07-11T08:58:01.256453Z
schema_version=14
competitor_cards=18
monitored_competitors=27
source_health=48
demand_signals=0
product_market_status=ran
product_market_runner_verdict=quiet
product_market_scout_artifact_count=20
```

Full-run manifest:

```json
{
  "discovered_count": 0,
  "error_count": 0,
  "files": [],
  "normalized_row_count": 0,
  "ready_count": 0,
  "skipped_row_count": 0,
  "tenant": "algolia"
}
```

VPS deployment:

```text
backup=/root/.hermes/backups/cios-app-20260711T075931Z-demand-ingestion/changed-files.tgz

cd /root/.hermes/apps/cios
.venv/bin/python -m pytest tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py -q -k "looker or product_market_chain_passes_discovered"
7 passed, 62 deselected in 0.67s

.venv/bin/python -m pytest tests/intelligence tests/scripts/test_build_product_market_payload.py tests/scripts/test_daily_run.py tests/scripts/test_product_market_runner.py -q
116 passed in 0.73s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Live demand truth after deployment:

```text
looker_export_count=0
public_generated_at=2026-07-11T07:47:23.172765Z
product_market_run.conversion_diagnostics includes:
No tenant-side demand evidence was captured, so product proof could not become
a product-market pattern.
demand_signals.count=0
feature_matrix.count=67
product_market_heatmap.count=0
product_market_patterns.count=0
product_market_history.count=0
product_market_trends.count=0
```

Current limitation:

- The code path exists and is tested locally and on the VPS.
- Production still has no real Looker/GA export in
  `/root/.hermes/apps/cios/data/looker/algolia/`, so the correct current
  behavior is zero demand signals and no demand-backed recommendation.
- Do not seed fake demand into production. A real GA/Looker export or future
  authenticated analytics connector is required before Argus can produce the
  inward-demand side of the intelligence layer.

## Quality Revision Flakiness Repair

A live wrapper run after the demand-ingestion patch failed safely:

```text
algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=2 verdict=signals quality=failed fn=clean delivered=False product_market=ran llm=8
ABORT: dashboard publish blocked for algolia; quality_status=failed; synth_verdict=signals
algolia errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0',
'revision pass error (original failed verdict kept): ReadTimeout: ',
'quality failed; promoted signals withheld from persistence']
```

Root cause:

- The quality revision pass re-synthesized every target as one all-or-nothing
  block.
- One model `ReadTimeout` discarded all revised signals and kept the original
  failed quality verdict.
- A second live run proved the timeout was no longer the only problem: the
  revision could complete, but revised claims still failed quality because the
  model kept unsupported Google/Agent Search context.

Implemented fix:

- `synthesize_quality_revision_targets` isolates revision errors per
  competitor. A timeout for one target no longer throws away successful
  revisions for other targets.
- `should_apply_quality_revision_result` now requires at least one successful
  revision target when the caller supplies `revision_success_count`.
- `should_drop_revised_signals_after_failed_quality` implements
  evidence-or-silence after one failed revision: if revised promoted signals
  still fail quality, Argus drops those signals, re-reviews a quiet/current
  read, and only publishes if that quiet read passes.

Verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py -q -k "quality_revision or drop_revised or quality_review_finalizes"
5 passed, 55 deselected in 0.28s

python3 -m pytest tests/scripts/test_daily_run.py tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py -q
73 passed in 0.29s

python3 -m pytest -q
708 passed, 18 deselected in 3.23s

VPS:
.venv/bin/python -m pytest tests/scripts/test_daily_run.py tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py -q
73 passed in 0.67s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```

Live Hermes wrapper acceptance after the fix:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=39 failed=9 skipped=0 facts=429 deltas=429 signals=2 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=5
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 423.4s. LLM calls used: 5 / 35
algolia: delivered=True quality=passed errors=['own-brand: skipped by CIOS_ENABLE_OWN_BRAND_READ=0', 'prescriptions: skipped by CIOS_ENABLE_PRESCRIPTIONS=0']
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Public artifact verification:

```text
https://ci.chowmes.com/data/semantic-dashboard.json
schema_version=14
generated_at=2026-07-11T08:40:41.689487Z
competitor_cards=18
monitored_competitors=27
source_health=48
demand_signals=0
product_market_status=ran
product_market_runner_verdict=quiet
product_market_scout_artifact_count=20

https://ci.chowmes.com/briefs/algolia/constructor-2026-07-11.html
contains_constructor=True
contains_elastic=False

https://ci.chowmes.com/briefs/algolia/elastic-2026-07-11.html
contains_constructor=False
contains_elastic=True
```

## Demand Manifest And Archive Contract

The first demand-ingestion slice could read Looker/GA exports, but operations
still could not tell the difference between these states:

- no export was present;
- an export was present but had the wrong shape;
- an export normalized into usable demand rows;
- the same drop-folder export would be reprocessed on the next run.

Implemented fix:

- `prepare_product_market_looker_exports` now writes
  `looker-export-manifest.json` into the product-market workdir.
- Every discovered export is recorded with:
  - raw path;
  - whether it came from the tenant drop folder;
  - status: `ready`, `empty`, or `error`;
  - raw row count;
  - normalized row count;
  - skipped row count;
  - normalized payload path when ready.
- The daily product-market payload receives normalized JSON files from
  `looker-normalized/`, not raw user export paths.
- After a successful product-market runner execution, auto-discovered drop
  folder files are moved out of the live inbox:
  - valid files -> `_archive/<timestamp>/`;
  - empty or broken files -> `_rejected/<timestamp>/`;
  - explicit `CIOS_PRODUCT_MARKET_LOOKER_EXPORTS` paths are not moved.

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py -q -k "looker or product_market_chain_passes_discovered or product_market_chain_runs_plan"
4 passed, 57 deselected in 0.24s

python3 -m pytest tests/scripts/test_daily_run.py tests/intelligence/test_importers.py tests/scripts/test_build_product_market_payload.py tests/scripts/test_product_market_runner.py -q
76 passed in 0.31s

python3 -m pytest -q
709 passed, 18 deselected in 3.46s

python3 scripts/verify_hermes_package_contract.py --app-dir .
PASS: CI-OS Hermes package contract satisfied
```
## GA4 Connector Control Plane

The inward-demand plane had file upload and manifest preparation, but it still
did not expose the authenticated GA4 connector as an operator-visible control.
That meant Argus could say "no demand evidence" without showing whether the
analytics connector was disabled, missing credentials, missing property/date
configuration, or actually runnable.

Implemented fix:

- Added `Ga4ExportStatus` and `Ga4ExportRunResult` to the admin typed
  boundary.
- Added `Ga4DemandExportControl` in `src/cios/admin/demand_imports.py`.
  It reports:
  - whether GA4 export is enabled;
  - whether required config is present;
  - whether credentials exist, without returning the credential path;
  - whether the export script exists;
  - date window, dimensions, metric, limit, source URL configured flag, and
    tenant output path.
- Added local-only/admin-token guarded routes:
  - `GET /api/tenants/{tenant}/argus/ga4-export`
  - `POST /api/tenants/{tenant}/argus/ga4-export`
  - `POST /admin/{tenant}/argus/ga4-export`
- The run action calls `scripts/export_ga4_demand.py` with a bounded timeout
  and writes `data/looker/<tenant>/ga4-demand.json`, which is the same inward
  demand inbox the Hermes product-market payload already consumes.
- Credential paths and property values are redacted from API/HTML responses and
  from surfaced error details.
- The admin page now shows a "GA4 connector" block inside Demand imports with
  readiness, missing config, export window, metric/dimension settings, output
  path, and a "Run GA4 export now" button.

Local verification:

```text
python3 -m pytest tests/admin/test_app.py -q -k "ga4"
5 passed, 26 deselected in 0.39s

python3 -m pytest tests/admin/test_app.py -q
31 passed in 0.81s

python3 -m pytest tests/admin tests/scripts/test_export_ga4_demand.py tests/intelligence/test_ga4_exporter.py tests/scripts/test_verify_hermes_package_contract.py -q
43 passed in 1.15s

python3 scripts/verify_hermes_package_contract.py --app-dir . --skip-python-imports
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
752 passed, 21 deselected in 4.16s
```

VPS deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T132317Z-ga4-admin-control.tgz
copied=src/cios/admin,tests/admin

.venv/bin/python -m pytest tests/admin tests/scripts/test_export_ga4_demand.py tests/intelligence/test_ga4_exporter.py tests/scripts/test_verify_hermes_package_contract.py -q
43 passed, 1 warning in 2.70s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
751 passed, 1 skipped, 21 deselected, 1 warning in 4.55s
```

Live GA4 readiness smoke, with no secret values printed:

```text
ga4_status=disabled
ga4_enabled=False
ga4_ready=False
ga4_missing_required=none
ga4_property_configured=False
ga4_credentials_configured=False
ga4_credentials_path_exists=False
ga4_adc_configured=False
ga4_script_path_exists=True
ga4_output_path=/root/.hermes/apps/cios/data/looker/algolia/ga4-demand.json
```

Current blocker:

- The GA4 connector code is deployed and test-covered, but the live tenant has
  not been configured with GA4 property/date/credential environment values.
  Argus therefore correctly reports the inward-demand connector as disabled
  instead of pretending demand evidence exists.

## Product Feature Comparison Read

The product-muscle matrix existed as a list of captured feature positions, but
that still hid a critical business question: which monitored competitors have
no captured proof for a capability? A list of positive rows can make the system
look more confident than it is.

Implemented fix:

- Added `FeatureComparisonState`, `FeatureComparisonCompany`,
  `FeatureComparisonRow`, and `FeatureComparisonCell` to the admin typed
  boundary.
- Added `src/cios/admin/feature_comparison.py`, a pure derived read that
  combines:
  - the tenant competitor registry;
  - the current persisted feature-position matrix;
  - own-company positions already present in the evidence ledger.
- Added `GET /api/tenants/{tenant}/argus/feature-comparison`.
- Added a "Product feature comparison" section to the admin page.
- The comparison now renders cells as `proven`, `claimed`, `gap`,
  `disproven`, or `unknown`.
- `unknown` is deliberately not a product-gap claim. It means Argus has not
  captured product proof for that company/capability in the current evidence
  set.

Local verification:

```text
python3 -m pytest tests/admin/test_app.py -q -k "feature_comparison"
2 passed, 31 deselected in 0.30s

python3 -m pytest tests/admin/test_app.py -q
33 passed in 0.82s

python3 -m py_compile src/cios/admin/types.py src/cios/admin/feature_comparison.py src/cios/admin/app.py

python3 -m pytest tests/admin tests/db/test_product_market_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
53 passed in 1.33s

python3 scripts/verify_hermes_package_contract.py --app-dir . --skip-python-imports
PASS: CI-OS Hermes package contract satisfied

python3 -m pytest -q
754 passed, 21 deselected in 4.21s
```

VPS deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T133047Z-feature-comparison-admin.tgz
copied=src/cios/admin,tests/admin

.venv/bin/python -m pytest tests/admin tests/db/test_product_market_repo.py tests/scripts/test_verify_hermes_package_contract.py -q
53 passed, 1 warning in 2.77s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest -q
753 passed, 1 skipped, 21 deselected, 1 warning in 4.50s
```

Live route smoke against real Algolia tenant data:

```text
GET /api/tenants/algolia/argus/feature-comparison
status_code 200
company_count 29
capability_count 113
proven_cells 115
unknown_cells 3162
first_capability AI Agent Documentation Access

GET /admin?tenant=algolia
status_code 200
has_feature_comparison True
has_unknown True
has_unknown_explanation True
```

Current remaining gap:

- This makes missing product proof visible. It does not yet schedule automatic
  follow-up scans for the highest-value unknown cells. The next product-muscle
  slice should turn high-priority unknown cells into Scout/product-surface
  collection targets, gated by source confidence and tenant demand.

## Product-Muscle Unknown Cell Follow-Up Loop

Problem:

- The product feature comparison correctly exposed `unknown` cells, but Argus
  still treated them as passive UI facts.
- That meant the system could show uncertainty without converting uncertainty
  into the next Hermes collection job.

Implemented fix:

- Extended `build_product_muscle_gap_discovery_plan()` so it now combines:
  - monitored DB competitors;
  - persisted product feature matrix rows;
  - the latest product-market runner summary;
  - demand topics and market-movement hot capabilities.
- Added `feature_unknown_collection_targets` to `product_muscle_gap_plan`.
- Each prioritized unknown target includes competitor, capability,
  normalized capability key, priority score, priority reasons, and candidate
  product-surface URLs.
- Existing missing-company behavior is preserved. Missing companies still
  produce `missing_companies` and `candidate_url_count`; unknown feature cells
  use separate counters:
  - `unknown_feature_cell_count`
  - `prioritized_unknown_cell_count`
  - `feature_unknown_candidate_url_count`
- Updated `execute_product_muscle_gap_discovery()` so it validates both:
  - `missing_companies[].candidate_surface_urls`
  - `feature_unknown_collection_targets[].candidate_surface_urls`
- Stored/rejected candidate summaries now preserve optional target context
  such as `capability_text`, `priority_score`, and `priority_reasons`.
- Updated the Hermes cron wrapper `deploy/cios-daily.sh` so the daily run now
  executes product-muscle gap discovery after `daily_production_run.py` emits
  `argus-dashboard.json` and before public publish.
- The wrapper writes
  `out/product-muscle-gap-discovery-summary.json`.

Local verification:

```text
python3 -m pytest tests/scripts/test_daily_run.py tests/intelligence/test_product_muscle_gap_discovery.py -q -k "product_muscle_gap"
4 passed, 64 deselected in 0.29s

python3 -m pytest tests/deploy/test_cios_daily_wrapper.py -q
7 passed in 1.65s

python3 -m pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_daily_run.py tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_execute_product_muscle_gap_discovery.py tests/scripts/test_verify_hermes_package_contract.py -q
83 passed in 2.46s

python3 -m pytest -q
757 passed, 21 deselected in 4.46s

sh -n deploy/cios-daily.sh
```

VPS deployment and verification:

```text
backup_dir=/root/.hermes/backups/cios-20260711T134037Z-unknown-feature-targets
backup_dir=/root/.hermes/backups/cios-20260711T134037Z-gap-wrapper

.venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_daily_run.py tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_execute_product_muscle_gap_discovery.py tests/scripts/test_verify_hermes_package_contract.py -q
83 passed in 1.60s

.venv/bin/python -m pytest -q
756 passed, 1 skipped, 21 deselected, 1 warning in 4.65s

sh -n deploy/cios-daily.sh
wrapper_syntax_ok
```

Live DB smoke against real Algolia tenant data:

```text
monitored_company_count 27
covered_company_count 16
missing_company_count 11
unknown_feature_cell_count 2753
prioritized_unknown_cell_count 25
feature_unknown_candidate_url_count 150
first_unknown_target.company_name Coveo
first_unknown_target.capability_text Conversational Shopping Agent
first_unknown_target.priority_score 50
first_unknown_target.priority_reasons ["market_movement: Conversational Shopping Agent", "captured_product_proof: Bloomreach, Feature Matrix Test, Luigi's Box"]
```

Superseded gap before the next slice:

- The wrapper default tenant id is `CIOS_PRODUCT_MUSCLE_GAP_TENANT_ID=1`.
  This was correct for the current P0 Algolia deployment but had to become
  tenant-slug resolved before CI-OS could be packaged as a generic
  multi-tenant Hermes extension. The following section resolves this gap.
- Product-muscle gap discovery now stores validated candidate surfaces, but
  the next daily run still has to promote or sweep those candidates through
  the product-surface plan before they become full feature-matrix evidence.

## Tenant-Slug Product-Muscle Gap Discovery

Problem:

- `deploy/cios-daily.sh` still invoked product-muscle gap discovery with
  `CIOS_PRODUCT_MUSCLE_GAP_TENANT_ID=1`.
- That was acceptable only for the current Algolia database, not for a CI-OS
  Hermes package that can move to another Hermes instance or tenant database.
- Live smoke also exposed a loader bug: a bare gap plan containing only
  `feature_unknown_collection_targets` was rejected because the loader only
  recognized `missing_companies` as a valid top-level plan key.

Implemented fix:

- `scripts/execute_product_muscle_gap_discovery.py` now supports either:
  - `--tenant <slug>`
  - `--tenant-id <id>`
- Argparse abbreviation is disabled so `--tenant algolia` cannot be
  misinterpreted as `--tenant-id algolia`.
- `--tenant` resolves the tenant id through the app database with
  `SELECT id FROM tenants WHERE slug = %s`.
- `deploy/cios-daily.sh` now defaults
  `CIOS_PRODUCT_MUSCLE_GAP_TENANT` from `CIOS_DELIVER_TENANT`, falling back to
  `algolia`, and passes `--tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT"`.
- The gap-plan loader now accepts a bare object containing
  `feature_unknown_collection_targets`, not only `missing_companies`.

Local verification:

```text
python3 -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py tests/deploy/test_cios_daily_wrapper.py -q -k "tenant_slug or gap_discovery"
3 passed, 6 deselected in 0.44s

python3 -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py -q -k "bare_unknown_cell_plan"
1 failed before fix:
ValueError: ... does not contain product_muscle_gap_plan

python3 -m pytest tests/scripts/test_execute_product_muscle_gap_discovery.py tests/deploy/test_cios_daily_wrapper.py -q
10 passed in 2.05s

python3 -m pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_execute_product_muscle_gap_discovery.py tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_daily_run.py tests/scripts/test_verify_hermes_package_contract.py -q
85 passed in 2.50s

python3 -m pytest -q
759 passed, 21 deselected in 4.09s
```

VPS deployment and verification:

```text
backup_dir=/root/.hermes/backups/cios-20260711T135044Z-tenant-slug-gap-discovery

sh -n deploy/cios-daily.sh

.venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_execute_product_muscle_gap_discovery.py tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_daily_run.py tests/scripts/test_verify_hermes_package_contract.py -q
85 passed in 1.09s

.venv/bin/python -m pytest -q
758 passed, 1 skipped, 21 deselected, 1 warning in 4.45s
```

Live slug-resolution smoke:

```text
.venv/bin/python scripts/execute_product_muscle_gap_discovery.py \
  --tenant algolia \
  --gap-plan /root/.hermes/apps/cios/out/product-muscle-gap-synthetic-tenant-slug.json \
  --output /root/.hermes/apps/cios/out/product-muscle-gap-synthetic-tenant-slug-summary.json \
  --fetch-timeout-seconds 1 \
  --fetch-retries 0

status completed
candidate_url_count 1
validated_count 0
rejected_count 1
stored_candidate_count 0
first_rejected.company_name Tenant Slug Smoke
first_rejected.capability_text AI Shopping Agent
first_rejected.reason [Errno 111] Connection refused
```

Current remaining gap:

- Product-muscle gap discovery is now tenant-slug safe, but the newly validated
  candidate surfaces still need promotion/sweep wiring so candidate URLs become
  active product-surface monitoring inputs without manual promotion.

## Product-Surface Candidate Promotion Loop

Problem:

- Product-muscle gap discovery could validate candidate product-surface URLs and
  store them as `candidate` rows, but Hermes did not promote those validated
  candidates into the active product-surface monitoring set.
- That left the muscle loop half-open: Argus could decide what to inspect next,
  but Scout/product-surface planning would not automatically include the new
  validated surfaces on the next sweep.

Implemented fix:

- `scripts/promote_product_surface_candidates.py` now supports either:
  - `--tenant <slug>`
  - `--tenant-id <id>`
- Argparse abbreviation is disabled so tenant slug and tenant id cannot be
  confused.
- `--tenant` resolves the database tenant id via `SELECT id FROM tenants WHERE
  slug = %s`.
- `deploy/cios-daily.sh` now runs candidate promotion after product-muscle gap
  discovery and before public publish.
- Promotion defaults:
  - `CIOS_ENABLE_PRODUCT_SURFACE_CANDIDATE_PROMOTION=1`
  - `CIOS_PRODUCT_SURFACE_PROMOTION_TENANT=$CIOS_PRODUCT_MUSCLE_GAP_TENANT`
  - `CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE=product_muscle_gap_plan`
  - `CIOS_PRODUCT_SURFACE_PROMOTED_BY=hermes`
- The wrapper writes
  `out/product-surface-candidate-promotion-summary.json`.
- `scripts/verify_hermes_package_contract.py` now fails if the installed
  wrapper does not call `promote_product_surface_candidates.py`.

Local verification:

```text
python3 -m pytest tests/scripts/test_promote_product_surface_candidates.py tests/deploy/test_cios_daily_wrapper.py -q -k "resolves_tenant_slug or promotes_validated"
2 passed, 8 deselected in 0.43s

python3 -m pytest tests/scripts/test_verify_hermes_package_contract.py -q -k "wrapper_does_not_enable"
1 failed before verifier update:
AssertionError: assert 'wrapper missing product-surface candidate promotion' in result.stderr

python3 -m pytest tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_promote_product_surface_candidates.py tests/deploy/test_cios_daily_wrapper.py -q
17 passed in 2.71s

python3 -m pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_promote_product_surface_candidates.py tests/scripts/test_execute_product_muscle_gap_discovery.py tests/intelligence/test_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py tests/scripts/test_daily_run.py tests/scripts/test_verify_hermes_package_contract.py -q
92 passed in 2.84s

python3 -m pytest -q
761 passed, 21 deselected in 4.65s
```

VPS deployment and verification:

```text
backup_dir=/root/.hermes/backups/cios-20260711T135903Z-candidate-promotion-loop

sh -n deploy/cios-daily.sh
.venv/bin/python -m py_compile scripts/promote_product_surface_candidates.py scripts/verify_hermes_package_contract.py

.venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_promote_product_surface_candidates.py tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_execute_product_muscle_gap_discovery.py tests/intelligence/test_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py tests/scripts/test_daily_run.py -q
92 passed in 1.33s

.venv/bin/python -m pytest -q
760 passed, 1 skipped, 21 deselected, 1 warning in 4.71s
```

Live slug-resolution smoke:

```text
.venv/bin/python scripts/promote_product_surface_candidates.py \
  --tenant algolia \
  --discovery-source product_muscle_gap_plan \
  --promoted-by hermes-smoke \
  --limit 0 \
  --output /root/.hermes/apps/cios/out/product-surface-promotion-tenant-slug-smoke.json

status completed
promoted_count 0
```

Live rollback promotion smoke:

```text
inserted_status candidate
promoted_count 1
status_after_promotion active
promoted_by hermes-smoke
rolled_back true
synthetic_row_count_after_rollback 0
tenant_id 1
```

Current remaining gap:

- Validated candidates now promote into active product-surface monitoring for
  the next run. The next slice should close the same-day feedback gap: after
  promotion, Hermes should either schedule a bounded next-run sweep immediately
  or expose the promoted targets in the run console with a clear "will be swept
  next run" status.

## 2026-07-11 14:11 UTC - Post-run learning loop attached before publish

Problem:

- The Hermes wrapper rendered `argus-dashboard.html` and `argus-dashboard.json`
  before product-muscle gap discovery and product-surface candidate promotion.
- That meant the actual next-sweep learning work happened, but the published
  dashboard could not prove it. The system looked like a static report instead
  of an operating loop.

Change:

- Added `scripts/attach_post_run_summaries.py`.
- Bumped dashboard contract to `schema_version=17`.
- Extended `ProductMarketRunStatus` with:
  - `post_run_product_muscle_gap_discovery`
  - `post_run_product_surface_promotion`
  - `post_run_next_sweep_status`
- `scripts/rerender_dashboard.py` now preserves those fields when rebuilding
  the screen from live DB state.
- The cockpit trust area renders a visible `Post-run learning loop` row.
- `deploy/cios-daily.sh` now runs:
  1. product-muscle gap discovery,
  2. product-surface candidate promotion,
  3. post-run summary attachment,
  4. dashboard rerender,
  5. staged public publish.
- `scripts/verify_hermes_package_contract.py` now fails if the installed
  wrapper omits attach or rerender.

Local RED/GREEN evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_attach_post_run_summaries.py tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_preserves_last_product_market_run_trace tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_publisher.py::test_publish_to_file_writes_readable_json tests/dashboard/test_publisher.py::test_default_filename_is_versioned_and_tenant_scoped tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_applies_product_market_schema_before_daily_runner tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_executes_product_muscle_gap_discovery_before_publish tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_promotes_validated_product_surface_candidates_before_publish tests/scripts/test_verify_hermes_package_contract.py::test_preflight_passes_complete_hermes_package_contract tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_wrapper_does_not_enable_product_market_by_default -q
12 failed, 1 passed before implementation

.venv/bin/python -m pytest tests/scripts/test_attach_post_run_summaries.py tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_preserves_last_product_market_run_trace tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_publisher.py::test_publish_to_file_writes_readable_json tests/dashboard/test_publisher.py::test_default_filename_is_versioned_and_tenant_scoped tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_applies_product_market_schema_before_daily_runner tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_executes_product_muscle_gap_discovery_before_publish tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_promotes_validated_product_surface_candidates_before_publish tests/scripts/test_verify_hermes_package_contract.py::test_preflight_passes_complete_hermes_package_contract tests/scripts/test_verify_hermes_package_contract.py::test_preflight_fails_when_wrapper_does_not_enable_product_market_by_default -q
13 passed in 1.98s

.venv/bin/python -m pytest tests/dashboard/test_publisher.py tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/scripts/test_product_market_dashboard_wiring.py tests/scripts/test_attach_post_run_summaries.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py -q
91 passed in 3.44s

.venv/bin/python -m pytest -q
763 passed, 21 deselected, 1 warning in 5.40s
```

VPS deployment and verification:

```text
backup=/root/.hermes/backups/cios-20260711T141147Z-post-run-loop

bash -n deploy/cios-daily.sh
.venv/bin/python -m pytest [focused post-run loop suite] -q
13 passed in 1.06s

.venv/bin/python -m pytest -q
762 passed, 1 skipped, 21 deselected, 1 warning in 4.55s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios --require-scout --scout-bin /root/.hermes/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Remote positive smoke without publishing:

```text
stored 6
promoted 2
status Hermes queued 6 candidate product surfaces and activated 2 validated sources for the next sweep.

schema_version 17
post_status Hermes queued 6 candidate product surfaces and activated 2 validated sources for the next sweep.
html_has_loop True
```

Current remaining gap:

- The wrapper is now prepared for the next Hermes daily run to publish the
  post-run learning loop. The current remote `out/` artifact is still an older
  `schema_version=16` artifact with no sidecars, so the live site will not show
  the new row until the wrapper runs successfully or we deliberately trigger a
  production daily run.

## 2026-07-11 14:26 UTC - Manual Hermes daily wrapper run published schema 17

Command:

```text
cd /root/.hermes/apps/cios
timeout 900 deploy/cios-daily.sh
```

Run result:

```text
algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=2 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=5
Cockpit written: /root/.hermes/apps/cios/out/argus-dashboard.html
Brief written: /root/.hermes/apps/cios/out/brief.html (+ /root/.hermes/apps/cios/out/argus-dashboard.json)
Competitor briefs written: 27
Run complete in 582.1s. LLM calls used: 5 / 35
```

Post-run loop result:

```text
gap discovery: stored_candidate_count=115, rejected_count=35, candidate_url_count=150
candidate promotion: promoted_count=0
attach: attached post-run summaries to /root/.hermes/apps/cios/out/argus-dashboard.json
rerender: competitor briefs written: 27; cockpit 349082 bytes
publish: dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Live server-side validation:

```text
schema_version 17
generated_at 2026-07-11T14:26:16.809943Z
monitored_competitors 27
source_health 48
competitor_briefs 27
post_status Hermes queued 115 candidate product surfaces for the next sweep.
post_gap_stored 115
post_gap_rejected 35
post_promotion 0
html_has_post_loop True
html_size 348689
```

Live Playwright validation:

```text
PASS live_playwright_validation
schema_version=17
generated_at=2026-07-11T14:26:16.809943Z
post_run_status=Hermes queued 115 candidate product surfaces for the next sweep.
monitored=27 source_health=48
checked_briefs=Constructor,Elastic
```

Opened in-app browser:

```text
https://ci.chowmes.com/?v=20260711T142616#today-read
```

Next trust gap:

- Gap discovery queued 115 candidate surfaces, but the raw sidecar shows many
  guessed URLs, including HTTP 202/empty candidates for Coveo-style pages and
  obvious generic `/docs`, `/product`, `/pricing` guesses. The system now
  reports the loop honestly, but the candidate quality gate is too weak. A
  queued surface should mean "worth a next sweep," not merely "URL guessed and
  not hard-failed."

## 2026-07-11 14:30 UTC - Empty candidate URL responses no longer count as sweepable

Problem:

- Product-muscle gap discovery uses `ProbeFetcherAdapter` to decide whether a
  guessed product surface is reachable enough to queue.
- The adapter treated any successful HTTP fetch as reachable, even when the
  extracted page text was empty.
- This caused HTTP 202 / empty candidate URLs, especially Coveo-style guessed
  surfaces, to be stored as candidate product surfaces.

Change:

- `ProbeFetcherAdapter.fetch()` now returns `reachable=False` with
  `error="empty"` when the full-page fetch succeeds but extracted text is
  blank.
- This keeps candidate discovery aligned with the main source sweep, where
  empty pages are failure/degraded evidence, not useful product proof.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/collect/test_fetcher.py::test_probe_fetcher_adapter_rejects_empty_success_response_as_not_sweepable -q
1 failed before implementation:
assert True is False

.venv/bin/python -m pytest tests/collect/test_fetcher.py tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_execute_product_muscle_gap_discovery.py -q
12 passed in 0.20s

.venv/bin/python -m pytest -q
764 passed, 21 deselected, 1 warning in 5.50s
```

VPS deployment and verification:

```text
backup=/root/.hermes/backups/cios-20260711T143039Z-empty-probe-reject

.venv/bin/python -m pytest tests/collect/test_fetcher.py tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_execute_product_muscle_gap_discovery.py -q
12 passed in 0.51s

.venv/bin/python -m pytest -q
763 passed, 1 skipped, 21 deselected, 1 warning in 4.77s
```

Operational note:

- The already-published live dashboard still reports the just-completed manual
  run's `stored_candidate_count=115`. That is historical truth for that run.
  The stricter empty-response gate will affect the next Hermes daily run.

## 2026-07-11 14:43 UTC - Product muscle gap plan uses source-led evidence only

Problem:

- The post-run product-muscle gap plan still generated generic candidate URLs
  from a competitor domain, such as `/docs`, `/changelog`, `/product`,
  `/pricing`, `/developers`, and `/integrations`.
- Even with reachability validation afterward, that was the wrong intelligence
  posture: Argus should prioritize known monitored product surfaces from the
  source ledger, not guess pages from a company domain.

Change:

- `scripts/daily_production_run.py`
  - Replaced domain-template candidate generation with
    `candidate_product_surface_urls(competitor)`, which only returns active
    monitored source rows whose family maps to a product surface.
  - Added conservative source-family aliases for docs, changelogs, release
    notes, product/platform/solutions pages, pricing, API/developer docs, and
    integrations/marketplace/connectors.
  - Candidate rows now include `evidence_source_family` and
    `evidence_source_status`, so downstream gap discovery can trace why a URL
    was selected.
  - Blog/news/customer/story sources are not promoted into product-muscle
    candidates.
- `src/cios/db/repos/dashboard.py`
  - `PgMonitoredCompetitorsRepository.get_monitored_competitors()` now returns
    a deterministic `monitored_sources` JSONB array of active source rows for
    each competitor.
  - The public dashboard model still ignores this internal field; the field is
    consumed by the daily-run product-muscle planner before rendering.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q -k "product_muscle_gap"
3 failed before implementation because the planner returned generic domain guesses.

.venv/bin/python -m pytest tests/db/test_dashboard_repos.py -q
1 failed before implementation because the repository query did not expose monitored_sources.

.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q -k "product_muscle_gap"
3 passed, 64 deselected in 0.30s

.venv/bin/python -m pytest tests/db/test_dashboard_repos.py -q
2 passed in 0.07s

.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q
67 passed in 0.40s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py tests/scripts/test_product_market_dashboard_wiring.py -q
74 passed in 0.31s

.venv/bin/python -m pytest tests/intelligence/test_product_surface_planner.py tests/intelligence/test_product_muscle_gap_discovery.py tests/db/test_product_surface_repo.py -q
8 passed in 0.31s

.venv/bin/python -m pytest -q
766 passed, 21 deselected, 1 warning in 5.13s
```

VPS deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T144321Z-evidence-gap-plan

.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q -k "product_muscle_gap"
3 passed, 64 deselected in 0.77s

.venv/bin/python -m pytest tests/db/test_dashboard_repos.py -q
2 passed in 0.12s

.venv/bin/python -m pytest -q
765 passed, 1 skipped, 21 deselected, 1 warning in 4.83s

bash -n deploy/cios-daily.sh scripts/daily_production_run.py scripts/verify_hermes_package_contract.py

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Live DB smoke:

```text
algolia_monitored_competitors=27
competitors_with_active_source_arrays=25
evidence_backed_product_like_source_urls=15
gap_plan_candidate_url_count=15
gap_plan_candidate_families={'changelog': 5, 'docs': 4, 'product_page': 6}
```

Operational note:

- The next Hermes daily sweep will no longer queue domain-template product
  muscle candidates. It will only queue product-like active source rows already
  known to the source ledger, then let the existing gap-discovery validator
  decide whether those evidence-backed surfaces are sweepable.

## 2026-07-11 15:12 UTC - Hermes root wrapper and published data-quality repair

Problem:

- Running the actual Hermes cron entrypoint,
  `/root/.hermes/scripts/cios-daily.sh`, published current artifacts but did
  not run the package post-run loop. The root wrapper was stale relative to
  `/root/.hermes/apps/cios/deploy/cios-daily.sh`.
- Live validation showed `post_run_next_sweep_status` was missing after the
  14:55 UTC wrapper run even though the package wrapper had gap discovery,
  candidate promotion, attach, and rerender steps.
- After fixing the wrapper, the post-run status said Hermes "queued 46" even
  when `stored_candidate_count=0` and all 46 candidates were rejected as
  duplicates.
- Public JSON also exposed a retired test fixture row:
  `Feature Matrix Test`.

Root wrapper repair:

```text
backup=/root/.hermes/backups/cios-daily-root-20260711T145638Z-root-wrapper-post-run.sh
root wrapper now includes:
85: execute_product_muscle_gap_discovery.py
113: attach_post_run_summaries.py
118: rerender_dashboard.py

sudo bash -n /root/.hermes/scripts/cios-daily.sh /root/.hermes/apps/cios/deploy/cios-daily.sh
wrapper_syntax_ok

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

sudo cmp -s /root/.hermes/scripts/cios-daily.sh /root/.hermes/apps/cios/deploy/cios-daily.sh
root_wrapper_matches_package_wrapper
```

Corrected Hermes wrapper run:

```text
sudo timeout 900 /root/.hermes/scripts/cios-daily.sh

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
Run complete in 446.3s. LLM calls used: 5 / 35

post-run:
candidate_url_count=46
stored_candidate_count=0
rejected_count=46
promoted_count=0
attached post-run summaries to /root/.hermes/apps/cios/out/argus-dashboard.json
re-rendered cockpit 349833 bytes from live DB state
dashboard published to ci.chowmes.com from /root/.hermes/apps/cios
```

Package fixes:

- `scripts/attach_post_run_summaries.py`
  - No longer falls back from `stored_candidate_count` to
    `candidate_url_count` when saying what was queued.
  - When candidates were found but zero were stored, it now says:
    `Hermes found 46 candidate product surfaces, but none were new sweepable surfaces for the next sweep.`
- `scripts/daily_production_run.py`
  - Feature unknown proof now ignores feature-matrix rows whose company is not
    in the monitored competitor universe for the current run.
- `src/cios/db/repos/product_market.py`
  - `get_feature_matrix()` now publishes only own-company rows or rows joined
    to an active competitor. Retired competitor feature-position residue is no
    longer exposed in the public dashboard.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/scripts/test_attach_post_run_summaries.py::test_attach_post_run_summaries_does_not_claim_queue_when_all_candidates_rejected -q
1 failed before implementation because status said "queued 46".

.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_muscle_gap_discovery_plan_ignores_feature_proof_from_unmonitored_companies -q
1 failed before implementation because unknown_feature_cell_count included test-only fixture rows.

.venv/bin/python -m pytest tests/db/test_product_market_repo.py::test_get_feature_matrix_filters_to_own_company_or_active_competitors -q
1 failed before implementation because the repository did not join/filter active competitors.

.venv/bin/python -m pytest -q
769 passed, 21 deselected, 1 warning in 4.86s
```

Remote verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T150755Z-post-status-feature-filter

.venv/bin/python -m pytest tests/scripts/test_attach_post_run_summaries.py::test_attach_post_run_summaries_does_not_claim_queue_when_all_candidates_rejected tests/scripts/test_daily_run.py::test_product_muscle_gap_discovery_plan_ignores_feature_proof_from_unmonitored_companies -q
2 passed in 1.12s

.venv/bin/python -m pytest tests/scripts/test_attach_post_run_summaries.py tests/scripts/test_daily_run.py -q
71 passed in 1.20s

.venv/bin/python -m pytest tests/db/test_product_market_repo.py tests/dashboard/test_state_builder.py tests/scripts/test_product_market_dashboard_wiring.py -q
61 passed in 0.66s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied
```

Live repair and validation:

```text
recomputed_gap_candidate_url_count 0
recomputed_feature_unknown_candidate_url_count 46
contains_feature_matrix_test False

brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 349870 bytes from live DB state
published_feature_matrix_filter

https://ci.chowmes.com/data/semantic-dashboard.json
schema_version 17
generated_at 2026-07-11T15:11:56.484923Z
monitored_competitors 27
source_health 48
feature_matrix_rows 133
post_status completed
post_candidate_url_count 46
post_stored_candidate_count 0
post_rejected_count 46
post_promotion_count 0
post_run_status Hermes found 46 candidate product surfaces, but none were new sweepable surfaces for the next sweep.
contains_feature_matrix_test False
brief_refs 27

https://ci.chowmes.com/ status=200 last-modified=Sat, 11 Jul 2026 15:11:56 content-length=349870
https://ci.chowmes.com/brief.html status=200 last-modified=Sat, 11 Jul 2026 15:11:56 content-length=57625
https://ci.chowmes.com/briefs/algolia/constructor-2026-07-11.html status=200 last-modified=Sat, 11 Jul 2026 15:11:56 content-length=53748
https://ci.chowmes.com/briefs/algolia/elastic-2026-07-11.html status=200 last-modified=Sat, 11 Jul 2026 15:11:56 content-length=54489

PASS live_playwright_validation structure | nav_targets | semantic_layer:Google Vertex AI Search | post_run_status_and_fixture_filter | brief_routing:Constructor,Elastic,Algonomy | viewport_390 | viewport_768 | viewport_1280
```

Remaining trust gap:

- The status is now truthful, but the phrase "candidate product surfaces" can
  still be confusing because these 46 were all duplicate already-known source
  URLs. The next product-muscle improvement should separate "known evidence
  surfaces rechecked" from "new candidate sources to add" in the UI copy and
  backend contract.

## 2026-07-11 15:20 UTC - Duplicate product-surface rechecks separated from new candidates

Issue:

- The post-run product muscle loop still used "candidate product surfaces" for
  duplicate already-monitored URLs. That was technically true in the transient
  discovery loop, but it was bad operator language: the dashboard could imply
  Hermes found 46 new things when it had only rechecked known product surfaces.

Implementation:

- `src/cios/intelligence/product_muscle_gap_discovery.py`
  - Added `duplicate_source_count` and `new_candidate_rejected_count`.
  - Classifies `duplicate_normalized_url` rejections separately from genuinely
    rejected new candidates.
- `scripts/attach_post_run_summaries.py`
  - Emits the duplicate-specific status:
    `Hermes rechecked 46 already-monitored product surfaces; no new sweepable sources were added for the next sweep.`
- `src/cios/dashboard/cockpit_renderer.py`
  - Added a regression path so the run trace distinguishes duplicate rechecks
    from new candidate queues.

Verification:

```text
.venv/bin/python -m pytest tests/intelligence/test_product_muscle_gap_discovery.py tests/scripts/test_attach_post_run_summaries.py tests/dashboard/test_cockpit_renderer.py::test_cockpit_run_trace_distinguishes_duplicate_rechecks_from_new_candidate_queue -q
8 passed

.venv/bin/python -m pytest -q
772 passed, 21 deselected, 1 warning in 5.13s

backup=/root/.hermes/backups/cios-app-20260711T152003Z-duplicate-recheck-status

remote focused:
8 passed in 0.56s

PASS: CI-OS Hermes package contract satisfied
```

Live validation:

```text
generated_at 2026-07-11T15:20:49.687431Z
post_candidate_url_count 46
duplicate_source_count 46
new_candidate_rejected_count 0
post_stored_candidate_count 0
post_run_status Hermes rechecked 46 already-monitored product surfaces; no new sweepable sources were added for the next sweep.
contains_feature_matrix_test False
```

## 2026-07-11 15:31 UTC - Argus evidence-needs contract for withheld decisions

Issue:

- The live dashboard had real product muscle and pattern memory, but zero
  recommendations because the demand plane was empty. This is the correct
  conservative behavior, but the UI made it feel like an empty shell. Argus
  needed a first-class published contract explaining what evidence is missing,
  what it blocks, and what the operator should provide next.

Implementation:

- `src/cios/dashboard/types.py`
  - Added `ArgusEvidenceNeedSummary`.
  - Added `DashboardState.argus_evidence_needs`.
- `src/cios/dashboard/state_builder.py`
  - Derives evidence needs from persisted `product_market_run_intelligence`
    history:
    - product-market patterns with no demand and no recommendations create a
      `demand` evidence need;
    - conversation without product proof creates a `product_muscle` need;
    - product proof without conversation creates a `conversation` need.
- `src/cios/dashboard/cockpit_renderer.py`
  - Renders "What Argus needs next" under Argus run reads so withheld actions
    have an explicit explanation and next step.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions -q
ImportError before implementation because ArgusEvidenceNeedSummary did not exist.

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_product_market_state_empty_when_no_repo_injected tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions -q
4 passed in 0.12s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py tests/dashboard/test_cockpit_renderer.py tests/scripts/test_product_market_dashboard_wiring.py -q
77 passed in 0.22s

.venv/bin/python -m pytest -q
774 passed, 21 deselected, 1 warning in 5.60s
```

Remote verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T153022Z-argus-evidence-needs.tgz

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions -q
3 passed in 0.43s

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py tests/dashboard/test_cockpit_renderer.py tests/scripts/test_product_market_dashboard_wiring.py tests/scripts/test_verify_hermes_package_contract.py -q
84 passed in 0.84s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

Publish and live validation:

```text
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 350485 bytes from live DB state
published_generated_at 2026-07-11T15:31:31.662296Z
argus_evidence_needs 1
first_need Demand plane missing
feature_matrix 133
patterns 10
recommendations 0

https://ci.chowmes.com/data/semantic-dashboard.json
generated_at 2026-07-11T15:31:31.662296Z
argus_evidence_needs 1
first_need_title Demand plane missing
first_need_plane demand
first_need_blocks ['owner recommendations', 'priority ranking', 'action promotion']
feature_matrix 133
patterns 10
recommendations 0
demand 0

https://ci.chowmes.com/
has_what_argus_needs_next True
has_demand_plane_missing True
has_upload_ga4_looker True
has_argus_logo True
has_old_queue_wrong False
has_feature_matrix_test False

Playwright live smoke:
title Argus Competitive Intelligence Cockpit
hasEvidenceNeeds true
hasDemandMissing true
hasUploadStep true
hasLogo true
```

## 2026-07-11 15:40 UTC - Demand import template and operator schema published

Issue:

- The live cockpit correctly exposed the missing demand plane, but the next
  operator action was still too vague. The system said "Upload GA / Looker"
  without giving the exact accepted shape. That left the demand plane blocked
  by avoidable ambiguity.

Implementation:

- `src/cios/admin/demand_imports.py`
  - Added `DEMAND_IMPORT_TEMPLATE_FIELDS` and
    `DEMAND_IMPORT_TEMPLATE_CSV`.
- `src/cios/admin/app.py`
  - Added local-only endpoint:
    `GET /api/tenants/{tenant_slug}/argus/demand-imports/template`.
  - The endpoint returns `text/csv` with attachment filename
    `argus-demand-template.csv`.
  - Added an admin HTML link: "Download demand template".
- `src/cios/dashboard/types.py`
  - Extended `ArgusEvidenceNeedSummary` with `accepted_input_formats`,
    `required_fields`, and `operator_surface`.
- `src/cios/dashboard/state_builder.py`
  - Demand evidence needs now publish the accepted formats and required
    Looker/GA fields:
    `Page title`, `Page path`, `Engaged sessions`,
    `Engaged sessions previous period`, `Period start`, `Period end`,
    `Looker Studio URL`.
- `src/cios/dashboard/cockpit_renderer.py`
  - The public cockpit now renders `CSV, JSON, JSONL` and the required fields
    beside the missing demand-plane explanation.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions tests/admin/test_app.py::test_json_api_returns_argus_demand_import_template tests/admin/test_app.py::test_admin_html_links_to_demand_import_template -q
4 failed before implementation:
- ArgusEvidenceNeedSummary had no accepted_input_formats.
- Cockpit did not render CSV, JSON, JSONL.
- Template endpoint returned 404.
- Admin HTML did not link to the template.

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions tests/admin/test_app.py::test_json_api_returns_argus_demand_import_template tests/admin/test_app.py::test_admin_html_links_to_demand_import_template -q
4 passed, 1 warning in 0.43s

.venv/bin/python -m pytest tests/admin tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py tests/scripts/test_product_market_dashboard_wiring.py -q
113 passed, 1 warning in 1.02s

.venv/bin/python -m pytest -q
776 passed, 21 deselected, 1 warning in 5.34s
```

Remote verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T153915Z-demand-template-contract.tgz

.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_argus_evidence_needs_explain_withheld_action_when_demand_plane_missing tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_argus_evidence_needs_for_withheld_actions tests/admin/test_app.py::test_json_api_returns_argus_demand_import_template tests/admin/test_app.py::test_admin_html_links_to_demand_import_template -q
4 passed, 1 warning in 1.08s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied

.venv/bin/python -m pytest tests/admin tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py tests/scripts/test_product_market_dashboard_wiring.py -q
113 passed, 1 warning in 2.37s
```

Publish and live validation:

```text
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 350692 bytes from live DB state
published_generated_at 2026-07-11T15:40:09.340326Z
need_title Demand plane missing
need_formats ['csv', 'json', 'jsonl']
need_fields ['Page title', 'Page path', 'Engaged sessions', 'Engaged sessions previous period', 'Period start', 'Period end', 'Looker Studio URL']
operator_surface CI-OS local admin demand imports

https://ci.chowmes.com/data/semantic-dashboard.json
generated_at 2026-07-11T15:40:09.340326Z
title Demand plane missing
formats ['csv', 'json', 'jsonl']
fields ['Page title', 'Page path', 'Engaged sessions', 'Engaged sessions previous period', 'Period start', 'Period end', 'Looker Studio URL']
operator_surface CI-OS local admin demand imports
feature_matrix 133
patterns 10
demand 0

https://ci.chowmes.com/
has_formats True
has_page_title True
has_template_instruction True
has_logo True

Local-only admin template smoke:
template_status 200
template_type text/csv; charset=utf-8
template_disposition attachment; filename=argus-demand-template.csv
template_body Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL
```

## Ledger Refresh Brain Path

Problem addressed:

- The UI could say the demand plane was missing, but after a GA / Looker upload
  there was no focused Argus path to replay stored product, conversation, and
  demand ledgers into a fresh intelligence read without rerunning the full
  outward crawl.
- A demand-only refresh must not duplicate product, conversation, or demand
  source rows. It should save only derived intelligence: pattern observations,
  recommendations, and run intelligence summary.

Package-layer changes:

- `src/cios/db/repos/product_market.py`
  - Added `get_recent_product_events`, `get_recent_conversation_themes`, and
    `get_recent_demand_signals` replay readers.
- `src/cios/intelligence/runner.py`
  - Added `run_product_market_ledger_refresh`.
  - Rehydrates ledger rows into evidence-backed value objects, runs the
    deterministic product-market synthesizer, and persists only derived
    Argus intelligence.
- `src/cios/admin/app.py`
  - Added local-admin JSON and HTML actions:
    `/api/tenants/{tenant_slug}/argus/ledger-refresh`
    and `/admin/{tenant_slug}/argus/ledger-refresh`.
  - Demand imports now show a `Refresh Argus from evidence ledger` control.
- `scripts/refresh_product_market_from_ledger.py`
  - Added a Hermes-callable CLI wrapper for replaying a tenant's ledgers.

Local TDD evidence:

```text
.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_replays_existing_ledgers_without_resaving_inputs tests/db/test_product_market_repo.py::test_get_recent_product_events_reads_replayable_product_ledger_rows tests/db/test_product_market_repo.py::test_get_recent_conversation_themes_reads_replayable_conversation_ledger_rows tests/db/test_product_market_repo.py::test_get_recent_demand_signals_reads_replayable_demand_ledger_rows -q
1 import error before implementation:
- run_product_market_ledger_refresh was missing.

.venv/bin/python -m pytest tests/admin/test_app.py::test_json_api_refreshes_argus_from_evidence_ledger tests/admin/test_app.py::test_admin_html_can_refresh_argus_from_evidence_ledger tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms -q
3 failed before implementation:
- create_app did not accept ledger_refresh_runner.
- Admin HTML did not expose the refresh control.

.venv/bin/python -m pytest tests/scripts/test_product_market_runner.py::test_product_market_ledger_refresh_script_exists_and_imports tests/scripts/test_product_market_runner.py::test_product_market_ledger_refresh_script_resolves_tenant_slug -q
2 failed before implementation:
- scripts/refresh_product_market_from_ledger.py did not exist.

.venv/bin/python -m pytest tests/intelligence/test_runner.py tests/db/test_product_market_repo.py tests/admin/test_app.py tests/scripts/test_product_market_runner.py -q
69 passed, 1 warning in 0.89s

.venv/bin/python -m pytest -q
784 passed, 21 deselected, 1 warning in 5.18s
```

Remote deployment and verification:

```text
backup=/root/.hermes/backups/cios-app-20260711T155303Z-ledger-refresh.tgz

.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_replays_existing_ledgers_without_resaving_inputs tests/db/test_product_market_repo.py::test_get_recent_product_events_reads_replayable_product_ledger_rows tests/db/test_product_market_repo.py::test_get_recent_conversation_themes_reads_replayable_conversation_ledger_rows tests/db/test_product_market_repo.py::test_get_recent_demand_signals_reads_replayable_demand_ledger_rows tests/admin/test_app.py::test_json_api_refreshes_argus_from_evidence_ledger tests/admin/test_app.py::test_admin_html_can_refresh_argus_from_evidence_ledger tests/scripts/test_product_market_runner.py::test_product_market_ledger_refresh_script_exists_and_imports -q
7 passed, 1 warning in 0.93s

.venv/bin/python -m pytest tests/intelligence/test_runner.py tests/db/test_product_market_repo.py tests/admin/test_app.py tests/scripts/test_product_market_runner.py -q
69 passed, 1 warning in 2.62s

.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PASS: CI-OS Hermes package contract satisfied
```

## Demand Import Diagnostics in Admin and Daily Manifest

Problem addressed:

- Demand import failures were still too opaque for an operator. The importer
  knew why rows were skipped, but the local admin screen did not show the
  skipped-row evidence.
- Hermes daily runs were preparing Looker files without preserving the same
  skipped-row diagnostics in the daily manifest.

Production changes:

- `src/cios/admin/app.py`
  - Added a `Demand import diagnostics` table to the local admin demand import
    screen.
  - Shows file, row, reason, missing fields, and available columns.
- `scripts/daily_production_run.py`
  - Daily Looker preparation now uses `diagnose_looker_rows`.
  - Manifest file entries now include `skipped_rows` and
    `duplicate_row_count`.

Verification:

```text
local focused:
pytest tests/scripts/test_daily_run.py::test_prepare_product_market_looker_exports_writes_manifest_and_normalized_files tests/admin/test_app.py::test_admin_html_shows_demand_manifest_skipped_row_diagnostics -q
2 passed in 0.45s

local touched suites:
pytest tests/admin/test_app.py tests/scripts/test_daily_run.py tests/intelligence/test_importers.py -q
131 passed in 1.60s

local full:
pytest -q
874 passed, 21 deselected in 9.18s

remote focused:
.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_prepare_product_market_looker_exports_writes_manifest_and_normalized_files tests/admin/test_app.py::test_admin_html_shows_demand_manifest_skipped_row_diagnostics -q -p no:cacheprovider
2 passed, 1 warning in 1.32s

remote touched suites:
.venv/bin/python -m pytest tests/admin/test_app.py tests/scripts/test_daily_run.py tests/intelligence/test_importers.py -q -p no:cacheprovider
131 passed, 1 warning in 4.82s

remote full:
.venv/bin/python -m pytest -q -p no:cacheprovider
867 passed, 1 skipped, 21 deselected, 1 warning in 10.16s
```

## Latest Ledger Replay Read in Admin Console

Problem addressed:

- The admin run console showed that ledger replay ran, but compressed the
  result into a sentence. Operators still had to inspect raw JSON to see what
  Argus concluded from replayed product, conversation, and demand ledgers.

Production changes:

- `src/cios/admin/app.py`
  - Added `Latest ledger replay read` inside the Argus run console.
  - Shows replay verdict, top insight, primary action, demand read, conversion
    diagnostics, conversion blockers, and product/conversation/demand/pattern/
    recommendation counts from `ledger_refresh_summary`.

Verification:

```text
local focused:
pytest tests/admin/test_app.py::test_admin_page_renders_latest_ledger_replay_brain_trace -q
1 passed in 0.36s

local touched suites:
pytest tests/admin/test_app.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_daily_run.py tests/intelligence/test_importers.py -q
139 passed in 1.67s

local full:
pytest -q
875 passed, 21 deselected in 8.75s

remote focused:
.venv/bin/python -m pytest tests/admin/test_app.py::test_admin_page_renders_latest_ledger_replay_brain_trace -q -p no:cacheprovider
1 passed, 1 warning in 0.99s

remote touched suites:
.venv/bin/python -m pytest tests/admin/test_app.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_daily_run.py tests/intelligence/test_importers.py -q -p no:cacheprovider
139 passed, 1 warning in 4.55s

remote full:
.venv/bin/python -m pytest -q -p no:cacheprovider
868 passed, 1 skipped, 21 deselected, 1 warning in 8.81s
```

## Public Run Trace Ledger Replay Counts

Problem addressed:

- The public cockpit run trace could show the final Argus replay read as prose,
  but did not explicitly expose the replayed evidence counts. That made the
  public screen less inspectable than the admin console.

Production changes:

- `src/cios/dashboard/types.py`
  - Added product/conversation/demand/pattern/recommendation replay counts to
    `ProductMarketRunStatus`.
- `src/cios/dashboard/state_builder.py`
  - Preserves those counts from the final runner or ledger replay summary,
    with conversion-diagnostic fallbacks.
- `src/cios/dashboard/cockpit_renderer.py`
  - Renders `Ledger replay read` in the Hermes / Argus run trace.
- `tests/dashboard/test_state_builder.py`,
  `tests/dashboard/test_cockpit_renderer.py`, and
  `tests/dashboard/test_publisher.py`
  - Cover state, HTML, and JSON serialization.

Verification:

```text
local focused:
pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_prefers_final_ledger_replay_summary tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace -q
3 passed in 0.09s

local dashboard suite:
pytest tests/dashboard -q
124 passed in 0.37s

local package contract:
python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS
PASS: CI-OS Hermes package contract satisfied

local full:
pytest -q
875 passed, 21 deselected in 8.92s

remote focused:
.venv/bin/python -m pytest tests/dashboard/test_state_builder.py::test_product_market_run_status_prefers_final_ledger_replay_summary tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_product_market_run_trace_in_trust_area tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace -q -p no:cacheprovider
3 passed in 0.54s

remote dashboard suite:
.venv/bin/python -m pytest tests/dashboard -q -p no:cacheprovider
124 passed in 0.99s

remote package contract:
PASS: CI-OS Hermes package contract satisfied

remote full:
.venv/bin/python -m pytest -q -p no:cacheprovider
868 passed, 1 skipped, 21 deselected, 1 warning in 8.69s

live publish:
re-rendered cockpit 357669 bytes from live DB state
attached operator handoff to dashboard for tenant_id=1
published to /root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public

live endpoint smoke:
https://ci.chowmes.com/ 200 358875 text/html
html_has_ledger True
html_has_handoff True
https://ci.chowmes.com/data/semantic-dashboard.json 200 298045 application/json
generated_at 2026-07-11T21:20:06.882662Z
run_counts {'product_event_count': 318, 'conversation_theme_count': 500, 'demand_signal_count': 0, 'pattern_count': 2, 'recommendation_count': 0}
handoff blocked_on_evidence not_actionable

live click validation:
PASS dashboard_click_validation
```

## 2026-07-11 18:35 ET - Actual Hermes scheduler path repaired

Problem:

- The host-side package looked healthy, but the active runtime is the `hermes`
  container where host `/root/.hermes` is mounted as `/opt/data`.
- The actual Hermes cron job `cios-v2-daily` runs
  `/opt/data/scripts/cios-daily.sh`, not an ad hoc root shell path.
- The scheduler had two real runtime blockers:
  - CI-OS app/output files and public dashboard brief directories were partly
    root-owned, so the `hermes` user could not clean or republish them.
  - The active container venv did not have CI-OS runtime dependencies installed,
    so the package contract failed as the `hermes` user with missing `psycopg`.
- The existing `cron.script_timeout_seconds=360` was below the real daily loop
  budget once product-market extraction runs.

Repair:

```text
/opt/data/scripts/cios-daily.sh now matches /opt/data/apps/cios/deploy/cios-daily.sh
/opt/data/apps/cios ownership restored to hermes:hermes
/opt/data/apps/algolia-competitive-intelligence/apps/dashboard/public ownership restored to hermes:hermes
/opt/data/apps/cios/.venv installed with the CI-OS package runtime dependencies
/opt/data/config.yaml cron.script_timeout_seconds=1200
```

Verification:

```text
container package contract as hermes:
PASS: CI-OS Hermes package contract satisfied

container wrapper tests as hermes:
27 passed

forced Hermes cron:
hermes cron run 107e64d347d9
hermes cron tick

Hermes scheduler status:
Last run: 2026-07-11T18:35:58.479350-04:00  ok

cron output:
active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5
product_surface_export elapsed_s=145.442
Run complete in 377.5s. LLM calls used: 5 / 35
dashboard published to ci.chowmes.com from /opt/data/apps/cios

public artifacts:
index.html 364838 bytes hermes:hermes
data/semantic-dashboard.json 367224 bytes hermes:hermes
brief.html 57621 bytes hermes:hermes

live payload:
schema_version=18
generated_at=2026-07-11T22:35:57.365715Z
product_market_run.status=ran
product_market_run.runner_verdict=watch
product_event_count=393
conversation_theme_count=500
demand_signal_count=0
pattern_count=2
recommendation_count=0

live click validation:
PASS dashboard_click_validation
```

Remaining gaps:

- Inward demand is still absent: `demand_signal_count=0`.
- The product-market loop works but is still a monolith. Split Hermes execution
  into durable stages next: source sweep, product-muscle extraction, inward
  demand import, synthesis, learning, and publish.

## 2026-07-12 UTC - Daily wrapper made publish-safe again

Follow-up failure modes found from the real wrapper:

- A package sync had removed `/opt/data/apps/cios/.venv`; the wrapper therefore
  failed at `.venv/bin/python`.
- Live Postgres rejected run-stage metadata updates because `Json(...)`
  parameters were concatenated into `jsonb` columns without `::jsonb` casts.
- Sunday weekly cadence code ran after daily completion and could consume the
  wrapper timeout before the dashboard publish step.
- Clean quiet runs with no promoted claims still depended on the LLM quality
  reviewer, making quiet publish vulnerable to model variance.

Repairs:

- Recreated `/opt/data/apps/cios/.venv` and installed the CI-OS package runtime
  dependencies.
- Patched `PgRunStageRepository.finish_stage()` and `finish_ledger()` to cast
  metadata parameters to `jsonb`.
- Patched `_deliver_cadence_report()` to construct tenant-scoped
  `QualityReview` objects.
- Made weekly/monthly rollups opt-in with
  `CIOS_ENABLE_WEEKLY_ROLLUP` / `CIOS_ENABLE_MONTHLY_ROLLUP`.
- Patched the quality reviewer so `quiet_verdict=True`, no claims, and clean
  coverage passes deterministically without an LLM call.

Verification:

```text
local full:
913 passed, 21 deselected, 1 warning

remote full:
912 passed, 1 skipped, 21 deselected, 1 warning

remote package contract:
PASS: CI-OS Hermes package contract satisfied

actual wrapper:
timeout 900 /opt/data/scripts/cios-daily.sh
exit 0
active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=4
Run complete in 368.1s. LLM calls used: 4 / 35
Competitor briefs written: 27
dashboard published to ci.chowmes.com from /opt/data/apps/cios

live payload:
schema_version=19
generated_at=2026-07-12T00:56:51.390569Z
monitored_competitors=27
product_market_run.status=ran
product_market_stage_count=11

live click validation:
PASS dashboard_click_validation
```

Operational status:

- No leftover `cios-daily` / `daily_production_run` processes remained after
  the wrapper exited.
- Hermes cron `cios-v2-daily` still points to `cios-daily.sh`, next scheduled
  for `2026-07-12T09:00:00-04:00`.

## 2026-07-12 UTC - Product-muscle source rows and post-run trace preserved

Problem found:

- The dashboard repository exposed active source rows as `monitored_sources`,
  but the dashboard state model discarded them.
- The product-muscle gap planner therefore published missing-coverage plans
  with no evidence-backed candidate URLs, even though active docs/changelog
  product-like sources existed in Postgres.
- After the real wrapper ran, `attach_post_run_summaries.py` attached the
  post-run product-muscle discovery summary, but `rerender_dashboard.py`
  replaced it with report metadata that did not yet contain those sidecar
  fields.

Repairs:

- Added `MonitoredCompetitor.monitored_sources` to the dashboard state
  contract and bumped dashboard JSON to `schema_version=20`.
- Added regression tests proving the field survives through state build and
  publisher JSON.
- Patched rerender so latest report metadata still wins for the Argus read,
  while post-run sidecar fields are preserved from the saved dashboard when
  report metadata lacks them.

Verification:

```text
local full:
916 passed, 21 deselected, 1 warning

remote focused:
10 dashboard/source-row tests passed
1 rerender post-run sidecar test passed

actual wrapper:
timeout 900 /opt/data/scripts/cios-daily.sh
exit 0
Run complete in 688.5s. LLM calls used: 9 / 35
dashboard published to ci.chowmes.com from /opt/data/apps/cios

live payload after rerender tail:
generated_at=2026-07-12T01:25:24.814854Z
schema_version=20
monitored_with_source_rows=25
feature_unknown_candidate_url_count=47
post_gap_status=completed
post_gap_candidate_url_count=47
post_gap_duplicate_source_count=47
post_gap_stored_candidate_count=0
post_promotion_status=completed
post_promotion_promoted_count=0
post_run_next_sweep_status=Hermes rechecked 47 already-monitored product surfaces; no new sweepable sources were added for the next sweep.

live click validation:
PASS dashboard_click_validation

process check:
no_cios_daily_processes
```

Meaning:

- Argus can now carry monitored source URLs from the registry into the
  product-muscle planning loop.
- The latest post-run loop found 47 product-surface checks, but all were
  duplicates of already monitored URLs, so no new surfaces were stored or
  promoted.
- Demand remains the blocking plane: `demand_plane_status=missing`.

## 2026-07-12 UTC - Demand readiness contract deployed

Problem found:

- The live run correctly marked `demand_plane_status=missing`, but Argus did
  not publish a structured readiness answer for the inward plane.
- Operators could see that demand was missing, but not whether Hermes should
  run GA4, prepare a queued manual export, repair a bad export, or ask for
  configuration.

Repairs:

- Added `scripts/export_argus_demand_readiness.py`.
- Added `product_market_run.demand_readiness` to the dashboard payload and
  bumped public JSON to `schema_version=21`.
- Patched the production wrapper to run the readiness export, require
  `out/argus-demand-readiness.json`, attach it into dashboard JSON, and publish
  it with the same state as the cockpit.
- Updated package preflight and deploy wrapper tests so missing readiness
  wiring fails before publication.

Verification:

```text
local full:
920 passed, 21 deselected, 1 warning

remote focused:
50 passed
PASS: CI-OS Hermes package contract satisfied

actual wrapper:
timeout 900 /opt/data/scripts/cios-daily.sh
exit 0
Run complete in 660.0s. LLM calls used: 10 / 35
dashboard published to ci.chowmes.com from /opt/data/apps/cios

live payload:
schema_version=21
generated_at=2026-07-12T01:55:56.197687Z
top_attention_level=watch
product_market_run.status=ran
demand_plane_status=missing
demand_readiness.status=blocked_missing_demand_source
demand_readiness.next_hermes_action=configure_ga4_or_upload_demand_export
manual_import.inbox_file_count=0
ga4_connector.enabled=False
ga4_connector.ready=False
operator_handoff.status=blocked_on_evidence
monitored_competitors=27
active_source_sum=48
signal_count=6

artifact:
artifact_status=blocked_missing_demand_source
artifact_next=configure_ga4_or_upload_demand_export
artifact_secret_values=False
dashboard_attached_readiness=blocked_missing_demand_source configure_ga4_or_upload_demand_export

live click validation:
PASS dashboard_click_validation

process check:
no_cios_daily_processes
```

Production meaning:

- The published dashboard is no longer silent about the inward-data blocker.
  It now says the exact current truth: no manual demand export is queued, GA4
  export is not enabled/ready, and the next Hermes action is
  `configure_ga4_or_upload_demand_export`.
- Argus still cannot make demand-backed product-market recommendations until
  GA4/Looker data is connected. This deployment makes that blocker explicit
  and testable instead of hidden behind UI counters.

## 2026-07-12 UTC - Product feature comparison state deployed

Problem found:

- The product-market ledger had feature-position rows, but the public
  semantic layer flattened them into a few examples. That kept the dashboard
  from acting like product muscle: the user could not compare Algolia and the
  monitored competitors feature by feature.

Repairs:

- Added public `product_feature_comparison` state with bounded company
  columns, capability rows, evidence cells, first proof URLs, and explicit
  unknown cells.
- Bumped public JSON to `schema_version=22`.
- Rebuilt the cockpit semantic layer to render "Product feature comparison"
  as a real cross-company table instead of a sample list.

Deployment notes:

- Active app root on this host was `/root/.hermes/apps/cios`; `/opt/data/apps/cios`
  was absent, so the wrapper's fallback app root was used.
- Backed up touched dashboard files to
  `/root/.hermes/backups/cios-feature-comparison-20260712T021200Z.tgz`.
- The deployed `.venv` lacked `pip`, `pydantic`, and `pytest`; bootstrapped
  `pip` with `ensurepip`, installed the declared app dependencies, installed
  `pytest`, and restored `.venv` ownership to `10000:10000`.

Verification:

```text
local full:
922 passed, 21 deselected, 1 warning

remote focused:
3 passed, 1 warning

rerender + publish:
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 391987 bytes from live DB state
status=published

public HTTPS:
https://ci.chowmes.com/ HTTP/2 200
last-modified: Sun, 12 Jul 2026 02:15:27 GMT
content-length: 391987

live payload:
schema_version=22
generated_at=2026-07-12T02:15:26.999345Z
feature_comparison_rows=12
feature_comparison_total_rows=166
feature_comparison_total_companies=27
feature_comparison_companies=['Algolia', 'Bloomreach', 'Elastic', "Luigi's Box", 'Constructor', 'Lucidworks']
first_capability=Agent Studio

live click validation:
PASS dashboard_click_validation

in-app browser:
https://ci.chowmes.com/?v=20260712T021607#semantic-layer
Product feature comparison visible.
```

Production meaning:

- The dashboard now exposes one concrete product-muscle layer: a live,
  evidence-backed comparison of what Algolia and competitors have proved,
  claimed, or not yet shown in the current evidence set.
- This is still not the full Argus brain. Demand remains missing, and the next
  deeper layer is to connect GA4/Looker demand so product evidence, public
  conversation, and Algolia audience movement can be scored together.

## 2026-07-12 UTC - Demand feature alignment deployed

Problem found:

- Product feature comparison was live, but inward demand remained disconnected
  from that product proof. Raw demand counters cannot tell a PMM, sales, or
  product user why a capability matters unless the demand topic is matched to
  the feature matrix and evidence-bearing companies.

Repairs:

- Added `demand_feature_alignment` to the dashboard state contract.
- Bumped public JSON to `schema_version=23`.
- Matched demand topics to feature capabilities with the product-market
  capability normalizer.
- Published matched rows with demand evidence URL, matched capability,
  related companies, product proof counts, and next operator step.
- Rendered the new `Audience demand alignment` section in the semantic layer.

Deployment notes:

- Active app root remained `/root/.hermes/apps/cios`.
- Backed up touched dashboard files to
  `/root/.hermes/backups/cios-demand-feature-alignment-20260712T023027Z.tgz`.
- Synced only the dashboard source/tests touched by this slice.
- Re-rendered from live DB state and republished public artifacts. No daily
  refetch was run for this UI/data-contract slice.

Verification:

```text
local full:
925 passed, 21 deselected

remote focused:
4 passed, 1 warning

rerender + publish:
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 393048 bytes from live DB state
attached operator handoff to dashboard for tenant_id=1
published=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public

public HTTPS:
https://ci.chowmes.com/ HTTP/2 200
last-modified: Sun, 12 Jul 2026 02:31:42 GMT
content-length: 394254

live payload:
schema_version=23
generated_at=2026-07-12T02:31:40.874204Z
alignment_status=no_current_demand
alignment_rows=0
product_feature_rows=12

live click validation:
PASS dashboard_click_validation

in-app browser:
https://ci.chowmes.com/?v=20260712T023140#semantic-layer
Audience demand alignment visible.
```

Production meaning:

- This makes the inward-demand bridge explicit and testable.
- The live system still does not have connected GA4/Looker demand rows. The
  new block therefore correctly says no demand-to-product alignment was
  published with this run.
- The next production repair is not another screen tweak. It is wiring real
  GA4/Looker demand into the existing import/refresh lane and proving the
  public JSON contains matched or unmatched demand rows with evidence.

## 2026-07-12 UTC - Demand fast lane sidecar repair deployed

Problem found:

- The import-demand fast lane could prepare demand exports and rerender, but
  it did not rebuild the same Hermes/Argus sidecars that the daily wrapper
  builds before publish.
- The live demand readiness sidecar was stale and exposed the wrong manual
  drop folder: `/opt/data/apps/cios/data/looker/algolia`. The active app root
  is `/root/.hermes/apps/cios`.

Repairs:

- Patched `scripts/import_demand_and_refresh.py` so a rerendered demand import
  also refreshes demand readiness, attaches the post-run summary, exports the
  evidence work queue, builds the Argus operator handoff, and attaches that
  handoff to dashboard JSON/HTML before publish.
- Refreshed production sidecars and republished public artifacts.

Deployment notes:

- Active app root remained `/root/.hermes/apps/cios`.
- Backed up touched files to
  `/root/.hermes/backups/cios-demand-fastlane-sidecars-20260712T023840Z.tgz`.
- Synced only `scripts/import_demand_and_refresh.py` and
  `tests/scripts/test_import_demand_and_refresh.py`.

Verification:

```text
local full:
925 passed, 21 deselected

remote focused:
7 passed, 1 warning

public payload:
schema_version=23
alignment_status=no_current_demand
readiness_status=blocked_missing_demand_source
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
next_hermes_action=configure_ga4_or_upload_demand_export

live click validation:
PASS dashboard_click_validation

in-app browser:
https://ci.chowmes.com/?v=20260712T023926#semantic-layer
```

Production meaning:

- The demand ingestion path is more complete now: when a GA / Looker export is
  imported, the publish path will rebuild Argus readiness and handoff instead
  of leaving stale operating instructions behind.
- The live blocker remains real data access. No manual export is queued and
  GA4 is not configured, so the dashboard correctly remains
  `blocked_missing_demand_source`.

## 2026-07-12 UTC - Demand upload folder created and permissioned

Problem found:

- After the readiness path was corrected, the folder itself still did not
  exist. A user or admin process following the readiness instruction would hit
  a filesystem miss.
- When created by a sudo/root run, the folder would default to root ownership,
  which risks blocking the app/Hermes user from writing uploaded demand files.

Repairs:

- Patched `scripts/export_argus_demand_readiness.py` to create the tenant
  manual demand drop folder before publishing readiness.
- Added ownership alignment to the CI-OS app root owner for `data`,
  `data/looker`, and the tenant drop folder when the exporter has permission
  to chown.

Verification:

```text
local full:
926 passed, 21 deselected

remote focused:
4 passed, 1 warning

remote folder:
/root/.hermes/apps/cios/data owner=10000:10000
/root/.hermes/apps/cios/data/looker owner=10000:10000
/root/.hermes/apps/cios/data/looker/algolia owner=10000:10000

public payload:
schema_version=23
readiness_generated_at=2026-07-12T02:43:12.588897Z
readiness_status=blocked_missing_demand_source
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
next_hermes_action=configure_ga4_or_upload_demand_export
alignment_status=no_current_demand

live click validation:
PASS dashboard_click_validation

in-app browser:
https://ci.chowmes.com/?v=20260712T024312#semantic-layer
```

## 2026-07-12 UTC - Admin dashboard refresh sidecar chain deployed

Problem found:

- The repaired CLI demand fast lane rebuilt demand readiness and Argus handoff
  before publish, but the admin dashboard refresh runner still only rerendered
  and published dashboard artifacts.
- This left an operator-facing stale-state hole: the admin path could publish
  current HTML with old readiness, work queue, or operator handoff sidecars.

Repairs:

- Patched `src/cios/admin/dashboard_refresh.py` so the admin runner executes
  the full post-rerender sidecar chain before public publish:
  `export_argus_demand_readiness.py`, `attach_post_run_summaries.py`,
  `export_argus_evidence_work_queue.py`,
  `build_argus_operator_handoff.py`, and
  `attach_operator_handoff_to_dashboard.py`.
- Added a publish gate: if any sidecar step fails, the admin refresh raises and
  does not publish partial public artifacts.
- Added tests for sidecar execution order and failed-sidecar publish blocking.

Deployment notes:

- Active app root remained `/root/.hermes/apps/cios`.
- Public root remained
  `/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public`.
- Backed up touched production files to
  `/root/.hermes/backups/cios-admin-refresh-sidecars-20260712T024802Z.tgz`.
- Synced only `src/cios/admin/dashboard_refresh.py` and
  `tests/admin/test_dashboard_refresh.py`.

Verification:

```text
local focused admin+demand tests:
76 passed

local full:
927 passed, 21 deselected, 1 warning

remote focused:
tests/admin/test_dashboard_refresh.py
3 passed, 1 warning

production admin runner smoke:
runner_status=published
publish_status=published
sidecar_steps=demand_readiness, attach_demand_readiness, evidence_work_queue, operator_handoff, attach_operator_handoff

public payload:
schema_version=23
generated_at=2026-07-12T02:50:53.792723Z
readiness_generated_at=2026-07-12T02:50:54.513953Z
readiness_status=blocked_missing_demand_source
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
alignment_status=no_current_demand
operator_handoff_status=blocked_on_evidence

live click validation:
PASS dashboard_click_validation
```

Production meaning:

- Both the CLI demand import path and the admin dashboard refresh path now
  rebuild Argus readiness and handoff before publishing.
- The system is still not producing demand-aware intelligence because no real
  GA4 or Looker demand export is configured or uploaded yet.

## 2026-07-12 UTC - Demand importer contract hardened

Problem found:

- Pre-normalized demand uploads could be marked ready with only `topic`,
  `metric`, and `value`.
- Those rows lacked the period and evidence provenance required by the product
  market demand ledger, so the operator path could claim readiness before the
  row was safe to persist or cite.

Repair:

- Patched `src/cios/intelligence/importers.py` so pre-normalized demand rows
  require a parseable period before normalization.
- Added default stable provenance for valid pre-normalized rows when missing:
  `source_label=Looker Studio GA4 export` and `looker://<file>#row-<n>`.
- Added regression coverage in `tests/intelligence/test_importers.py` and
  `tests/admin/test_demand_imports.py`.

Deployment notes:

- Backed up production files to
  `/root/.hermes/backups/cios-demand-importer-contract-20260712T025747Z.tgz`.
- Synced only:
  `src/cios/intelligence/importers.py`,
  `tests/intelligence/test_importers.py`, and
  `tests/admin/test_demand_imports.py`.

Verification:

```text
local red before fix:
3 failed

local full after fix:
930 passed, 21 deselected, 1 warning

remote focused:
tests/intelligence/test_importers.py::test_already_normalized_looker_rows_get_stable_default_provenance
tests/intelligence/test_importers.py::test_already_normalized_looker_rows_skip_when_required_period_is_missing
tests/admin/test_demand_imports.py::test_demand_import_prepare_rejects_incomplete_pre_normalized_rows
tests/scripts/test_import_demand_and_refresh.py
10 passed, 1 warning
```

Production meaning:

- Incomplete demand rows now fail closed at prepare time and appear in the
  manifest as skipped rows. They no longer become fake ready demand input.
- Real demand data is still missing; this repair makes the future import path
  reliable, not magically populated.

## 2026-07-12 UTC - Demand ledger Postgres dedupe cast fixed

Problem found:

- A VPS rollback smoke exercised the real demand path without committing test
  rows: demand file prepare, demand ledger persist, ledger replay, and dashboard
  state build.
- The path failed at `PgProductMarketRepository.save_demand_signal` with
  `psycopg.errors.AmbiguousParameter` because Postgres could not infer the type
  for `%(source_fingerprint)s IS NOT NULL`.

Repair:

- Patched `src/cios/db/repos/product_market.py` to cast the source-fingerprint
  parameter in the dedupe predicate:
  `%(source_fingerprint)s::text IS NOT NULL` and
  `metadata->>'source_fingerprint' = %(source_fingerprint)s::text`.
- Added a unit regression in `tests/db/test_product_market_repo.py`.
- Added a guarded integration harness in
  `tests/integration/test_demand_to_dashboard_flow.py` for resettable local
  Postgres runs.

Deployment notes:

- Backed up production files to
  `/root/.hermes/backups/cios-demand-ledger-postgres-cast-20260712T030537Z.tgz`.
- Synced:
  `src/cios/db/repos/product_market.py`,
  `tests/db/test_product_market_repo.py`, and
  `tests/integration/test_demand_to_dashboard_flow.py`.

Verification:

```text
local red before fix:
1 failed

local focused:
41 passed

local full:
930 passed, 22 deselected, 1 warning

remote focused:
1 passed, 1 warning

remote rollback smoke result:
prepared_ready_count=1
persisted_demand_signal_count=1
summary_verdict=actionable
summary_demand_signal_count=1
summary_pattern_count=2
summary_recommendation_count=1
alignment_status=matched
alignment_match_status=matched
alignment_matched_capability=AI Shopping Agent
demand_plane_status=present
recommendation_count=1
```

Production meaning:

- Demand files can now reach the real Postgres demand ledger and flow into
  Argus synthesis and dashboard semantic alignment.
- The smoke was rolled back and did not contaminate public production data.
- The live public dashboard still needs a real committed GA4 / Looker export
  before it can truthfully move out of `no_current_demand`.

## 2026-07-12 UTC - Hermes demand-source gate deployed

Problem:

- The production demand plane is still empty:
  - `demand_signals_last30=0`
  - `demand_signals_total=0`
  - no queued manual demand export
  - GA4 export disabled or unconfigured
  - public dashboard still reports no current demand.
- That means Argus has no real inward-demand muscle yet. The dashboard may have
  UI and outward competitor sweep data, but it cannot truthfully produce
  feature-to-demand intelligence until a tenant demand source exists.

Repair:

- Added and deployed `scripts/check_argus_demand_source_gate.py`.
- Added and deployed
  `tests/scripts/test_check_argus_demand_source_gate.py`.
- The gate wraps `export_argus_demand_readiness` into a Hermes/admin-safe
  contract with actionable exit codes:
  - `0`: demand source is ready.
  - `2`: no usable demand source exists.
  - `3`: manual export exists but has validation errors.
- The payload intentionally reports credential and source readiness as booleans
  only; it does not include secret values.

Deployment notes:

- Backed up existing production files to
  `/root/.hermes/backups/cios-demand-source-gate-20260712T031620Z.tgz`.
- Synced only:
  `scripts/check_argus_demand_source_gate.py` and
  `tests/scripts/test_check_argus_demand_source_gate.py`.

Verification:

```text
local red before script/path fix:
6 failed

local focused after fix:
6 passed

local adjacent readiness/import suite:
17 passed

local full:
936 passed, 22 deselected, 1 warning

remote focused:
6 passed, 1 warning

live gate output:
status=fail
exit_code=2
readiness_status=blocked_missing_demand_source
next_hermes_action=configure_ga4_or_upload_demand_export
source_ready=false
current_demand_processed=false
manual_export_ready=false
manual_export_bad=false
ga4_ready=false
processed_row_count=0
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
```

Production meaning:

- The failure is expected and correct. Hermes now has a reliable way to refuse
  a false-ready Argus run when the tenant demand plane is empty.
- This is not the full Argus brain. It is a necessary hard gate for the brain:
  no inward demand source, no claim of product-market intelligence.
- Next required production input: configure the GA4 connector or upload a real
  GA / Looker export to
  `/root/.hermes/apps/cios/data/looker/algolia`.

## 2026-07-12 UTC - Runner and cron wrapper now block missing-demand publish

Problem:

- `scripts/check_argus_demand_source_gate.py` gave Hermes a standalone demand
  readiness check, but `scripts/daily_production_run.py` still needed to
  enforce the same truth at the public publish gate.
- `deploy/cios-daily.sh` previously stopped immediately if the daily runner
  returned non-zero, so a blocked daily run could fail without leaving an
  operator-facing demand-source gate artifact.

Repair:

- Patched `scripts/daily_production_run.py`:
  - if product-market intelligence ran and explicit demand counts are all zero,
    `should_publish_dashboard()` now returns false,
  - the publish block reason begins with
    `demand_source_status=missing`,
  - existing product-market hard failures remain blocking,
  - ledger demand or ready Looker/GA rows allow publish.
- Patched `deploy/cios-daily.sh`:
  - captures the exit code from `daily_production_run.py`,
  - on failure, runs `scripts/check_argus_demand_source_gate.py`,
  - writes `out/argus-demand-source-gate.json`,
  - exits with the original daily runner code,
  - does not continue to downstream public copy.

Deployment notes:

- Backed up production files to
  `/root/.hermes/backups/cios-runner-demand-publish-gate-20260712T032243Z.tgz`.
- Synced:
  `deploy/cios-daily.sh`,
  `scripts/daily_production_run.py`,
  `scripts/check_argus_demand_source_gate.py`,
  `tests/deploy/test_cios_daily_wrapper.py`,
  `tests/scripts/test_daily_run.py`,
  `tests/scripts/test_check_argus_demand_source_gate.py`.

Verification:

```text
local red before runner fix:
test_dashboard_publish_blocks_product_market_run_without_demand_source
1 failed

local publish-gate focused:
8 passed, 91 deselected

local daily runner file:
99 passed

local red before wrapper fix:
test_hermes_wrapper_writes_demand_source_gate_when_daily_blocks_publish
1 failed

local wrapper suite:
13 passed

local runner/wrapper/package/gate suite:
133 passed

local full:
940 passed, 22 deselected, 1 warning

remote publish-gate focused:
8 passed, 91 deselected, 5 warnings

remote wrapper+gate focused:
7 passed, 1 warning

remote app path:
/opt/data/apps/cios exists=no
/root/.hermes/apps/cios exists=yes

live demand-source gate after deploy:
status=fail
exit_code=2
readiness_status=blocked_missing_demand_source
next_hermes_action=configure_ga4_or_upload_demand_export
source_ready=false
manual_export_ready=false
ga4_ready=false
processed_row_count=0
```

Production meaning:

- The public dashboard path now fails closed when the product-market layer has
  no demand evidence.
- The cron wrapper now leaves a machine-readable gate artifact for Argus/Hermes
  operators instead of only a failed shell exit.
- The remaining blocker is not code in this slice. It is the absence of a real
  tenant demand source: configure GA4 or upload a GA / Looker export.

## 2026-07-12 UTC - Product-muscle work queue wired into Hermes run artifacts

Problem:

- The admin UI could show product-muscle gaps, but Hermes-facing artifacts did
  not yet treat those gaps as run truth.
- That meant missing changelog/docs/release/API/pricing/integration/product
  surfaces could remain an admin-side issue instead of blocking or shaping the
  operator handoff and data-plane manifest.

Repair:

- Added `scripts/export_argus_product_muscle_work_queue.py`.
- Patched `scripts/build_argus_operator_handoff.py` so product-muscle work
  items merge with the evidence queue and can become the top operator blocker.
- Patched `scripts/export_argus_data_plane_manifest.py` so product-muscle
  blockers mark the product-reality plane as
  `blocked_missing_product_surfaces`.
- Patched `deploy/cios-daily.sh` so Hermes exports, validates, and passes
  `out/argus-product-muscle-work-queue.json` into the handoff and manifest
  before public publish.
- Patched `scripts/verify_hermes_package_contract.py` so deployed packages
  fail preflight if this exporter or wrapper wiring is missing.

Deployment notes:

- Backed up production files to
  `/tmp/cios-product-muscle-artifact-backup-20260712T051718Z.tar`.
- Synced:
  `deploy/cios-daily.sh`,
  `scripts/export_argus_product_muscle_work_queue.py`,
  `scripts/build_argus_operator_handoff.py`,
  `scripts/export_argus_data_plane_manifest.py`,
  `scripts/verify_hermes_package_contract.py`,
  affected script tests, and wrapper tests.

Verification:

```text
local affected suite:
49 passed

local full:
977 passed, 22 deselected, 1 warning

remote package preflight:
PASS: CI-OS Hermes package contract satisfied

remote affected suite:
49 passed

remote full:
976 passed, 1 skipped, 22 deselected, 1 warning
```

Production meaning:

- Hermes now sees missing product-muscle coverage as an operating blocker, not
  as a decorative admin table.
- Argus can say "add product surface evidence" as the next run action when the
  feature matrix cannot be trusted.
- This still does not complete the full Argus brain. The next major blocker is
  still the inward demand plane: GA4/Looker must be connected or uploaded for
  demand-backed recommendations.

## 2026-07-12 UTC - Demand fast lane now refreshes product-muscle sidecars too

Problem:

- `scripts/import_demand_and_refresh.py` was the operator fast lane for
  uploading a GA / Looker export and replaying Argus from the evidence ledger.
- After rerender, it rebuilt demand readiness, evidence queue, operator
  handoff, and data-plane manifest, but it did not include the new
  product-muscle work queue.
- That meant a manual demand import could produce sidecars that were weaker
  than the scheduled Hermes daily wrapper, even though both paths should expose
  the same run truth before publish.

Repair:

- Patched `_refresh_post_rerender_artifacts()` in
  `scripts/import_demand_and_refresh.py` to run
  `scripts/export_argus_product_muscle_work_queue.py`.
- The fast lane now passes
  `out/argus-product-muscle-work-queue.json` into:
  - `build_argus_operator_handoff.py --product-muscle-queue`
  - `export_argus_data_plane_manifest.py --product-muscle-work-queue`
- Updated `tests/scripts/test_import_demand_and_refresh.py` so demand-import
  replay proves sidecar parity with the daily wrapper.

Deployment notes:

- Backed up production files to
  `/tmp/cios-demand-fast-lane-product-muscle-backup-20260712T052306Z.tar`.
- Synced:
  `scripts/import_demand_and_refresh.py`,
  `tests/scripts/test_import_demand_and_refresh.py`.

Verification:

```text
local demand fast-lane tests:
7 passed

local affected suite:
36 passed

local full:
977 passed, 22 deselected, 1 warning

remote affected suite:
36 passed

remote full:
976 passed, 1 skipped, 22 deselected, 1 warning
```

Production meaning:

- A manual Looker/GA demand import can now refresh Argus and produce the same
  Hermes-readable sidecar chain as the scheduled daily run.
- When inward demand arrives, Argus replay will still preserve product-muscle
  blockers and feature-matrix coverage truth instead of accidentally treating
  demand import as a shortcut around product evidence.

## 2026-07-12 UTC - Blocked Hermes daily runs now leave operator artifacts

Problem:

- The scheduled Hermes wrapper could correctly refuse public publish when the
  demand plane was missing, but a blocked run still had to leave Argus with
  local run truth.
- The first repair added failure-path sidecar export to `deploy/cios-daily.sh`,
  but the live run exposed a second contract break: `daily_production_run.py`
  wrote the versioned dashboard state file during a blocked publish, while the
  sidecar tools read `out/argus-dashboard.json`.
- Result before this fix: live wrapper exited `2`, public stayed unchanged, but
  operator sidecars were skipped because `out/argus-dashboard.json` was absent.

Repair:

- Patched `deploy/cios-daily.sh` so non-zero daily runs that have
  `out/argus-dashboard.json` still export:
  - `argus-demand-readiness.json`
  - `argus-evidence-work-queue.json`
  - `argus-product-muscle-work-queue.json`
  - `argus-operator-handoff.json`
  - `argus-data-plane-manifest.json`
- Patched `daily_production_run.py` so the publish-gate stage writes local
  dashboard artifacts whenever a dashboard state exists, even if public publish
  is blocked. Public publish remains blocked by the wrapper exit code.
- Synced the tested package wrapper to the actual Hermes script path:
  `/root/.hermes/scripts/cios-daily.sh`.

Local verification:

```text
bash -n deploy/cios-daily.sh scripts/daily_production_run.py
affected suite:
140 passed

full suite:
977 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-daily-failure-sidecars-backup-20260712T053349Z.tar
backup=/tmp/root-hermes-scripts-cios-daily-20260712T054126Z.bak
backup=/tmp/cios-daily-json-contract-backup-20260712T055528Z.tar

/root/.hermes/scripts/cios-daily.sh now matches
/root/.hermes/apps/cios/deploy/cios-daily.sh
```

Remote verification:

```text
affected suite:
140 passed

full suite:
976 passed, 1 skipped, 22 deselected, 1 warning
```

Live Hermes-path acceptance:

```text
timeout 900 /root/.hermes/scripts/cios-daily.sh
wrapper_rc=2

algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0
facts=469 deltas=469 verdict=quiet quality=passed fn=clean
product_market=ran

ABORT: dashboard publish blocked for algolia
demand_source_status=missing
ga4_export_status=skipped_disabled
looker_ready_count=0
ledger_demand_signal_count=0

artifact_present=out/argus-dashboard.html
artifact_present=out/brief.html
artifact_present=out/argus-dashboard.json
artifact_present=out/argus-demand-source-gate.json
artifact_present=out/argus-demand-readiness.json
artifact_present=out/argus-evidence-work-queue.json
artifact_present=out/argus-product-muscle-work-queue.json
artifact_present=out/argus-operator-handoff.json
artifact_present=out/argus-data-plane-manifest.json

manifest_status=blocked_on_evidence
manifest_next_action=configure_ga4_or_upload_demand_export
manifest_planes=audience_demand,market_conversation,operator_learning,product_reality,registry_coverage,run_truth
product_muscle_work_items=17
product_muscle_blocking=12
product_muscle_limiting=5
evidence_work_items=1
evidence_blocking=1
demand_readiness_status=blocked_missing_demand_source
out_generated_at=2026-07-12T06:02:09.283436Z
out_demand_plane_status=missing
out_pattern_count=2
out_product_event_count=500
public_after_generated_at=2026-07-12T04:07:00.190182Z
```

Production meaning:

- Hermes can now run the CI-OS package, refuse unsafe public publish, and still
  leave Argus with the evidence queue, product-muscle queue, operator handoff,
  demand gate, and data-plane manifest needed for the next operator action.
- Public dashboard freshness did not change during the blocked run, which is
  correct. The package `out/` directory now contains current run truth.
- The remaining blocker is not the wrapper or artifact chain. It is the inward
  demand plane: connect GA4 or upload Looker demand evidence so Argus can move
  from `blocked_on_evidence` to publishable recommendations.

## 2026-07-12 UTC - Queued demand import fast lane

Problem:

- The admin app and daily full run could see tenant demand files under
  `data/looker/{tenant}`, but the operator CLI still required `--input`.
- That meant Hermes or an operator could not run the package command
  "process whatever Looker/GA demand export is already queued for this tenant"
  without re-uploading the file path manually.
- This kept the inward-demand plane operationally brittle: the dashboard was
  blocked on demand, but the direct package command to process queued demand was
  missing.

Repair:

- Patched `scripts/import_demand_and_refresh.py`:
  - `--input` is now optional.
  - New `--queued` flag processes exports already present in the tenant drop
    folder.
  - CLI validation now requires either at least one `--input` or `--queued`.
  - Queued mode now fails closed with `no_ready_demand` when no ready export is
    present, so automation cannot confuse an empty queue with a successful
    import.
  - Existing `--input` behavior is unchanged; uploaded files are still copied
    into `data/looker/{tenant}` before prepare/refresh.
- Added regression coverage in
  `tests/scripts/test_import_demand_and_refresh.py` for queued files already in
  `data/looker/algolia` and for empty queued mode.
- No Hermes core file was modified. This remains a CI-OS package capability.

Local verification:

```text
red test before patch:
FAILED test_import_demand_and_refresh_prepares_existing_queued_looker_file_without_input
argparse: the following arguments are required: --input

single queued-mode regression:
1 passed

affected demand/admin/dashboard-flow suite:
75 passed, 1 deselected, 1 warning

full local package suite:
979 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-queued-demand-fastlane-backup-20260712T061214Z.tar
backup=/tmp/cios-queued-demand-failclosed-backup-20260712T061652Z.tar
deploy_status=ok
```

Remote verification:

```text
affected demand/admin/dashboard-flow suite:
75 passed, 1 deselected, 1 warning

non-destructive live smoke using a temporary app/work directory:
queued_smoke_status=prepared
queued_smoke_copied_inputs=0
queued_smoke_ready_count=1
queued_smoke_normalized_rows=1
queued_smoke_topic=AI Shopping Agent

empty queued-mode smoke:
empty_queue_rc=1
empty_queue_status=no_ready_demand
empty_queue_ready_count=0

full remote package suite:
978 passed, 1 skipped, 22 deselected, 1 warning
```

Production meaning:

- Hermes now has a package-level command path to process tenant demand exports
  that are already queued in the CI-OS package state.
- This does not fake demand or unblock publish by itself. It removes one
  operator/Hermes execution gap so the next real GA4/Looker export can be
  processed into `demand_signals`, replay Argus, refresh sidecars, and then
  pass or fail the same publish gates as the daily run.
- The current live blocker remains the absence of real configured or uploaded
  Algolia demand evidence. The next required slice is to connect GA4 or place a
  valid Looker export under `/root/.hermes/apps/cios/data/looker/algolia` and
  run the queued import path through ledger persistence and Argus replay.

## 2026-07-12 UTC - Hermes-callable demand intake coordinator

Problem:

- Demand readiness and demand import existed as separate package commands.
- Hermes still had to infer which operation to run:
  - if manual Looker/GA export is queued, import queued demand;
  - if GA4 is configured, export GA4 first, then import queued demand;
  - if no source is usable, stop with a clear operator action.
- That split left another execution gap between "Argus is blocked on demand"
  and "Hermes can run the correct next demand-plane action."

Repair:

- Added `scripts/run_argus_demand_intake.py`.
- The coordinator:
  - reads the demand readiness payload;
  - runs queued manual demand import when `status=queued_manual_exports`;
  - runs GA4 export first when `status=ready_to_export_ga4`, then processes
    the generated queued export;
  - returns `blocked_missing_demand_source` with exit `2` when no demand source
    is ready;
  - returns `blocked_bad_manual_export` with exit `3` when a queued export is
    malformed;
  - writes one machine-readable result with `status`, `exit_code`, `mode`,
    `next_hermes_action`, `readiness`, `ga4_export`, and `demand_import`.
- Added `tests/scripts/test_run_argus_demand_intake.py`.
- Updated `scripts/verify_hermes_package_contract.py` and its tests so a
  deployed CI-OS package cannot pass Hermes preflight while missing the demand
  intake coordinator.
- No Hermes core file was modified.

Local verification:

```text
red test before script:
5 failed
FileNotFoundError: scripts/run_argus_demand_intake.py

red package-contract test before verifier update:
preflight passed even when scripts/run_argus_demand_intake.py was missing

focused coordinator + package-contract tests:
6 passed

affected demand/intake/admin/package-contract suite:
113 passed, 1 deselected, 1 warning

full local package suite:
985 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-demand-intake-coordinator-backup-20260712T062334Z.tar
deploy_status=ok
```

Remote verification:

```text
package preflight:
PASS: CI-OS Hermes package contract satisfied

affected demand/intake/admin/package-contract suite:
113 passed, 1 deselected, 1 warning

non-destructive live positive smoke using a temporary app/work directory:
intake_positive_status=demand_imported_and_argus_refreshed
intake_positive_exit=0
intake_positive_mode=queued_manual_export
intake_positive_ready_count=1
intake_positive_normalized_rows=1

live production-source check:
intake_live_exit=2
intake_live_status=blocked_missing_demand_source
intake_live_mode=blocked
intake_live_next=configure_ga4_or_upload_demand_export

full remote package suite:
984 passed, 1 skipped, 22 deselected, 1 warning
```

Production meaning:

- Hermes now has one CI-OS package command for the inward-demand plane:
  `scripts/run_argus_demand_intake.py`.
- The command can safely run in automation because it does not pretend success
  when no source exists, and it chooses the correct path for manual queued
  exports versus configured GA4.
- This still does not create real Algolia demand evidence. It makes the demand
  intake loop executable and auditable once a real GA4 connector or Looker
  export is present.
- The current production blocker remains unchanged:
  `/root/.hermes/apps/cios/data/looker/algolia` has no real queued demand
  export, and GA4 is not configured on the live host.

## 2026-07-12 UTC - Product-muscle heuristic probes for uncovered competitors

Problem:

- Product-muscle gap discovery only validated URLs already present in the
  monitored source registry.
- That was safe, but too passive: a competitor with a known domain and no
  active product surfaces produced an empty `candidate_surface_urls` list.
- Result: Hermes could report "missing product surfaces" but often had no
  executable next probes for changelogs, docs, release notes, pricing, APIs,
  integrations, or product pages.

Repair:

- Patched `scripts/daily_production_run.py` so the product-muscle gap plan now
  keeps two different buckets:
  - `candidate_surface_urls`: evidence-backed URLs from active monitored
    sources.
  - `heuristic_surface_probes`: low-confidence domain-derived probes that are
    explicitly marked `requires_validation=true`.
- Added deterministic heuristic probes from a known company domain:
  - `/changelog`
  - `/release-notes`
  - `/docs`
  - `/developers`
  - `/pricing`
  - `/integrations`
  - `/products`
  - `/platform`
- Patched `src/cios/intelligence/product_muscle_gap_discovery.py` so the
  discovery executor validates both evidence-backed candidates and heuristic
  probes. Only validator-accepted URLs become `candidate` product surfaces.
- Discovery summaries now report `heuristic_candidate_url_count` and preserve
  `candidate_source=heuristic_surface_probes` plus
  `discovery_reason=domain_heuristic` in accepted/rejected rows.
- No Hermes core file was modified.

Local verification:

```text
red daily-plan test before patch:
KeyError: 'heuristic_surface_probes'

red executor test before patch:
candidate_url_count was 0 instead of 2 for heuristic probes

focused daily/product-muscle tests:
5 passed

affected product-muscle/dashboard/data-plane suite:
197 passed

full local package suite:
986 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-product-muscle-heuristic-probes-backup-20260712T063039Z.tar
deploy_status=ok
```

Remote verification:

```text
affected product-muscle/dashboard/data-plane suite:
197 passed

deployed package smoke:
heuristic_probe_count=8
heuristic_families={"api_docs": 1, "changelog": 1, "docs": 1, "integration": 1, "pricing": 1, "product_page": 2, "release_notes": 1}
first_probe={"discovery_reason": "domain_heuristic", "requires_validation": true, "surface_family": "changelog", "url": "https://algonomy.com/changelog"}

full remote package suite:
985 passed, 1 skipped, 22 deselected, 1 warning
```

Production meaning:

- Argus/Hermes now has an executable next step for domain-known competitors
  that lack product-reality coverage.
- The system still does not pretend guessed URLs are evidence. They are probes,
  and the discovery executor must validate them before they become candidate
  product surfaces.
- This moves the product-muscle layer closer to a real operating loop:
  identify product-surface gaps -> propose bounded probes -> validate probes ->
  queue accepted product surfaces -> promote and extract with Scout.

## 2026-07-12 UTC - Product-muscle loop now runs even when demand blocks public publish

Problem:

- The Hermes wrapper already ran product-muscle gap discovery and candidate
  promotion on successful daily runs.
- But the current production system is intentionally blocked on missing inward
  demand evidence. That meant `daily_production_run.py` exited nonzero before
  the wrapper reached the product-muscle discovery and promotion steps.
- Result: the public dashboard was correctly not published, but the product
  reality layer also stopped making progress. Demand blockage should not
  prevent independent product-surface coverage work.

Repair:

- Patched `deploy/cios-daily.sh` failure path.
- When the daily runner exits nonzero but still leaves
  `out/argus-dashboard.json`, the wrapper now:
  - runs `execute_product_muscle_gap_discovery.py`;
  - runs `promote_product_surface_candidates.py`;
  - attaches `product-muscle-gap-discovery-summary.json` and
    `product-surface-candidate-promotion-summary.json` to the local dashboard
    JSON with `attach_post_run_summaries.py`;
  - continues exporting demand readiness, work queues, operator handoff, and
    data-plane manifest;
  - still exits nonzero and still does not touch the public dashboard.
- Synced the package wrapper to the actual Hermes cron wrapper:
  `/root/.hermes/scripts/cios-daily.sh`.

Local verification:

```text
red wrapper test before patch:
blocked publish path skipped gap-discovery and candidate-promotion

blocked-path wrapper regression:
1 passed

affected wrapper/product-muscle suite:
133 passed

full local package suite:
986 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-wrapper-blocked-product-muscle-backup-20260712T063517Z.tar
deploy_status=ok
```

Remote verification:

```text
package preflight:
PASS: CI-OS Hermes package contract satisfied

affected wrapper/product-muscle suite:
133 passed

full remote package suite:
985 passed, 1 skipped, 22 deselected, 1 warning
```

Live Hermes-path acceptance:

```text
timeout 900 /root/.hermes/scripts/cios-daily.sh
wrapper_rc=2

daily production runner exited with 2; demand source gate exited with 2

artifact_argus-dashboard.json=present
artifact_product-muscle-gap-discovery-summary.json=present
artifact_product-surface-candidate-promotion-summary.json=present
artifact_argus-demand-readiness.json=present
artifact_argus-product-muscle-work-queue.json=present
artifact_argus-data-plane-manifest.json=present

gap_status=completed
gap_candidate_url_count=47
gap_heuristic_candidate_url_count=0
gap_stored_candidate_count=0
gap_rejected_count=47
promotion_status=completed
promotion_promoted_count=0
dashboard_gap_attached=True
dashboard_promotion_attached=True
manifest_status=blocked_on_evidence
manifest_next=configure_ga4_or_upload_demand_export
```

Production meaning:

- A demand-blocked run now still advances and records product-muscle discovery
  work.
- In this live run, Hermes validated 47 product-surface candidates but accepted
  none. That is still useful intelligence: the product-muscle coverage gap is
  no longer silent, and rejected candidates are now part of run truth.
- Public publish remains correctly blocked until inward demand evidence exists.

## 2026-07-12 UTC - Local admin/run-console service made persistent

Problem:

- CI-OS had a tested local admin app, but it was not installed as a persistent
  Hermes-host service.
- That left competitor/source management, demand import intake, and Argus
  blocker inspection dependent on an ad hoc foreground process.
- A package could pass preflight even if the admin service unit was missing,
  bound publicly, or skipped the CI-OS env file.

Repair:

- Added package-owned systemd unit artifact:
  `deploy/cios-admin.service`.
- The unit runs the package admin runner only:
  `scripts/run_admin.py --env-file /root/.hermes/cios-env --host 127.0.0.1 --port 8765`.
- It is loopback-only and uses `NoNewPrivileges=true`.
- Hardened `scripts/verify_hermes_package_contract.py` so preflight now fails
  if the service artifact is missing, binds to `0.0.0.0`, omits the env file,
  omits the admin runner, or drops `NoNewPrivileges=true`.
- Installed the unit on Chowmes as `/etc/systemd/system/cios-admin.service` and
  enabled it with systemd.

Local verification:

```text
red service-contract tests before patch:
3 failed, 1 passed, 21 deselected

green service-contract slice:
4 passed, 21 deselected

focused package/admin suite:
27 passed

full local package suite:
994 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/root/.hermes/apps/cios/.codex-backups/admin-service-20260712T073435Z
package preflight:
PASS: CI-OS Hermes package contract satisfied

focused package/admin suite:
27 passed

full remote package suite:
993 passed, 1 skipped, 22 deselected, 1 warning
```

Live service verification:

```text
systemctl is-active cios-admin.service:
active

listen socket:
127.0.0.1:8765

admin smoke:
admin_health=ok
registry_competitors=29
registry_sources=49
demand_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
demand_inbox_files=0
demand_ready_count=0
argus_readiness=not_actionable
manifest_blockers=13
product_muscle_work_items=17
```

Production meaning:

- The admin/run-console layer is now a persistent local-only service, not a
  manual throwaway process.
- Operators can inspect the monitored competitor/source registry and upload or
  prepare demand evidence through the package admin plane.
- The system is still not end-to-end actionable: live Argus readiness remains
  `not_actionable` because the inward demand plane has no GA4/Looker data and
  the product-reality plane still has product-surface blockers.
- No Hermes core file was modified.

## 2026-07-12 UTC - Product-muscle work queue now explains latest Scout execution

Problem:

- The Argus product-muscle work queue correctly identified competitors with
  product surfaces but no feature evidence.
- But it did not show what Hermes had already attempted during the latest
  product-surface export run.
- Operators saw generic advice like "Run Scout product-surface extraction" even
  when Hermes had already planned the surfaces, run Scout, and captured
  success/failure output under `/tmp/cios-product-market/<tenant>/`.
- The persistent admin service also used `PrivateTmp=true`, which hid the
  Hermes `/tmp/cios-product-market` artifacts from the admin process.

Repair:

- Added `src/cios/admin/product_surface_execution_trace.py`.
- The admin product-muscle queue now reads:
  - `product-surface-plan.json`
  - `product-surface-execution-summary.json`
  - the emitted product-surface JSON row files.
- Work items now include latest execution facts in `observed_state`:
  - `latest_surface_export_planned_count`
  - `latest_surface_export_succeeded_count`
  - `latest_surface_export_failed_count`
  - `latest_surface_export_row_count`
  - `latest_surface_export_empty_output_count`
  - `latest_surface_export_last_error`
  - `latest_surface_export_summary_path`
- Updated the admin service contract and unit to use `PrivateTmp=false` so the
  local-only admin plane can read Hermes product-market artifacts.
- Preflight now fails if the admin service uses private `/tmp` and would hide
  these artifacts.

Local verification:

```text
red trace tests before implementation:
2 failed

red service contract before implementation:
1 failed

focused trace/service suite:
98 passed, 1 warning

full local package suite:
996 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/root/.hermes/apps/cios/.codex-backups/product-surface-trace-20260712T074534Z
backup=/root/.hermes/apps/cios/.codex-backups/admin-private-tmp-fix-20260712T074803Z

focused remote trace/service suite:
98 passed, 1 warning

package preflight:
PASS: CI-OS Hermes package contract satisfied

full remote package suite:
995 passed, 1 skipped, 22 deselected, 1 warning
```

Live service verification:

```text
systemctl is-active cios-admin.service:
active

systemctl show cios-admin.service -p PrivateTmp --value:
no

listen socket:
127.0.0.1:8765

product-muscle work item count:
17

Coveo trace:
planned=4
succeeded=1
failed=3
row_count=0
empty_outputs=1
last_error=RuntimeError: Scout product surface scrape returned no markdown

Athos Commerce trace:
planned=1
succeeded=1
failed=0
row_count=0
empty_outputs=1

Meilisearch trace:
planned=1
succeeded=0
failed=1
row_count=0
last_error=subprocess.TimeoutExpired: scout_http_shim scrape timed out after 120 seconds

Typesense trace:
planned=1
succeeded=1
failed=0
row_count=0
empty_outputs=1
```

Production meaning:

- The product-muscle queue is now an operating diagnostic, not just a missing
  coverage list.
- Hermes/Argus can distinguish "no product surface exists" from "surface exists
  but Scout produced no rows" from "Scout failed on the last run."
- This makes the next product-muscle fixes concrete: Coveo needs scrape/no
  markdown handling, Meilisearch needs timeout handling, and several successful
  zero-row surfaces need either better extraction prompts or better source URLs.
- This still does not solve the missing inward demand plane. Argus remains
  `not_actionable` until GA4/Looker demand evidence is loaded or configured.
- No Hermes core file was modified.

## 2026-07-12 UTC - Product-surface failures classified into repair actions

Problem:

- The product-muscle queue showed raw latest Scout execution counts, but it did
  not classify failure modes into operator or automation actions.
- This still made the queue too generic: a timeout, an uncrawlable page, and a
  successful zero-row extraction all require different repairs.
- `export_product_surface_with_scout.py` also let subprocess timeouts bubble as
  Python tracebacks, which polluted execution summaries and made the live queue
  harder to interpret.

Repair:

- Added product-surface failure classification in
  `src/cios/admin/product_muscle_work_queue.py`.
- Work-item observed state now includes:
  - `latest_surface_export_failure_category`
  - `latest_surface_export_repair_action`
- Current categories:
  - `no_markdown`: Scout could not return markdown for the page.
  - `timeout`: Scout scrape/extract exceeded the configured timeout.
  - `scout_failure`: Scout failed for another reason.
  - `empty_extraction`: Scout succeeded but produced zero product rows.
- Work-item `next_step` now uses the repair action when a latest execution
  diagnosis is available.
- `scripts/export_product_surface_with_scout.py` now catches subprocess
  `TimeoutExpired` and returns a concise timeout error instead of a full Python
  traceback.

Local verification:

```text
red diagnostics tests before implementation:
4 failed

focused diagnostics/exporter tests:
4 passed

affected suite:
81 passed, 1 warning

full local package suite:
999 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/root/.hermes/apps/cios/.codex-backups/product-surface-repair-diagnostics-20260712T075446Z

affected remote suite:
81 passed, 1 warning

package preflight:
PASS: CI-OS Hermes package contract satisfied

full remote package suite:
998 passed, 1 skipped, 22 deselected, 1 warning
```

Live service verification:

```text
systemctl is-active cios-admin.service:
active

listen socket:
127.0.0.1:8765

Coveo:
category=no_markdown
repair=Replace or fix the product surface URL, or use a crawlable docs/changelog source that Scout can return as markdown.

Meilisearch:
category=timeout
repair=Retry the surface with JavaScript enabled or a higher timeout, then replace the source if it still stalls.

Athos Commerce:
category=empty_extraction
repair=Review the product-surface extraction prompt or replace the source with a page that contains concrete release, docs, pricing, or integration proof.

Typesense:
category=empty_extraction
repair=Review the product-surface extraction prompt or replace the source with a page that contains concrete release, docs, pricing, or integration proof.
```

Production meaning:

- Argus now explains why a product-muscle item is blocked and what repair class
  applies.
- This is not yet autonomous repair, but it is a necessary step toward Hermes
  acting on the queue: the next runner can route `no_markdown`, `timeout`, and
  `empty_extraction` to different remediation policies.
- The inward demand plane is still absent, so Argus remains not actionable for
  final recommendation promotion.
- No Hermes core file was modified.

## 2026-07-12 UTC - Product-surface repair history exposed in admin

Problem:

- Product-surface repair retries could be launched from the admin/product-muscle
  queue, but operators still had to inspect `/tmp` artifacts to understand what
  happened afterward.
- This made the repair loop opaque: a failed retry, a no-match retry, and a
  successful product-ledger refresh were not visible as first-class admin state.

Repair:

- Added `ProductSurfaceRepairHistoryStore` to read recent
  `product-surface-repairs` summaries, preferring the combined
  `admin-repair-summary.json` when present and falling back to the raw
  `repair-summary.json`.
- Added `write_product_surface_repair_admin_summary` so the admin repair action
  persists the combined repair result, including `argus_refresh` and
  `argus_read` when repaired Scout rows are imported.
- Added
  `GET /api/tenants/{tenant_slug}/argus/product-surface-repairs`.
- Added an admin page section titled `Latest product-surface repair attempts`
  showing target, status, extracted rows, imported product events, error/detail,
  and summary path.

Local verification:

```text
red API/UI tests before implementation:
2 failed

focused repair-history tests:
7 passed, 1 warning

admin suite:
92 passed, 1 warning

full local package suite:
1012 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-admin-repair-history-backup-20260712T083445Z

focused remote repair-history tests:
4 passed, 1 warning

remote admin suite:
92 passed, 1 warning

remote full package suite:
1011 passed, 1 skipped, 22 deselected, 1 warning
```

Live service verification:

```text
systemctl is-active cios-admin.service:
active

GET /api/tenants/algolia/argus/product-surface-repairs:
attempt_count=3
latest.status=no_matching_failed_surface
previous Coveo attempt: category=no_markdown, surface_id=10, error=HTTP 403

/admin?tenant=algolia:
contains Latest product-surface repair attempts
```

Production meaning:

- The product-muscle loop is now inspectable from the admin UI: diagnose,
  launch bounded repair, see result, and see whether Argus imported product
  proof.
- This does not solve product-source quality by itself. It removes another
  blind spot so Hermes/Argus can operate the repair loop with visible state.
- No Hermes core file was modified.

## 2026-07-12 UTC - Argus demand intake exposed as admin operation

Problem:

- The inward-demand plane had a Hermes-callable coordinator
  (`scripts/run_argus_demand_intake.py`), but the local-only admin/run-console
  layer did not expose it as a first-class operation.
- Operators still saw separate low-level actions: upload demand, prepare demand,
  GA4 export, refresh Argus. That did not match the real operating question:
  "Can Hermes fix or explain the missing demand plane now?"

Repair:

- Added `src/cios/admin/demand_intake.py`.
- Added `DemandIntakeControl`, which runs
  `scripts/run_argus_demand_intake.py` with bounded execution and writes each
  attempt to:
  `/tmp/cios-product-market/{tenant}/demand-intake-runs/{run_id}/demand-intake-summary.json`.
- Added `DemandIntakeHistoryStore`, which reads recent intake attempts and
  normalizes the operator-facing fields:
  status, mode, readiness status, next Hermes action, GA4 record count,
  normalized demand rows, demand signals, Argus top insight, error, and summary
  path.
- Added admin API routes:
  - `GET /api/tenants/{tenant}/argus/demand-intake`
  - `POST /api/tenants/{tenant}/argus/demand-intake`
- Added admin form route:
  - `POST /admin/{tenant}/argus/demand-intake`
- Added admin UI section:
  - `Argus demand intake`
  - one-button `Run demand intake`
  - recent attempt history table

Local verification:

```text
red tests before implementation:
ModuleNotFoundError: No module named 'cios.admin.demand_intake'

focused demand-intake tests:
6 passed, 1 warning

admin suite:
98 passed, 1 warning

full local package suite:
1018 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-admin-demand-intake-backup-20260712T084600Z

focused remote demand-intake tests:
6 passed, 1 warning

remote admin suite:
98 passed, 1 warning

remote full package suite:
1017 passed, 1 skipped, 22 deselected, 1 warning

package contract:
PASS: CI-OS Hermes package contract satisfied
```

Live service verification:

```text
systemctl is-active cios-admin.service:
active

GET /api/tenants/algolia/argus/demand-intake before operation:
attempt_count=0

POST /api/tenants/algolia/argus/demand-intake:
status=blocked_missing_demand_source
exit_code=2
command_status=blocked
next_hermes_action=configure_ga4_or_upload_demand_export

GET /api/tenants/algolia/argus/demand-intake after operation:
attempt_count=1
latest.readiness_status=blocked_missing_demand_source
latest.normalized_row_count=0
latest.demand_signal_count=0

/admin?tenant=algolia:
contains Argus demand intake
```

Production meaning:

- Hermes/Argus now has a visible local admin operation for the missing inward
  demand plane: inspect readiness, export GA4 if ready, process queued GA /
  Looker files, persist demand rows, refresh Argus, and record the result.
- The current live state is still blocked because no GA4 credentials/property
  or manual GA / Looker export is present. That is now represented as a durable
  demand-intake attempt with the next Hermes action, not as vague UI confusion.
- No Hermes core file was modified.

## 2026-07-12 UTC - Data-plane manifest consumes demand-intake artifact

Problem:

- The inward-demand plane had a Hermes-callable/admin-callable coordinator and
  durable attempt history, but `argus-data-plane-manifest.json` still only
  reflected demand readiness plus dashboard state.
- That left a truth gap: the operating manifest could say demand was missing,
  but not whether Hermes/Argus had already attempted demand intake, what that
  attempt returned, or what action remained.

Repair:

- Patched `scripts/export_argus_data_plane_manifest.py`.
- Added `--demand-intake` as a manifest input.
- Added `artifact_refs.demand_intake`.
- Added `planes.audience_demand.details.demand_intake`.
- Demand-intake details now include status, command status, exit code, mode,
  next Hermes action, summary path, and nested artifact counts only when those
  artifacts actually exist.
- A successful intake with demand rows can upgrade the audience-demand plane to
  `processed` and surface the latest Argus replay insight.
- A blocked no-source attempt stays blocked and does not leak fake zero-row
  import counts.
- No Hermes core file was modified.

Local verification:

```text
red focused test before final patch:
1 failed, 4 passed
blocked demand intake leaked zero-count detail fields

focused manifest suite:
5 passed

affected manifest/demand/package suite:
53 passed

full local package suite:
1019 passed, 22 deselected, 1 warning
```

Remote deployment:

```text
backup=/tmp/cios-data-plane-demand-intake-backup-20260712T085819Z.tar
deploy_status=ok

affected remote manifest/demand/package suite:
53 passed

full remote package suite:
1018 passed, 1 skipped, 22 deselected, 1 warning

package contract:
PASS: CI-OS Hermes package contract satisfied
```

Live manifest smoke:

```text
manifest_status=blocked_on_evidence
manifest_next=configure_ga4_or_upload_demand_export
demand_status=blocked_missing_demand_source
demand_blocks_action=True
demand_intake_status=blocked_missing_demand_source
demand_intake_next=configure_ga4_or_upload_demand_export
demand_intake_zero_noise_keys=
```

Production meaning:

- The manifest now carries the inward-demand repair attempt as part of Argus
  run truth.
- The UI/admin layer can tell the difference between "demand was never tried"
  and "Hermes tried demand intake and is blocked because no GA4/Looker source is
  configured or uploaded."
- This still does not create actual Algolia demand evidence. The system remains
  blocked until GA4 is configured or a valid Looker/GA export is uploaded and
  imported.

## Demand Operator Commands In Cockpit - 2026-07-12

Problem:

- The data-plane manifest carried sanitized demand operator commands, but the
  public cockpit handoff still rendered only the single primary command from
  the evidence queue.
- That made Argus less actionable than the manifest: the public screen could
  say demand was blocked, but not show the operator the full safe command set
  generated by demand readiness.

Repair:

- `scripts/build_argus_operator_handoff.py` now accepts `--demand-readiness`.
- The handoff payload includes public-safe `operator_commands` derived from
  `argus-demand-readiness.json`.
- Command summaries contain `label`, `method`, `surface`, and `route_kind`;
  they intentionally strip raw `href`.
- `DashboardOperatorHandoff` now models those command summaries.
- `src/cios/dashboard/cockpit_renderer.py` renders the command list in the
  Argus operator handoff block without exposing admin/API URLs.
- `deploy/cios-daily.sh` passes `argus-demand-readiness.json` into the handoff
  builder on both blocked and successful daily-run paths.

Verification:

```text
targeted local RED:
2 failed
- build_operator_handoff_payload() did not accept demand_readiness
- cockpit did not render Open demand admin

targeted local GREEN:
3 passed

affected local suite:
95 passed

full local suite:
1022 passed, 22 deselected, 1 warning

local syntax/package contract:
bash -n deploy/cios-daily.sh
python3 -m py_compile scripts/build_argus_operator_handoff.py src/cios/dashboard/types.py src/cios/dashboard/cockpit_renderer.py src/cios/dashboard/__init__.py
PASS: CI-OS Hermes package contract satisfied

remote targeted suite:
3 passed

remote affected suite:
95 passed

remote full suite:
1021 passed, 1 skipped, 22 deselected, 1 warning

remote package contract:
PASS: CI-OS Hermes package contract satisfied
```

Remote artifact smoke:

```text
operator_command_count 3
command_1 {"label": "Download demand template", "method": "get", "route_kind": "api", "surface": "Demand imports"}
command_2 {"label": "Open demand admin", "method": "get", "route_kind": "admin", "surface": "Admin"}
command_3 {"label": "Run GA4 export now", "method": "post", "route_kind": "admin", "surface": "GA4 connector"}
handoff_commands_have_href False
html_has_download_demand_template True
html_has_open_demand_admin True
html_has_run_ga4_export_now True
html_has_raw_api_href False
html_has_raw_admin_hash False
html_has_raw_ga4_admin False
```

Production meaning:

- The cockpit is now more actionable about the blocked inward-demand plane.
- This is still not a demand-data fix. Argus remains blocked from fully
  demand-backed recommendations until GA4 is configured or a valid GA/Looker
  export is uploaded and imported.
