# CI-OS Admin Run Console

Status: in progress

Goal: expose the latest Hermes/Argus run evidence in the local admin surface so operators can inspect what ran, what Argus prioritized, and which learning instructions affected product-surface planning.

Current slice:

- Add a read-only admin API for latest run status.
- Render a compact Run Console section on the local-only admin page.
- Persist product-market chain summary into report metadata after the chain runs.
- Keep this inside CI-OS; do not touch Hermes core.

## 2026-07-12 UTC - Argus data-plane manifest surfaced in admin

- Added a package-local `ArgusDataPlaneManifestStore` for
  `argus-data-plane-manifest.json`.
- Added a read-only admin endpoint:
  `/api/tenants/{tenant_slug}/argus/data-plane-manifest`.
- Added an `Argus operating planes` block to the admin run console. It exposes:
  registry coverage, product reality, market conversation, audience demand,
  operator learning, and run truth.
- The block shows source of truth, manifest status, Argus readiness, next Hermes
  action, per-plane status/counts/storage, top blockers, and artifact path.
- The package preflight now requires
  `src/cios/admin/data_plane_manifest.py`, so deployable CI-OS packages cannot
  ship the manifest exporter without the local operator inspection surface.

Verification:

```bash
.venv/bin/python -m pytest \
  tests/admin/test_data_plane_manifest.py \
  tests/admin/test_app.py \
  tests/scripts/test_verify_hermes_package_contract.py -q
```

Result: 79 passed, 1 Starlette/httpx deprecation warning.

Remote production verification:

```bash
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest \
  tests/admin/test_data_plane_manifest.py \
  tests/admin/test_app.py \
  tests/scripts/test_verify_hermes_package_contract.py -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q --tb=short -p no:cacheprovider
```

Result:

- Preflight: PASS.
- Focused remote bundle: 79 passed, 1 Starlette/httpx deprecation warning.
- Full remote suite: 955 passed, 1 skipped, 22 deselected, 1 Starlette/httpx
  deprecation warning.
- Production manifest read through `ArgusDataPlaneManifestStore`: artifact found
  at `/root/.hermes/apps/cios/out/argus-data-plane-manifest.json`, status
  `blocked_on_evidence`, next Hermes action
  `configure_ga4_or_upload_demand_export`, six operating planes present.
- Admin API route `/api/tenants/algolia/argus/data-plane-manifest` returned 200
  in-process on the VPS with `audience_demand=blocked_missing_demand_source`.
- Public sidecar `https://ci.chowmes.com/data/argus-data-plane-manifest.json`
  reports `blocked_on_evidence`, `not_actionable`, one blocker, and the same next
  Hermes action.
