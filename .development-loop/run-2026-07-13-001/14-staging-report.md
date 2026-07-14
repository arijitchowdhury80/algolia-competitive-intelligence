# Staging Report

Date: 2026-07-14
Verdict: PASS
Human gate: covered by Arijit's standing autonomous-goal authorization and
explicit approval to deploy and run the cgroup design.

## Deployment

- Package commit: `1fa7ac5`
- Archive: `/opt/cios/releases/1fa7ac5.tar.gz`
- SHA-256:
  `63b3c56e7129c8c710e895d29c72a57c02986ef92bdfa10afbe162b275da255c`
- Backup: `/opt/cios/backups/pre-1fa7ac5-20260714T035200Z`
- Public wrapper SHA-256:
  `feb00bcc5656f9f6f2f9c5960f2b370a6040ccdc09443e72cf1fc20739fd9478`

Hermes core, SSH, firewall, Caddy, and public exposure were unchanged.

## Smoke And Observability

- Container queue-client startup as `hermes`: PASS.
- Linux package preflight as `cios` in delegated transient cgroup: PASS.
- `cios-runner.path`: active.
- Queue ownership: `cios:hermes`, mode 3770.
- Private state/log ownership: `cios:cios`, no group access.
- systemd journal, queue state, private log metadata, public run status, process
  identity, and cgroup membership were observed during both runs.

## Live Journeys

| Request | Result | Runtime | Cleanup |
|---|---:|---:|---|
| `a70f4e219d294280a26703962c9be4e9` | 0 | 14m 06s | clean |
| `1b938c9de92f4568a059bdb84d3f9e6b` | 0 | 8m 39s | clean |

Both runs had zero permission and traceback indicators. After each run, the
service was inactive, `active-run` and the service cgroup were absent, no shim
job remained, and a 30-second hash window showed no late writes.

## Rollback Drill

The immutable archive was extracted to
`/tmp/cios-rollback-drill-1fa7ac5`. Package preflight ran as `cios`, shell
syntax passed, and the extracted wrapper matched the live wrapper. No live
service or data was changed during the drill.

## Feature Flags And UI

No feature flag or browser UI changed in Phase 1. Playwright is not applicable
to this runtime ownership gate.
