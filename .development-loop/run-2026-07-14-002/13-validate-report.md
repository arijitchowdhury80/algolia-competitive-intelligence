# Validate Report

Timestamp: 2026-07-14T10:27:43Z
Verdict: PASS TO STAGING GATE

## 1. Static analysis: PASS

- `pyright --project pyright-phase2.json`: `0 errors, 0 warnings` for the new
  publication package and changed publication/readiness CLIs.
- `mypy --strict src/cios/publication`: success.
- Ruff over Phase 2 publication and readiness surfaces: pass.
- `python3 -m compileall -q src scripts`, shell syntax, and
  `git diff --check`: pass.
- Installed Pydantic and Psycopg signatures were inspected directly. Pydantic
  boundary calls match version 2.12.5; Psycopg's context-manager commit behavior
  explains and validates the integration-isolation fix.
- Code-validator result: PASS WITH WARN. The documented orchestration-length
  exceptions in `08-code-health-report.md` remain; there is no Critical or
  Important code-health finding.

The repository-wide Ruff baseline still contains 51 pre-existing findings in
legacy files. This slice did not broaden into unrelated cleanup; its focused
surfaces are clean and the full regression suite is green.

## 2. Unit tests and coverage: PASS

- Full default suite after adding the CI workflow contract: `1318 passed, 3
  skipped, 23 deselected in 34.55s`.
- Focused publication/launch tests after strict-type rectification: `42 passed`.
- Branch coverage across `cios.publication` and the two publication/readiness
  CLIs: 88% total, above the 80% SOP floor. Per-file coverage ranges from 81%
  to 100% for the publication package and 89% to 93% for the CLIs.

## 3. Integration: PASS

A temporary Postgres cluster bound only to `127.0.0.1:5433` applied the real
schema, seed, RLS role, repositories, and demand-to-dashboard path. Result:
`23 passed`. The cluster was stopped after the run and production data was
never contacted.

The run found and fixed a pre-existing session-scope isolation defect; see
`07b-debug-log.md`.

## 4. Contracts: PASS

Pydantic models enforce run IDs, tenants, publication kinds, artifact paths,
timestamps, safety, manifests, public status, and publication results. Tests
cover invalid identifiers, duplicate/traversing paths, missing/extra/empty and
tampered artifacts, stale or mismatched run state, package verdict structure,
and exact manifest digest binding.

Package preflight on this checkout passed and wrote a structured run-bound
verdict. Dashboard Playwright dependencies also passed their executable check.

The immutable release candidate is Git commit `47d3bd7` with tree
`ef09b04cfe9a0e4d5b3cf5f7008693a10b3a14eb`. Its extracted archive passed
package preflight; `/private/tmp/cios-47d3bd7.tar.gz` has SHA-256
`0e83a836fe75689e5ceac1f89fe02337458dc7e65f87e94031e452a6a7ee9298`.

GitHub Actions run `29326371217` independently passed `static-and-unit` and
`postgres-integration` on the draft package pull request. The subsequent
workflow-only commits do not alter the archived `47d3bd7` candidate.

## 5. End to end: PASS LOCALLY

A localhost static server read the stable `served/` router while Chromium and
direct HTTP checks exercised root and `/v2` dashboard, status, manifest, brief,
and competitor-brief routes. Every route returned HTTP 200; root and `/v2`
bytes matched; Chromium confirmed both pages were bound to the restored run.

The server remained running while publication advanced from immutable release
A to B and then restored A. Dashboard and latest status both returned to A.
The complete live dashboard click journey is intentionally deferred to Stage
12 after the approved cutover; no production UI behavior changed in this slice.

## 6. Performance: PASS FOR LOCAL BOUNDARY

One hundred sequential manifest reads through the local static service
completed with p50 0.318 ms, p95 0.448 ms, and max 0.836 ms. No database schema
or query path changed. The candidate systemd unit bounds the static process to
128 MB memory, 20% CPU, and 32 tasks.

No product traffic SLA was specified for this internal pilot, so these numbers
are validation evidence rather than a production capacity claim. Staging will
repeat load and process-limit checks on the VPS.

## 7. Security regression: PASS WITH RECORDED RESIDUAL

- Changed-file secret scan: 62 files, zero candidate secret files.
- The direct pinned dependency advisory scan recorded in `09-security-review.md`
  found no known vulnerabilities and no dependency changed afterward.
- Scanner and release-store planted defects remain green: local paths,
  configured secrets, credential-shaped JSON, symlinks, router tampering,
  concurrent publishers, stale verdicts, unsafe run IDs, and digest mismatch.
- Read-only VPS inspection confirmed the new `cios` account exists. The live
  legacy static process remains root-owned until the staging gate.

Residual: this package has version ranges but no reviewed lock file. That is a
packaging-phase requirement before general distribution, not a Phase 2 pilot
regression.

## 8. SOP compliance: PASS WITH WARN

Code-validator and test-validator checklists were applied against the fresh
Coding and Testing SOPs. TDD RED evidence is recorded in `07-build-log.md`;
unit, filesystem integration, real-Postgres integration, Pydantic contract,
Chromium route, rollback, performance, and security layers all ran.

Warnings:

- Established orchestrators retain documented function-length exceptions.
- The legacy repository test layout predates the newer three-directory SOP;
  tests remain separated by behavior and integration marker without an
  unrelated tree-wide move.
- Scenario enumeration lives in the approved requirements and plan rather than
  duplicated comment blocks in every test file.

## Validation risk surface

| Layer | Proves | Does not prove |
|---|---|---|
| Static | Changed publication code is typed, linted, importable, and syntactically valid | VPS runtime permissions and service manager behavior |
| Unit/coverage | Pure contracts, scanning, validation, verdicts, and fault paths | Real database or HTTP behavior |
| Integration | Real Postgres schema/RLS/repos and real filesystem promotion | Production data quality or VPS service cutover |
| Contract | Public artifacts and verdicts match the approved schemas | Business evidence completeness |
| Browser/HTTP | Root and `/v2` resolve one run through the stable router | Full live dashboard click behavior |
| Performance | Local static serving is bounded and fast for 100 reads | Production peak capacity |
| Security | Known Phase 2 threats and planted defects remain mitigated | Unknown transitive CVEs without a lock file |

Remaining risk is deliberately owned by Stage 12: install the immutable
`47d3bd7` package, run as `cios`, seed the sibling store with one real Hermes run, verify
the live route and clicks, execute the planted-defect matrix, and prove service
rollback on the VPS.

## Gate

All eight local validation layers pass. Development-Loop auto-advances to
STAGING and waits for the mandatory human approval before changing the live
service or route.
