# CI-OS Demand Import Diagnostics

Status: completed

Goal: make the inward demand plane accept realistic GA4 / Looker Studio page exports and explain skipped rows instead of silently producing an empty demand plane.

Changes:

- `src/cios/intelligence/importers.py`
  - Added `diagnose_looker_rows`.
  - Supports real GA4 / Looker headers such as `Page title and screen name`, `Landing page + query string`, `Engaged sessions (previous period)`, and `Date range`.
  - Parses date ranges such as `Jul 1, 2026 - Jul 8, 2026`.
  - Preserves the existing normalized-row contract.
- `src/cios/admin/demand_imports.py`
  - Adds skipped-row diagnostics to the demand import manifest.
  - Shows `reason`, `missing_fields`, `row_number`, `source_file`, and `available_columns`.

Verification:

- Local focused red/green tests: 3 passed.
- Local demand/admin path tests: 74 passed.
- Local full suite: 873 passed, 21 deselected.
- Remote focused tests: 3 passed, 1 warning.
- Remote demand/admin path tests: 74 passed, 1 warning.
- Remote full suite: 866 passed, 1 skipped, 21 deselected, 1 warning.
- Remote prepare-only smoke normalized a real-looking GA4 export into `topic=AI Shopping Agent`, `value=1240.0`, `period_start=2026-07-01T00:00:00+00:00`, `period_end=2026-07-08T00:00:00+00:00`.

## Admin-visible Diagnostics Extension

Status: deployed to production host.

Problem addressed:

- The admin API and importer could diagnose bad GA / Looker rows, but the HTML operator surface still hid those reasons.
- The Hermes daily runner prepared Looker exports without writing the same row-level diagnostics into its run manifest.

Changes:

- `scripts/daily_production_run.py`
  - Uses `diagnose_looker_rows` when preparing Looker exports.
  - Daily run manifest entries now include `skipped_rows` and `duplicate_row_count`.
- `src/cios/admin/app.py`
  - Adds a `Demand import diagnostics` table.
  - Shows skipped row file, row number, reason, missing fields, and available columns.

Verification:

- Local focused tests: 2 passed.
- Local admin/daily/importer path tests: 131 passed.
- Local full suite: 874 passed, 21 deselected.
- Remote focused tests: 2 passed, 1 warning.
- Remote admin/daily/importer path tests: 131 passed, 1 warning.
- Remote full suite: 867 passed, 1 skipped, 21 deselected, 1 warning.

## GA4 Fast Lane To Argus Refresh

Status: implemented locally, pending deployment verification.

Problem addressed:

- The admin surface could run a GA4 export into the tenant demand drop folder.
- A separate action could prepare queued demand exports, persist demand signals,
  refresh Argus from the evidence ledger, and refresh dashboard artifacts.
- When GA4 was ready, Hermes still had two operator actions to sequence instead
  of one safe package-owned action from GA4 to a demand-backed Argus read.

Changes:

- `src/cios/admin/app.py`
  - Added `POST /api/tenants/{tenant_slug}/argus/ga4-export/refresh`.
  - Added `POST /admin/{tenant_slug}/argus/ga4-export/refresh`.
  - Both routes use the same shared action:
    1. Run GA4 export into the tenant drop folder.
    2. Prepare the queued demand file through `DemandImportStore`.
    3. Persist normalized demand rows to the product-market ledger.
    4. Refresh Argus from persisted evidence.
    5. Refresh dashboard/public artifacts through the admin dashboard runner.
  - The JSON response returns the GA4 export summary, demand import summary,
    demand ledger write summary, ledger refresh summary, extracted Argus read,
    and dashboard refresh summary.
  - Secret credential paths stay out of the response.
- `scripts/export_argus_demand_readiness.py`
  - When GA4 is ready, the first operator action is now
    `Run GA4 export and refresh Argus`, pointing to
    `/admin/{tenant}/argus/ga4-export/refresh`.

Local focused verification:

```bash
.venv/bin/python -m pytest \
  tests/admin/test_app.py::test_json_api_runs_ga4_export_and_refreshes_argus_in_one_operator_action \
  tests/admin/test_app.py::test_json_api_blocks_ga4_refresh_when_dashboard_refresh_fails \
  tests/admin/test_app.py::test_admin_html_shows_ga4_connector_and_form \
  tests/admin/test_app.py::test_admin_html_can_run_ga4_export_and_refresh_argus_when_ready \
  tests/scripts/test_export_argus_demand_readiness.py::test_export_argus_demand_readiness_marks_ga4_ready_to_export -q
```

Result: 5 passed, 1 Starlette/httpx deprecation warning.

Remote production verification:

```bash
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/admin/test_app.py \
  tests/scripts/test_export_argus_demand_readiness.py \
  tests/scripts/test_import_demand_and_refresh.py \
  tests/scripts/test_export_ga4_demand.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q --tb=short -p no:cacheprovider
```

Result:

- Preflight: PASS.
- Remote demand/admin/GA4 bundle: 74 passed, 1 Starlette/httpx deprecation
  warning.
- Remote full suite: 958 passed, 1 skipped, 22 deselected, 1 Starlette/httpx
  deprecation warning.
- Production GA4 status is currently `disabled`: no property, date window, or
  credentials are configured; the export script is present.
- In-process admin route smoke:
  - `GET /api/tenants/algolia/argus/ga4-export` returned 200 with
    `status=disabled`, `ready=false`.
  - `POST /api/tenants/algolia/argus/ga4-export/refresh` returned controlled
    400 with `GA4 export is not ready: GA4 export disabled`.
  - `/admin?tenant=algolia` includes `Run GA4 export and refresh Argus`, disabled
    while GA4 is not ready.
- Public data-plane manifest still reports `blocked_on_evidence`,
  `audience_demand=blocked_missing_demand_source`, and next Hermes action
  `configure_ga4_or_upload_demand_export`.

## GA4 Rolling Date Windows

Status: implemented locally, pending deployment verification.

Problem addressed:

- GA4 export previously required static `CIOS_GA4_CURRENT_*` and
  `CIOS_GA4_PREVIOUS_*` dates.
- Static dates make a daily Hermes job silently stale unless an operator updates
  env vars every day.

Changes:

- `src/cios/intelligence/ga4_exporter.py`
  - Added `resolve_ga4_date_windows`.
  - Explicit date env vars still win when all four are present.
  - If dates are omitted, CI-OS computes a rolling complete-day comparison
    window:
    - current: last `CIOS_GA4_ROLLING_DAYS` complete UTC days, default 7
    - previous: the immediately preceding same-size window
  - `CIOS_GA4_TODAY` is supported for deterministic tests/backfills.
- `src/cios/admin/demand_imports.py`
  - GA4 readiness no longer requires static date env vars.
  - Admin status reports the computed current and previous windows.
  - Partial explicit date configuration is still treated as not ready.
- `scripts/daily_production_run.py`
  - Hermes daily GA4 export now uses the shared rolling-window resolver.

Local verification:

```bash
.venv/bin/python -m pytest \
  tests/intelligence/test_ga4_exporter.py \
  tests/admin/test_app.py \
  tests/scripts/test_export_argus_demand_readiness.py \
  tests/scripts/test_export_ga4_demand.py \
  tests/scripts/test_daily_run.py -q
```

Result: 172 passed, 1 Starlette/httpx deprecation warning.

Remote production verification:

```bash
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/intelligence/test_ga4_exporter.py \
  tests/admin/test_app.py \
  tests/scripts/test_export_argus_demand_readiness.py \
  tests/scripts/test_export_ga4_demand.py \
  tests/scripts/test_daily_run.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q --tb=short -p no:cacheprovider
```

Result:

- Preflight: PASS.
- Remote GA4/admin/daily bundle: 172 passed, 1 Starlette/httpx deprecation
  warning.
- Remote full suite: 962 passed, 1 skipped, 22 deselected, 1 Starlette/httpx
  deprecation warning.
- Live production GA4 status remains `disabled`, but now computes the rolling
  window that will be used once GA4 is enabled:
  - current: `2026-07-05` to `2026-07-11`
  - previous: `2026-06-28` to `2026-07-04`
  - export script present: true
