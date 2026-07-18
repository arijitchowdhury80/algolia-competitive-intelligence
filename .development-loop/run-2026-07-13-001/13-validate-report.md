# Validation Report

Date: 2026-07-14
Scope: Phase 1 Hermes-owned execution recovery through `1fa7ac5`
Verdict: PASS

## Layer Results

| Layer | Result | Evidence |
|---|---|---|
| 1. Static analysis | PASS | Shell syntax, Python compilation, package preflight, and `git diff --check` passed. The current Coding SOP was read from its relocated Second-Brain path. No external library API signature changed. |
| 2. Unit tests | PASS | Full suite: 1,251 passed, 3 skipped, 23 deselected. Focused runtime, wrapper, queue, and package suite: 111 passed. |
| 3. Integration | PASS | Linux delegated-cgroup preflight passed as `cios`; two real Hermes cron runs passed against the live queue, database, model shim, output, and public-status paths. |
| 4. Contract | PASS | CI-OS Hermes package contract passed locally and on Linux. The public wrapper contract requires fixed host and Hermes namespaces plus branch-local trusted interpreters. |
| 5. E2E | PASS | Hermes cron job `107e64d347d9` triggered requests `a70f4e219d294280a26703962c9be4e9` and `1b938c9de92f4568a059bdb84d3f9e6b`; both returned 0. No browser layer was in Phase 1 scope. |
| 6. Performance | PASS | Runs completed in 14m 06s and 8m 39s, below the 25-minute systemd runtime ceiling. |
| 7. Security regression | PASS | Independent review returned APPROVE with no findings after each live-debug correction. No secrets printed; no permission errors, root ownership drift, orphan work, or public-path leakage observed. |
| 8. SOP compliance | PASS with warnings | Both live defects followed red-green TDD. Tests cover fixed-path selection, private-vs-Hermes interpreter behavior, queue security, timeout, and package contract. Existing repository test layout predates the current three-directory Testing SOP, and the two pushed fix commit subjects are sentence-case rather than conventional prefixes; history was preserved because those exact commits map to the deployed release. |

## Code Validator Result

- Regression surface: PASS; full suite has no failures.
- Error boundary: PASS; the wrapper fails closed for unavailable roots, queue,
  interpreter, helper, and invalid results.
- Security: PASS; paths are fixed, caller overrides remain forbidden, and queue
  execution uses a sanitized environment.
- Duplication/naming/comments: PASS for the small shell boundary.
- Git convention: WARN; preserve deployed commit identity rather than rewrite
  published history.

## Test Validator Result

- TDD discipline: PASS; both production failures were first reproduced by red
  tests, then corrected.
- Unit/contract/integration/E2E layers: PASS for the Phase 1 risk surface.
- Failure coverage: PASS for namespace absence, unreadable app venv, symlinks,
  caller overrides, timeouts, detached descendants, and finalizer behavior.
- Structure and coverage metric: WARN; tests follow the repository's existing
  layout and no new branch-coverage percentage was collected.

## Remaining Risk

Phase 1 does not prove atomic, fresh, run-bound publication. The latest run is
correctly blocked on missing demand evidence and publishes a fresh diagnostic
without replacing the last decision surface. Publication integrity is Phase 2.
