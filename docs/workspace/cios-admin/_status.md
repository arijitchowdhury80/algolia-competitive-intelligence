# CI-OS Admin Feature Status

Status: in progress

Goal: add a CI-OS-owned, local-only admin surface for managing monitored competitors and source URLs without modifying Hermes core or making the public dashboard writable.

Latest slice: HTML registry edit controls are implemented locally for competitors, source URLs, and product surfaces. The admin API already supported update calls; the HTML operator surface now exposes those same writes through collapsed edit forms, so registry maintenance no longer requires raw API calls.

Follow-up slice: the GA4 connector panel now explains the setup gap when the inward demand connector is disabled or incomplete. It lists the required env/config keys and disables the `Run GA4 export now` button until the connector is actually ready, instead of showing the misleading disabled-state line `Missing: None`.

Latest product-muscle operator slice: successful product-surface repair output now feeds back into Argus. The local-only admin API/form still runs a bounded repair retry, but when the repair produces `scout_paths`, CI-OS builds a product-market payload from those repaired rows, persists/synthesizes through the existing product-market runner, and returns the refreshed Argus read.

Latest repair-history slice: the local-only admin surface now exposes recent product-surface repair attempts. Operators can inspect the latest bounded repair retries from the admin page and JSON API, including target company, failure category, status, extracted rows, imported product events, error detail, and summary path. Repair actions also write an admin-level summary beside the raw repair output so the history survives service restarts.

Latest demand-intake slice: the local-only admin surface now exposes Argus inward-demand intake as a first-class operation. Operators can run the Hermes-facing coordinator from one button and inspect recent intake attempts, including readiness status, next Hermes action, GA4/manual mode, normalized demand rows, persisted demand signals, Argus read, and summary path.

Latest demand refresh reliability slice: successful admin/API demand refreshes
now archive consumed queued uploads after the full refresh chain succeeds. Both
manual demand-import refresh and GA4-export-and-refresh move ready raw uploads
from `data/looker/{tenant}/` to `_archive/{timestamp}/`; dashboard refresh
failures leave the raw upload in place for retry. JSON refresh responses expose
the archive summary.

Latest demand work-order slice: the local-only admin operator handoff now
preserves and renders Argus' current `demand_collection_plan` and generated
`demand_plan_template`. The Run Console shows an `Argus demand work order`
block with topic count, top planned demand topics, related competitors,
evidence-reference counts, and a direct planned-template download link. The
operator API `/api/tenants/{tenant}/argus/operator-handoff` also returns the
same plan and template fields, so admin automation can inspect the current
evidence collection queue without reading raw artifacts.

Latest demand preview coverage slice: queued/manual GA or Looker demand import
previews now compare each file against the current Argus demand work order from
the Hermes data-plane manifest. The local-only API
`/api/tenants/{tenant}/argus/demand-imports` returns `demand_plan_coverage` per
queued preview, including status, planned topic count, matched topic count,
off-plan record count, matched topics, and missing topics. The admin HTML
queued-demand table now shows the same plan coverage so an operator can tell
whether an uploaded file actually covers the topics Argus requested before
running refresh.

Latest demand prepare metadata slice: demand import preparation now also uses
the same Argus demand work order. Matching manual GA / Looker rows are written
to normalized payload files with `argus_capability_key`,
`argus_assessment`, suggested filters, related competitors, evidence URLs, and
`argus_plan_matched=true`. Prepare and refresh API/form paths all pass the
current Hermes data-plane demand plan into `DemandImportStore.prepare`, so the
ledger receives plan-aware demand evidence instead of generic page-topic rows.

Latest upload coverage slice: demand import upload now uses the same Hermes
data-plane demand plan as status and prepare. The JSON upload API returns
immediate `demand_plan_coverage` for the uploaded file, and the HTML upload
form queues files through the same plan-aware store call. This closes the
operator feedback gap where upload could accept a GA / Looker file without
telling the caller whether it matched Argus' requested topics.

Latest feature comparison work-order slice: the local-only feature comparison
matrix now reads the same Hermes data-plane demand plan as the demand import
flow. Capabilities Argus has explicitly requested for demand/product proof are
shown as matrix rows even when no product proof has been captured yet. Those
cells render as `unknown`, so planned-but-unproven capabilities like `Channel
Assistant (AI Agent)` and `Complete Discovery Plan` no longer disappear from
the product-muscle view.

Latest product-muscle targeted work queue slice: Argus-planned unknown
capability cells now become explicit product-muscle work items. If a monitored
competitor already has product evidence and active product surfaces, but the
current Argus demand/product work order asks about a capability that remains
unknown for that competitor, the queue emits a targeted extraction task for
that company/capability. Hermes' `export_argus_product_muscle_work_queue.py`
now reads `argus-demand-readiness.json`, so the wrapper artifact and local
admin API stay aligned.

Scope:
- FastAPI admin app inside `src/cios/admin`.
- Read active tenants, competitors, sources, and latest source health.
- Add/edit/pause/retire competitors.
- Add/edit/pause/retire source URLs.
- Add/edit/pause/retire product surface URLs.
- HTML admin page for local operators.
- Tests for auth/local-only guard, API writes, and HTML affordances.

Verification:
- `python3 -m py_compile src/cios/admin/app.py`
- `pytest tests/admin/test_app.py::test_admin_html_lists_competitors_sources_and_add_forms tests/admin/test_app.py::test_html_forms_edit_competitor_source_and_product_surface -q`
- `pytest tests/admin/test_app.py -q`
- `pytest tests/admin -q`
- `pytest -q`
- Result after registry edit slice: `876 passed, 21 deselected`
- Result after GA4 setup-clarity slice: `877 passed, 21 deselected`

Production verification:
- Deployed to `/root/.hermes/apps/cios` after backup:
  `/root/.hermes/apps/cios/.codex-backups/admin-registry-edit-20260711T212804Z`
- Remote `py_compile` passed for `src/cios/admin/app.py`.
- Remote focused registry edit tests: `2 passed, 1 warning`.
- Remote admin app tests: `54 passed, 1 warning`.
- Remote admin folder tests: `60 passed, 1 warning`.
- Remote full package tests: `869 passed, 1 skipped, 21 deselected, 1 warning`.
- Remote package contract: `PASS: CI-OS Hermes package contract satisfied`.
- Live dashboard click validation from local E2E harness against `https://ci.chowmes.com/`: `PASS dashboard_click_validation`.
- Remote E2E browser validation was not run because the production venv lacks Playwright/browser dependencies; browser dependencies were not installed as part of this admin registry slice.
- Live GA4 connector diagnosis: disabled, no property configured, no credentials configured, no date windows configured.
- Live demand inbox diagnosis: zero queued files, zero previews, zero normalized rows.
- GA4 setup-clarity deployment backup:
  `/root/.hermes/apps/cios/.codex-backups/ga4-setup-clarity-20260711T213454Z`
- Remote GA4 setup focused tests: `2 passed, 1 warning`.
- Remote admin app tests after GA4 setup-clarity: `55 passed, 1 warning`.
- Remote admin folder tests after GA4 setup-clarity: `61 passed, 1 warning`.
- Remote full package tests after GA4 setup-clarity: `870 passed, 1 skipped, 21 deselected, 1 warning`.
- Live env render check: `Connector setup needed`, required GA4 keys, and disabled export button all present.
- Demand file-upload deployment backup:
  `/root/.hermes/backups/cios-admin-demand-file-upload-20260712T032817Z.tgz`
- Local focused demand upload tests: `4 passed, 1 warning`.
- Local admin folder tests after file-upload slice: `67 passed, 1 warning`.
- Local full package tests after file-upload slice: `941 passed, 22 deselected, 1 warning`.
- Remote focused demand upload tests: `4 passed, 2 warnings`.
- Remote admin folder tests after file-upload slice: `67 passed, 2 warnings`.
- Product-surface repair admin deployment backup:
  `/root/.hermes/backups/cios-admin-product-surface-repair-20260712T081514Z.tgz`
- Local product-surface repair admin focused tests: `39 passed, 1 warning`.
- Local admin folder tests after product-surface repair admin slice:
  `87 passed, 1 warning`.
- Local full package tests after product-surface repair admin slice:
  `1007 passed, 22 deselected, 1 warning`.
- Remote focused product-surface repair admin tests:
  `13 passed, 1 warning`.
- Remote package contract after product-surface repair admin slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote admin service restart verification:
  `active`, `NoNewPrivileges=yes`, `PrivateTmp=no`, `127.0.0.1:8765`,
  `/health` returned `{"status":"ok"}`.
- Live admin smoke:
  `html_has_product_surface_repair True`,
  `html_has_repair_action True`,
  `html_has_product_muscle_queue True`.
- Live API smoke:
  `POST /api/tenants/algolia/argus/product-surface-repair` with a non-matching
  company returned HTTP `200`, `status=no_matching_failed_surface`,
  `selected=0`, `returncode=2`.
- Remote full package tests after product-surface repair admin slice:
  `1006 passed, 1 skipped, 22 deselected, 1 warning`.
- Product-surface repair-to-refresh deployment backup:
  `/root/.hermes/backups/cios-admin-repair-refresh-20260712T082133Z.tgz`
- Local repair-to-refresh API tests:
  `2 passed, 1 warning`.
- Local admin folder tests after repair-to-refresh slice:
  `88 passed, 1 warning`.
- Local full package tests after repair-to-refresh slice:
  `1008 passed, 22 deselected, 1 warning`.
- Remote focused repair-to-refresh tests:
  `3 passed, 1 warning`.
- Remote package contract after repair-to-refresh slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote admin service restart after repair-to-refresh:
  `active`, `PrivateTmp=no`, `NoNewPrivileges=yes`, `/health` returned
  `{"status":"ok"}`.
- Live API no-match smoke:
  `POST /api/tenants/algolia/argus/product-surface-repair` returned HTTP
  `200`, `status=no_matching_failed_surface`, `selected=0`,
  `argus_refresh=None`, `argus_read=None`.
- Remote full package tests after repair-to-refresh slice:
  `1007 passed, 1 skipped, 22 deselected, 1 warning`.
- Local repair-history focused tests:
  `7 passed, 1 warning`.
- Local admin folder tests after repair-history slice:
  `92 passed, 1 warning`.
- Local full package tests after repair-history slice:
  `1012 passed, 22 deselected, 1 warning`.
- Product-surface repair-history deployment backup:
  `/tmp/cios-admin-repair-history-backup-20260712T083445Z`.
- Remote repair-history focused tests:
  `4 passed, 1 warning`.
- Remote admin folder tests after repair-history slice:
  `92 passed, 1 warning`.
- Remote admin service restart after repair-history:
  `active`.
- Live repair-history API smoke:
  `GET /api/tenants/algolia/argus/product-surface-repairs` returned
  `attempt_count=3`; latest status `no_matching_failed_surface`; previous Coveo
  attempt preserved `category=no_markdown`, `surface_id=10`, `error=HTTP 403`.
- Live admin HTML smoke:
  `/admin?tenant=algolia` contains `Latest product-surface repair attempts`.
- Remote full package tests after repair-history slice:
  `1011 passed, 1 skipped, 22 deselected, 1 warning`.
- Local demand-intake focused tests:
  `6 passed, 1 warning`.
- Local admin folder tests after demand-intake slice:
  `98 passed, 1 warning`.
- Local full package tests after demand-intake slice:
  `1018 passed, 22 deselected, 1 warning`.
- Demand-intake deployment backup:
  `/tmp/cios-admin-demand-intake-backup-20260712T084600Z`.
- Remote demand-intake focused tests:
  `6 passed, 1 warning`.
- Remote admin folder tests after demand-intake slice:
  `98 passed, 1 warning`.
- Remote admin service restart after demand-intake:
  `active`.
- Live demand-intake API smoke before operation:
  `GET /api/tenants/algolia/argus/demand-intake` returned
  `attempt_count=0`.
- Live demand-intake no-source operation smoke:
  `POST /api/tenants/algolia/argus/demand-intake` returned
  `status=blocked_missing_demand_source`, `exit_code=2`,
  `command_status=blocked`,
  `next_hermes_action=configure_ga4_or_upload_demand_export`.
- Live demand-intake history smoke after operation:
  `attempt_count=1`, latest `readiness_status=blocked_missing_demand_source`,
  `normalized_row_count=0`, `demand_signal_count=0`.
- Live admin HTML smoke:
  `/admin?tenant=algolia` contains `Argus demand intake`.
- Remote full package tests after demand-intake slice:
  `1017 passed, 1 skipped, 22 deselected, 1 warning`.
- Remote package contract after demand-intake slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Local focused demand-refresh archive tests:
  `6 passed, 1 warning`.
- Local adjacent admin/import/integration suite after demand-refresh archive
  slice: `98 passed, 2 deselected, 1 warning`.
- Local full package tests after demand-refresh archive slice:
  `1144 passed, 23 deselected, 1 warning`.
- Demand-refresh archive deployment backup:
  `/root/.hermes/backups/cios-demand-refresh-archive-20260712T225031Z.tgz`.
- Remote focused demand-refresh archive tests:
  `6 passed, 1 warning`.
- Remote adjacent admin/import/integration suite after demand-refresh archive
  slice: `98 passed, 2 deselected, 1 warning`.
- Remote full package tests after demand-refresh archive slice:
  `1143 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote package contract after demand-refresh archive slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote admin service restart after demand-refresh archive slice:
  `active`; `/health` returned `{"status":"ok"}`.
- Local demand work-order focused admin tests:
  `2 passed, 1 warning`.
- Local affected admin/operator-handoff/preflight suite after demand work-order
  slice: `145 passed, 1 warning`.
- Local full package tests after demand work-order slice:
  `1147 passed, 23 deselected, 1 warning`.
- Demand work-order admin deployment backup:
  `/root/.hermes/backups/cios-admin-demand-workorder-20260712T234338Z.tgz`.
- Remote focused admin/operator-handoff/preflight tests after demand work-order
  slice: `66 passed, 1 warning`.
- Remote admin service restart after demand work-order slice:
  `active`; `/health` returned `{"status":"ok"}`.
- Live admin HTML smoke:
  `/admin?tenant=algolia` contains `Argus demand work order`,
  `12 topics to collect`, `argus-demand-plan-template.csv`,
  `Channel Assistant`, and `Download Argus demand plan template`.
- Live admin API smoke:
  `GET /api/tenants/algolia/argus/operator-handoff` returned
  `status=blocked_on_evidence`, `topic_count=12`,
  `template=argus-demand-plan-template.csv`, and first topic
  `Channel Assistant (AI Agent)`.
- Remote full package tests after demand work-order admin slice:
  `1146 passed, 1 skipped, 23 deselected, 1 warning`.
- Local demand preview coverage RED tests first failed because
  `DemandImportStore.status()` did not accept `demand_plan`, the API did not
  call the data-plane manifest store, and the admin HTML had no plan-coverage
  column.
- Local focused demand preview coverage tests after implementation:
  `3 passed, 1 warning`.
- Local affected admin/import/demand-plan suite after implementation:
  `99 passed, 1 warning`.
- Local full package tests after demand preview coverage slice:
  `1150 passed, 23 deselected, 1 warning`.
- Local package contract after demand preview coverage slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Demand preview coverage deployment backup:
  `/root/.hermes/backups/cios-demand-preview-coverage-20260713T000154Z.tgz`.
- Remote package contract after deployment:
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote focused demand preview coverage tests:
  `3 passed, 1 warning`.
- Remote affected admin/import/demand-plan suite:
  `99 passed, 1 warning`.
- Remote full package tests after demand preview coverage slice:
  `1149 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote admin service restart after demand preview coverage slice:
  `active`; `/health` returned `{"status":"ok"}`.
- Live admin smoke:
  `GET /api/tenants/algolia/argus/demand-imports` returned tenant `algolia`
  with `queued_previews=0`; `/admin?tenant=algolia` contains `Plan coverage`
  and `Demand imports`.
- Demand prepare metadata RED tests first failed because
  `DemandImportStore.prepare()` did not accept `demand_plan` and the prepare
  API did not consult the data-plane manifest.
- Local focused demand prepare metadata tests after implementation:
  `2 passed, 1 warning`.
- Local affected admin/import/demand refresh suite after demand prepare
  metadata slice: `115 passed, 1 warning`.
- Local full package tests after demand prepare metadata slice:
  `1152 passed, 23 deselected, 1 warning`.
- Local package contract after demand prepare metadata slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Demand prepare metadata deployment backup:
  `/root/.hermes/backups/cios-demand-prepare-metadata-20260713T001108Z.tgz`.
- Remote package contract after demand prepare metadata deployment:
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote focused demand prepare metadata tests:
  `2 passed, 1 warning`.
- Remote affected admin/import/demand refresh suite:
  `115 passed, 1 warning`.
- Remote full package tests after demand prepare metadata slice:
  `1151 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote admin service restart after demand prepare metadata slice:
  `active`; `/health` returned `{"status":"ok"}`.
- Live admin smoke:
  `GET /api/tenants/algolia/argus/demand-imports` returned tenant `algolia`
  with `queued_previews=0`; `/admin?tenant=algolia` still contains
  `Plan coverage` and `Demand imports`.
- Upload coverage RED test first failed because the upload API did not consult
  the data-plane manifest and returned no plan-aware coverage.
- Local focused upload coverage test after implementation:
  `1 passed, 1 warning`.
- Local affected admin/import/demand refresh suite after upload coverage slice:
  `116 passed, 1 warning`.
- Local full package tests after upload coverage slice:
  `1153 passed, 23 deselected, 1 warning`.
- Local package contract after upload coverage slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Upload coverage deployment backup:
  `/root/.hermes/backups/cios-demand-upload-coverage-20260713T001733Z.tgz`.
- Remote package contract after upload coverage deployment:
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote focused upload coverage test:
  `1 passed, 1 warning`.
- Remote affected admin/import/demand refresh suite after upload coverage
  slice: `116 passed, 1 warning`.
- Remote full package tests after upload coverage slice:
  `1152 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote admin service restart after upload coverage slice:
  `active`; `/health` returned `{"status":"ok"}`.
- Live admin smoke:
  `GET /api/tenants/algolia/argus/demand-imports` returned tenant `algolia`
  with `queued_previews=0`; `/admin?tenant=algolia` still contains
  `Plan coverage` and `Demand imports`.
- Feature comparison work-order RED tests first failed because the
  `/argus/feature-comparison` route did not call the Hermes data-plane manifest
  store and admin HTML did not render Argus-planned capabilities.
- Local focused feature-comparison tests after implementation:
  `2 passed`.
- Local affected admin/product-muscle/export suite:
  `104 passed`.
- Local full package tests:
  `1155 passed, 23 deselected`.
- Local package contract:
  `PASS: CI-OS Hermes package contract satisfied`.
- Feature comparison work-order deployment backup:
  `/root/.hermes/backups/cios-feature-comparison-plan-20260713T003121Z.tgz`.
- Remote focused feature-comparison tests:
  `2 passed, 1 warning`.
- Remote affected admin/product-muscle/export suite:
  `104 passed, 1 warning`.
- Remote full package tests:
  `1154 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote package contract:
  `PASS: CI-OS Hermes package contract satisfied`.
- Live admin/API smoke:
  `/api/tenants/algolia/argus/feature-comparison` returned `company_count=28`,
  `row_count=189`, planned rows including `AI Shopping Agent`, `Channel
  Assistant (AI Agent)`, `Complete Discovery Plan`, and `Conversational
  Assistant (AI Agent)`; `/admin?tenant=algolia` contains `Channel Assistant
  (AI Agent)` and `Product feature comparison`.
- Targeted product-muscle RED tests first failed because no planned unknown
  capability work item was emitted and the export script had no
  demand-readiness helper.
- Local focused targeted queue/export tests:
  `3 passed`.
- Local affected product-muscle/wrapper/import/preflight suite:
  `99 passed`.
- Local full package tests:
  `1158 passed, 23 deselected`.
- Local package contract:
  `PASS: CI-OS Hermes package contract satisfied`.
- Targeted product-muscle deployment backup:
  `/root/.hermes/backups/cios-product-muscle-planned-capabilities-20260713T004051Z.tgz`.
- Remote focused targeted queue/export tests:
  `3 passed`.
- Remote affected product-muscle/wrapper/import/preflight suite:
  `99 passed`.
- Remote full package tests:
  `1157 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote package contract:
  `PASS: CI-OS Hermes package contract satisfied`.
- Live admin/API smoke:
  `/api/tenants/algolia/argus/product-muscle-work-queue` returned
  `work_item_count=45` and `targeted_capability_count=45`, with targeted items
  such as `Athos Commerce / Complete Discovery Plan` and
  `Bloomreach / Channel Assistant (AI Agent)`.
- Live Hermes export smoke:
  `scripts/export_argus_product_muscle_work_queue.py --demand-readiness
  out/argus-demand-readiness.json` produced
  `artifact_work_item_count=45` and `artifact_targeted_capability_count=45`.

Out of scope for v1:
- Public anonymous writes.
- Full auth provider integration.
- Hermes core changes.
- Auto-discovery workflows beyond manual source URL entry.
