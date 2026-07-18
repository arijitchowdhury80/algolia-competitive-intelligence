# CI-OS Phase 2 Runbook

Date: 2026-07-16
Stage: Development-Loop Stage 13 Finish
Candidate: `11dc7df631ac84a500c833eb21659b0a98ed5cf2`
Verified run: `cios-20260716T090552Z-3890353`

## Scope

This runbook covers the Phase 2 controlled monitored pilot decision for the
CI-OS publication-integrity package. It does not authorize Phase 3 product
muscle work, Scout completion, GA4 or Looker integration work beyond the
already supplied manual export, Argus intelligence changes, production UI
redesign, Caddy changes, firewall changes, Hermes core edits, credential
rotation, or data deletion.

Current staged state:

- `/opt/cios/app` is bound to `/opt/cios/releases/11dc7df`.
- `/opt/cios/app/run-queue` is bound to `/root/.hermes/apps/cios/run-queue`.
- `/etc/fstab` points `/opt/cios/app` at `/opt/cios/releases/11dc7df`.
- `/etc/cios-env` and `/root/.hermes/cios-env` set
  `CIOS_PACKAGE_VERSION=11dc7df` and `CIOS_PUBLICATION_V2=1`.
- `cios-admin.service`, `cios-runner.path`, and
  `ci-dashboard-static.service` are active.
- `cios-static.service` is inactive.
- No public Caddy or firewall route cutover has occurred.

## Pre-Deployment Checklist

All items must be true before any production route cutover or monitored pilot
traffic increase:

- Stage 12 human acceptance is recorded for run
  `cios-20260716T090552Z-3890353`.
- GitHub Actions is green for package commit `11dc7df`.
- GitHub Actions is green for finish-artifact commit after this runbook lands.
- Local full suite evidence remains attached to the staging report:
  `1335 passed, 3 skipped, 23 deselected`.
- Pyright phase-2 project remains clean.
- Ruff over touched publication/status surfaces remains clean.
- Delegated systemd package preflight reports:
  `PASS: CI-OS Hermes package contract satisfied`.
- Publication integrity verdict is pass for the current run.
- Public status is bound to the current run and reports
  `publish_status=published`, `status=published`, and
  `public_dashboard_updated=true`.
- Strict launch readiness reports all checks true and `blockers=[]`.
- Strict launch readiness must use the served publication manifest, not the
  data-plane manifest. Valid served manifest paths are
  `/opt/cios/public-store/served/publication-manifest.json` and
  `/opt/cios/public-store/served/v2/publication-manifest.json`; the manifest
  SHA must match `manifest_sha256` in
  `/opt/cios/app/out/publication-integrity-verdict.json`.
- Dashboard click validation is run-bound to
  `cios-20260716T090552Z-3890353` and passed desktop/tablet/mobile viewports.
- Product-muscle caveats are understood as nonblocking Phase 3 follow-up:
  `work_item_count=39`, `blocking_count=0`, `limiting_count=39`.
- Human final production decision explicitly authorizes the route cutover.

## Deployment Steps

These steps are for the human-approved controlled monitored pilot only.

1. Confirm the immutable staged package:
   `CIOS_PACKAGE_VERSION=11dc7df`.
2. Confirm `CIOS_PUBLICATION_V2=1` in both `/etc/cios-env` and
   `/root/.hermes/cios-env`.
3. Confirm `cios-admin.service` and `cios-runner.path` are active.
4. Confirm `ci-dashboard-static.service` still serves the staged dashboard.
5. Re-run one Hermes-owned queue request and confirm:
   - runner exit code `0`
   - publication integrity pass
   - source coverage `checked=42`, `failed=0`
   - public status current-run and publishable
   - strict launch readiness `blockers=[]` using the served
     `publication-manifest.json`
6. If and only if the human production decision authorizes it, switch the
   public route to the staged dashboard service using the approved Caddy
   change plan.
7. Do not change firewall rules during this cutover.
8. Do not modify Hermes core during this cutover.
9. Preserve the previous public service and config backup until the 48-72 hour
   feedback window closes.

## Post-Deploy Validation: First 15 Minutes

Start this window immediately after any route cutover.

| Minute | Check | Pass Criteria | Owner |
| --- | --- | --- | --- |
| 0 | Route health | Public route returns HTTP 200 for dashboard root | Codex/operator |
| 2 | Public status | Current run ID matches latest Hermes-owned run | Codex/operator |
| 4 | Publication integrity | Current verdict is pass | Codex/operator |
| 6 | Source coverage | Active and checked sources match; failures remain 0 | Codex/operator |
| 8 | Dashboard interaction | Navigation, timeline, semantic layer, brief route, and appendices work | Codex/operator |
| 10 | Logs | No new `cios-admin`, `cios-runner`, Caddy, or gateway errors | Codex/operator |
| 12 | Product caveats | Phase 3 limiter count remains visible, not hidden | Codex/operator |
| 15 | Launch readiness | Strict readiness stays pass with `blockers=[]` | Codex/operator |

## Rollback Trigger

Rollback immediately if any of these occur:

- Public route serves a stale run, mismatched manifest, partial copy, or path
  leak.
- Strict launch readiness returns any blocker.
- Publication integrity fails.
- Dashboard click validation fails on the public route.
- Source failure count becomes nonzero without a documented disposition.
- Caddy route change breaks unrelated Chowmes/Hermes services.
- Any secret, filesystem path, or private Looker export path appears in public
  artifacts.
- Operator sees a misleading launch-ready claim that hides Phase 3 caveats.

## Rollback Procedure

1. Revert the public route to the prior known-good Caddy target.
2. Keep `/opt/cios/app` bound to the immutable staged package unless the staged
   package itself is implicated.
3. If the staged package is implicated, restore the previous release bind mount
   and matching `CIOS_PACKAGE_VERSION`.
4. Restart only the impacted service.
5. Re-run route health, public status, publication integrity, and click
   validation.
6. Record the rollback in the development-loop feedback artifact before any
   new deployment attempt.

## Monitoring Table

| Signal | Source | Cadence | Alert Condition |
| --- | --- | --- | --- |
| Public route health | HTTP status and dashboard root | 0, 5, 15 minutes, then hourly for 48h | non-200 or stale bundle |
| Run binding | public status JSON | 0, 5, 15 minutes, then hourly for 48h | run ID mismatch |
| Publication integrity | verdict artifact | every run and after cutover | verdict not pass |
| Source coverage | run health artifact | every run | active != checked or failed > 0 |
| Product caveats | product-muscle queue | every run | blocking > 0 or limiter caveats hidden |
| Dashboard behavior | Playwright click verdict | cutover, 15 minutes, next daily run | failed interaction or viewport |
| Service health | `systemctl` and logs | cutover, 15 minutes, next daily run | errors or inactive expected service |
| Public safety | artifact scan | every run | secret/path/private export leak |

## Feature Flag Cleanup Criteria

`CIOS_PUBLICATION_V2` stays enabled during the controlled monitored pilot. It
can be considered permanent only after:

- Stage 14 feedback window is complete.
- At least one next daily Hermes-owned run passes strict readiness.
- No rollback trigger fires during the first 48-72 hours.
- Phase 3 product-muscle caveats are either resolved or explicitly accepted as
  nonblocking by the human decision record.
- The legacy publication path is documented as removable and has a rollback
  alternative.

Until those criteria are met, do not remove the flag, delete the legacy path,
or claim full Algolia pilot completion.
