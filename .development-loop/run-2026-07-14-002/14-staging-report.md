# Staging Report

Status: FAILED AND ROLLED BACK; AWAITING PHASE-ORDER DECISION

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

## Required human decision

The recommended choice is to amend the Phase 2 live gate so a fresh,
run-bound blocked diagnostic plus the planted-defect matrix proves publication
integrity, while the legacy decision surface remains live until Phase 4
produces the first truthful decision generation. The alternative is to
authorize and provide the GA4/Looker demand path now, explicitly reordering
Phase 4 ahead of the Phase 2 decision-publication proof.

No Scout, GA4/Looker, Argus intelligence, production UI, Caddy, firewall, or
Hermes core work began during this staging attempt.

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
