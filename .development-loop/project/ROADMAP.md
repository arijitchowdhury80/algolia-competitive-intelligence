# CI-OS Roadmap

Canonical roadmap: `docs/plan/2026-07-13-ci-os-completion-plan.md`.

Phase 0 passed on 2026-07-13. The clean retained baseline is commit
`12b97ae6c6fb121a308e9755e7076b6291a04302` on
`codex/ci-os-phase0-baseline`.

Phase 1 passed on 2026-07-14 at deployed commit `1fa7ac5` after two consecutive
real Hermes cron executions completed as `cios` with clean containment.

Phase 2 staging passed on 2026-07-16 at package commit `11dc7df` after a
Hermes-owned run completed as `cios-20260716T090552Z-3890353` and strict launch
readiness returned all checks true with `blockers=[]`.

Current active gate: Stage 13 final production decision for the Phase 2
controlled monitored pilot.

Do not begin Phase 3 until the Stage 13 human production decision is resolved.
Phase 3 currently owns the 39 visible confidence-limiting, nonblocking
product-muscle work items.
