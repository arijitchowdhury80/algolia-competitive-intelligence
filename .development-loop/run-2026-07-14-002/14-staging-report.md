# Staging Report

Status: FAILED CANDIDATE RETAINED; DEMAND-PATH REORDER AUTHORIZED

Draft package PR #1 targets the dedicated `ci-os-package-main` source branch.
Its GitHub static/unit and Postgres integration checks pass. The PR remains a
draft, and this automated evidence does not authorize the staging sequence.

## Verified current production baseline

Read-only inspection on 2026-07-14 confirmed:

- `cios` exists as UID 997, primary group `cios`, supplementary group `hermes`.
- `/opt/cios/app` is owned by `cios:cios`.
- `ci-dashboard-static.service` is active on `127.0.0.1:8662`.
- The legacy service runs as root with no memory, CPU, or task limit.
- Its document root is the retained mutable dashboard directory under the
  Algolia Competitive Intelligence package.
- `/opt/cios/public-store` does not yet exist.

No production file, process, service, Caddy route, firewall rule, credential,
Hermes core file, or public response changed during inspection.

### Baseline revalidation

A second read-only inspection at `2026-07-14T10:50Z` found no staging drift:

- `ci-dashboard-static.service` remains active as `root:root`, serving the
  retained mutable dashboard root on `127.0.0.1:8662` with unlimited memory
  and CPU and `TasksMax=9483`.
- `cios-static.service` is not installed or active, and
  `/opt/cios/public-store` remains absent.
- Loopback and public root responses are both HTTP 200, 394,895 bytes, and
  SHA-256 `280b721bb5276394abac2d4ea1547c1883d1b2b6e94a993a919d4b316dff5db7`.
- Caddy runs in the `caddy` Docker container, not as a host systemd unit. Its
  active config is mounted from `/home/chowmesadmin/lab-judge/Caddyfile`; the
  `ci.chowmes.com` route reverse-proxies only to `127.0.0.1:8662`, and
  `caddy validate` reports `Valid configuration`.
- The local candidate archive still hashes to
  `0e83a836fe75689e5ceac1f89fe02337458dc7e65f87e94031e452a6a7ee9298`,
  and candidate tree `47d3bd7^{tree}` remains
  `ef09b04cfe9a0e4d5b3cf5f7008693a10b3a14eb`.

The staging sequence therefore requires no Caddy edit or reload. Cutover and
rollback change only which loopback static service owns port 8662.

## Executed staging evidence

Arijit approved the bounded Stage 12 sequence on 2026-07-14. Execution stopped
before the static-service cutover because the sibling store never produced a
complete decision generation.

### Installation and rollback baseline

- Root-only rollback snapshot:
  `/opt/cios/staging-backups/20260714T134100Z`.
- Legacy unit SHA-256:
  `ef8ec58d139456b09c1cc7612263f91031b865bf5d4c5a35c8824ecf61a90f71`.
- Legacy loopback and public root SHA-256:
  `280b721bb5276394abac2d4ea1547c1883d1b2b6e94a993a919d4b316dff5db7`.
- Candidate archive was reverified on the VPS before extraction and installed
  at `/opt/cios/releases/47d3bd7`.
- Off-route and mounted package preflights both passed in delegated systemd
  cgroups.
- `/opt/cios/public-store` was created as `cios:hermes` mode `2750`; the
  release, store, backup, and diagnostic evidence remain retained.

### Attempt 1: runtime dependency and package-mode failures

- Queue request: `ea34d298445944edb8ab3cae9022b81c`.
- Terminal result: exit code 2 before publication.
- Sanitized cause: the localhost Claude shim was unhealthy because its shared
  virtualenv executable was mode `0750` and inaccessible to `cios-shim`.
- `ExecStopPost` also returned `203/EXEC` because
  `deploy/cios-run-finalize.sh` was archived without an executable bit.
- The shim was repaired with a dedicated `cios-shim` virtualenv while the old
  link was preserved. Its real health check then returned `healthy=true` on
  `127.0.0.1:8663`.
- Candidate runtime scripts were corrected to their documented deployment
  modes before the changed-hypothesis retry.

### Attempt 2: healthy execution, truthful diagnostic publication

- Queue request: `f9a040a200384c3799ce7fed233ecfd4`.
- CI-OS run ID: `cios-20260714T135025Z-1989449`.
- Hermes wrapper result, runner main process, and finalizer: exit code 0.
- Package contract verdict: pass and run-bound.
- Publication integrity verdict: pass and run-bound.
- Demand source gate: fail, with zero processed demand rows and no ready GA4
  or manual export.
- Public run status: `blocked_on_evidence`, `publish_status=blocked`, and
  `public_dashboard_updated=false`.
- The immutable store correctly promoted only
  `latest-diagnostics -> diagnostics/cios-20260714T135025Z-1989449`; it did not
  create a `current` decision pointer.

This is correct product behavior, but it cannot satisfy the Phase 2 exit gate
or support the static-service cutover. The approved plan requires one fresh,
complete decision run in Phase 2 while simultaneously locking GA4/Looker work
until Phase 2 passes. Creating a false `published` status, migrating stale
legacy bytes as fresh evidence, or serving a router with no `current` pointer
would lower the gate and is prohibited.

### Rollback result

- `/opt/cios/app` is again the original
  `/root/.hermes/apps/cios` bind mount.
- The pre-staging `/etc/cios-env`, `/root/.hermes/cios-env`, and `/etc/fstab`
  bytes were restored; publication-v2 flags are absent.
- `ci-dashboard-static.service` was never stopped. Loopback and public hashes
  remain the exact legacy baseline.
- `cios-runner.path`, `cios-admin.service`, and the repaired
  `cios-claude-shim.service` are active and localhost-only.
- Restart exposed a second latent package defect: `cios-admin.service` lacked
  `PYTHONPATH=/opt/cios/app/src`. A minimal systemd drop-in restored the admin
  to HTTP 200. The versioned unit and preflight contract are being corrected
  under TDD.

Candidate `47d3bd7` is not eligible for another staging attempt. Its immutable
tag and files remain evidence; a new candidate must include the executable and
admin import-path fixes and pass CI before use.

## Human decision: bring the demand input forward

On 2026-07-14 Arijit authorized read-only access to the private Algolia Looker
Studio report and manual CSV export so the real demand input can be supplied
before the final Phase 2 publication proof. This is an explicit, narrow
reordering of the Phase 4 demand-input dependency. It does not authorize Scout,
GA4 credential setup, report editing, production UI work, Caddy or firewall
changes, or Hermes core changes.

The authenticated report was inspected without editing it. The selected
current window was 2026-07-07 through 2026-07-13 and the comparison window was
2026-06-30 through 2026-07-06. Raw exports were saved only in the untracked
`data/` directory of the separate local CI-OS checkout and must not be committed
to GitHub. Verified raw evidence:

- `algolia-looker-page-metrics_2026-07-07_2026-07-13.csv`: 100 parsed
  data rows; SHA-256
  `d61c96717f3cb3682baf0c7c2da47b6ca31a41989608c89ff42df8904c50149c`.
- `algolia-looker-landing-page-metrics_2026-07-07_2026-07-13.csv`: 100
  parsed data rows; SHA-256
  `2d641d6071084a05b6a0cfb8a64b3b015f977278b24af429be9c24c097ce2cee`.
- `algolia-looker-campaign-metrics_2026-07-07_2026-07-13.csv`: 100 parsed
  data rows; SHA-256
  `666783216400646be80d7f7a800a3d5db02f7881db9449d9a61652cc5094b48e`.
- `algolia-looker-campaign-metrics_2026-06-30_2026-07-06.csv`: 100 parsed
  data rows; SHA-256
  `8b8444de3f8af844712f402167df30a785771d76555eff13356859368d019124`.
- `algolia-looker-landing-page-device-sessions_2026-06-30_2026-07-06.csv`:
  10,558 parsed data rows; SHA-256
  `ad27f9db658c519035e9e6f6dfd969dba9559c9bd84668d1c4608ee62bbb0243`.

The package `.gitignore` excludes `data/`; private tenant exports are not
package inputs and cannot enter a release through a broad Git add.

The eligible minimum intake row is the current `/products/ai-search` page:
786 sessions in the selected seven-day window, mapped explicitly to the active
Argus topic `Agent Search`. The prior landing-page export contains 751 sessions
for the same path, but it uses a different chart dimension from the current
page export. It is corroborating evidence only; CI-OS must not calculate or
publish a synthetic week-over-week change from unlike dimensions. Coverage is
therefore one directly mapped active topic with a real nonzero metric and
explicit unknown coverage for the remaining topics.

Package-owned local validation against the live Argus plan passed before any
upload: `status=prepared`, `ready_count=1`, `normalized_row_count=1`,
`skipped_row_count=0`, `duplicate_row_count=0`, coverage `covered`, one matched
plan topic, zero missing topics, and zero off-plan rows. The normalized source
fingerprint is
`5ce535e8db8cce5d3decebd6c509706b065b60b6cc3f37ae1b1aba5bb6f79352`.
The focused importer and demand fast-lane suite passed `32 passed`.

Fresh-candidate local verification also passed: the default suite reported
`1321 passed, 3 skipped, 23 deselected`; Ruff passed; Pyright reported zero
errors, warnings, or information findings; strict MyPy passed; and the Hermes
package contract passed. The workstation-wide `pip check` still reports two
unrelated pre-existing `python-jobspy` constraints against the globally
installed NumPy and regex versions. No package dependency changed in this
slice; the clean GitHub Actions environment remains the authoritative package
dependency gate before a new candidate can be tagged or installed.

Candidate `47d3bd7` remains failed and ineligible. The next attempt must use a
fresh immutable candidate containing the package fixes after that tag, import
the verified demand row through the package-owned intake path, and rerun every
remaining Stage 12 gate before public cutover.

## Proposed bounded staging sequence

1. Install immutable Phase 2 candidate `47d3bd7` under
   `/opt/cios/releases/47d3bd7` after verifying archive SHA-256
   `0e83a836fe75689e5ceac1f89fe02337458dc7e65f87e94031e452a6a7ee9298`,
   then point `/opt/cios/app` at it as `cios`.
2. Back up the exact legacy `ci-dashboard-static.service` unit and record the
   legacy root plus public response hashes. Do not remove either rollback target.
3. Create `/opt/cios/public-store` as `cios:hermes` mode `2750` and run package
   preflight as `cios`.
4. Enable `CIOS_PUBLICATION_V2=1` with the exact package version, trigger one
   real Hermes-owned CI-OS run, and validate the sibling store before changing
   the live route.
5. Probe the candidate `served/` root on a temporary loopback port, then stop
   the probe.
6. Stop only `ci-dashboard-static.service`, install/start `cios-static.service`
   on the same loopback port, and leave Caddy/firewall unchanged.
7. Verify process user/group, cgroup limits, root and `/v2` hashes, public-safe
   status, package/publication/click/launch verdicts, and Playwright desktop and
   mobile journeys.
8. Execute the approved stale/mismatched/partial/symlink/path/secret defect
   matrix and verify every case fails without moving the decision pointer.
9. Execute the rollback drill below, verify the legacy public response, then
   return to the candidate only if every rollback check passes.

## Rollback drill

Trigger rollback on any failed health, ownership, route, hash, click, launch,
or process-limit check:

1. Stop and disable only `cios-static.service`.
2. Restore the backed-up legacy unit if its bytes changed.
3. Start `ci-dashboard-static.service` against the retained legacy root.
4. Verify `127.0.0.1:8662`, `https://ci.chowmes.com/`, service user/root,
   response hashes, and Caddy health.
5. Leave the failed immutable release and sibling store intact for diagnosis;
   do not delete evidence during rollback.

## Original human gate

Approval authorizes the bounded staging sequence, including backing up the
legacy service, creating the sibling store, one real Hermes CI-OS run, the
single static-service cutover, live Playwright verification, planted defects,
and the mandatory rollback drill. It does not authorize Caddy/firewall changes,
Hermes core edits, credential changes, data deletion, Scout/GA4 work, or a
launch-ready claim.
