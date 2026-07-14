# Staging Report

Status: AWAITING HUMAN APPROVAL

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

## Human gate

Approval authorizes the bounded staging sequence, including backing up the
legacy service, creating the sibling store, one real Hermes CI-OS run, the
single static-service cutover, live Playwright verification, planted defects,
and the mandatory rollback drill. It does not authorize Caddy/firewall changes,
Hermes core edits, credential changes, data deletion, Scout/GA4 work, or a
launch-ready claim.
