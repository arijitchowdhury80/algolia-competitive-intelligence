# Intake

## Problem and users

CI-OS can produce correct artifacts while still exposing a mixed generation,
accepting stale or spoofed validation evidence, or publishing a status that is
not bound to the decision surface it describes. The immediate users are the
CI operator, Argus, and Algolia teams relying on a truthful current read.

## Success

- One run ID begins at the Hermes-triggered wrapper and reaches every public
  evidence contract and validation result.
- A complete immutable artifact generation is validated before one atomic
  pointer promotion.
- Final status is atomically written last and names the exact promoted or
  blocked run.
- Blocked diagnostics remain visible without changing the last successful
  decision generation.
- Freshness, run binding, hashes, source disposition, current extraction, and
  derived safety are machine-checked.
- Every planted stale, mismatched, spoofed, partial, self-attested, path-leak,
  and secret-leak case fails.

## Explicitly out of scope

Scout extraction completion, GA4/Looker connection, Argus recommendation
quality, Product Muscle IA implementation, and general production UI work.

## Systems and constraints

This slice touches the CI-OS app wrapper, publication module, public status and
manifest exporters, launch evidence checker, admin refresh publication helper,
tests, package contract, and later the CI static service unit. Hermes core,
firewall, Caddy routes, credentials, and database schema are unchanged.

## Scope classification

`FULL`. The work changes a public release boundary, safety validation, runtime
evidence contracts, and a production service account.

The approved goal charter authorizes autonomous progress through local safe
gates. It reserves credentials, new public/internal access decisions,
recommendation acceptance, destructive infrastructure, and release ownership
for explicit human input. None is needed for local Phase 2 implementation.
Production cutover remains a Development-Loop staging gate.
