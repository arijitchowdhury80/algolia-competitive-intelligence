# CI-OS Changelog

## 2026-07-14

- Added delegated cgroup v2 containment and a dedicated `cios` runtime owner.
- Added the secure Hermes-to-systemd request queue and private finalization.
- Corrected host/container queue namespaces and selected Hermes' trusted Python
  for the container-side queue client.
- Deployed immutable release `1fa7ac5` and passed the rollback-bundle drill.
- Passed Phase 1 with two consecutive real Hermes runs, both exit 0 and clean.

## 2026-07-13

- Created local Phase 0 review branch `codex/ci-os-phase0-baseline`.
- Added hygiene commit `b5787b1` to quarantine generated artifacts and remove
  tracked `.DS_Store` metadata from the source set.
