# Discovery

## Authoritative inputs

- Goal charter: `docs/goals/2026-07-13-complete-ci-os-algolia-pilot.md`
- Completion plan: `docs/plan/2026-07-13-ci-os-completion-plan.md`
- Dossier: `docs/status/2026-07-13-ci-os-project-dossier.md`
- Phase 0 source baseline: `12b97ae6c6fb121a308e9755e7076b6291a04302`

## Current evidence

The Unix ownership boundary is working live. Hermes queues the run, the host
runner executes as `cios`, and the model shim executes as `cios-shim`.

The 2026-07-13 23:51 UTC product-surface stage planned 53 items with three
workers. Its child command allowed 300 seconds per export, while the enclosing
stage allowed only 240 seconds. The stage timed out at 240.104 seconds. Export
files continued to be written for roughly seven seconds after the enclosing
stage reported failure, proving descendant cleanup was incomplete.

No Scout, demand-plane, intelligence, or production-UI scope is unlocked by
this recovery work.

## Discovery verdict

The failure is reproducible from configuration and live timestamps. Continue
to the approved Phase 1 repair. No unresolved discovery question requires a
human decision.
