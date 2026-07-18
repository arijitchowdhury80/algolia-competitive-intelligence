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

Phase 2 controlled monitored pilot cutover passed on 2026-07-17 for public run
`cios-20260717T130034Z-890867`. The 15-minute validation window passed and
strict readiness ended with `status=pass`, `exit_code=0`, and `blockers=[]`.

Current active gate: Stage 14 feedback monitoring for the Phase 2 controlled
pilot.

Do not begin Phase 3 until the Stage 14 monitoring baseline is recorded or any
post-cutover findings are explicitly accepted. Phase 3 currently owns the
visible confidence-limiting, nonblocking product-muscle work items.
