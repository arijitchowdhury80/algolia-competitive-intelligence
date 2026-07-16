# CI-OS Changelog

## 2026-07-16

- Passed Phase 2 staging for immutable candidate `11dc7df` with Hermes-owned
  run `cios-20260716T090552Z-3890353`.
- Verified strict launch readiness with all checks true and `blockers=[]`.
- Preserved visible Phase 3 product-muscle caveats: 39 confidence-limiting,
  nonblocking work items.
- Added the Stage 13 controlled-pilot runbook and verdict. Production route
  cutover remains blocked on the final human decision gate.

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
