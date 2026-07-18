# PRD

## Summary

Build the CI-OS publication boundary that validates and promotes one immutable
run generation while preserving honest blocked diagnostics.

## Objective

- Reject every documented planted defect.
- Preserve one-generation consistency for root and `/v2` routes.
- Pass one real Hermes publication-integrity run without weakening product
  launch gates.

## Consumers

The Hermes-triggered CI-OS wrapper, admin refresh path, public static server,
launch validator, Argus operator, and Algolia business readers.

## Solution and acceptance

The detailed API, release layout, safety rules, rollback, and acceptance
criteria are canonical in
`.development-loop/run-2026-07-14-002/04-spec.md` and
`.development-loop/run-2026-07-14-002/02-requirements.md`.

V1 includes immutable generations, manifest/hash validation, safety scanning,
run propagation, structured evidence, atomic pointers, and status-last. It does
not include new evidence sources, recommendation logic, or UI work.

Open questions: none block local implementation. Production service cutover
remains the staging gate.
