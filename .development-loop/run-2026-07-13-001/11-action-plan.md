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
