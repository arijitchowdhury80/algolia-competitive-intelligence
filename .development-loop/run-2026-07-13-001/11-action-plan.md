# Review Action Plan

1. Add a regression proving per-item expiry increments `timed_out` and emits a
   `timed_out` terminal result while still killing the full process group.
2. Add a regression rejecting stage budgets with less than 30 seconds of
   executor cleanup and summary-write margin.
3. Add manifest and public-status regressions for `timed_out`, `not_started`,
   `batch_timed_out`, and `batch_timeout_seconds`.
4. Implement only the status correction, explicit margin validation, and
   serializer propagation needed to satisfy those tests.
5. Rerun the affected set, package checks, shell/compile checks, and full suite.

The actions preserve the approved architecture, introduce no new dependency or
schema, and stay inside the autonomous Phase 1 recovery scope.

## Corrected-Commit Review Actions

1. Reproduce the daily timeout orphan with a descendant that ignores SIGTERM
   and writes a late marker.
2. Replace the generic direct-child timeout with registered process-group
   supervision and add a package-contract guard.
3. Centralize daily exception redaction for persisted, printed, and uncaught
   process-boundary errors.
4. Convert product-surface spawn failures to terminal failed results and retain
   redacted timeout diagnostics.
5. Decouple chain tests from `subprocess.run` by mocking the application
   supervision boundary.
6. Run exact regressions, affected tests, package/syntax/compile checks, the
   full suite, then security and code re-review before deployment.

## Detached-Session Review Actions

1. Reproduce the escape in both execution paths with a descendant that calls
   `setsid()`, ignores TERM, and writes a delayed marker.
2. Extend the shared supervisor to snapshot and terminate detached descendants
   within the same bounded cleanup window.
3. Add a deployed-package runtime self-test that rejects a process-group-only
   implementation, while retaining the fast static source contract.
4. Rerun exact regressions, affected tests, package/syntax/compile checks, and
   the full suite.
5. Require converged security and code-review approval before deployment.
