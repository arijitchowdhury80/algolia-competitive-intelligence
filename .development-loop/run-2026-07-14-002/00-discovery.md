# Discovery

## Authoritative inputs

- Goal charter: `docs/goals/2026-07-13-complete-ci-os-algolia-pilot.md`
- Completion plan: `docs/plan/2026-07-13-ci-os-completion-plan.md`
- Phase 1 verdict: `.development-loop/run-2026-07-13-001/16-verdict.md`
- Deployed code commit: `1fa7ac5`
- Phase 1 documentation head: `dea1816`

## Current publication path

The Hermes app wrapper writes one mutable `$OUT` directory, deletes its prior
contents, and runs the daily pipeline. The daily runner creates an internal
`daily-<tenant>-<epoch>` run ID, but the wrapper does not own or export a
top-level run identity. The data-plane manifest and public status do not carry
that run ID.

The successful path copies artifacts into `.argus-publish.<pid>` and then
copies them one by one into the live public root. This is staging, but not
atomic promotion. The status is copied before optional demand artifacts and
before the briefs tree. The Python admin refresh helper mirrors the same
sequential behavior. The blocked path updates public status and demand helper
files while correctly retaining the last decision surface.

The launch gate currently trusts two PASS substrings and three self-attested
safety booleans. It has no freshness limit, shared run-ID check, artifact hash
manifest, recursive final-artifact scan, source-disposition proof, or
current-run product-extraction completeness check.

## Live serving boundary

`ci.chowmes.com` reverse proxies to a root-owned Python static server on
`127.0.0.1:8662`. The server reads the mutable dashboard `public/` directory
directly. Caddy itself does not need to change for atomic publication. A
sibling release store plus a stable served router can be cut over by changing
only the static server document root. The existing public directory can remain
as an immediate rollback target. The static server does not require root and
should run as `cios`, consistent with the application-user boundary.

## Discovery constraints

- Hermes core remains untouched.
- Scout, GA4/Looker, Argus recommendation work, and production UI are out of
  scope.
- No new public route or admin surface is introduced.
- Agent-thread capacity was exhausted, so Discovery and Architecture Review
  are performed inline as permitted by the workflow.

## Verdict

The failures and the serving boundary are understood. No unresolved product or
access decision is required before local implementation.
