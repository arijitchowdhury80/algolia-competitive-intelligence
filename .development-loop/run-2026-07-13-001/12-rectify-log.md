# Rectification Log

## Red

Four focused regressions failed against reviewed commit `8b0e800`:

- item expiry did not increment `timed_out`;
- a 600.1-second stage budget was accepted over a 600-second batch budget;
- the manifest dropped four execution-budget fields;
- public run status dropped the same four fields.

## Green

- Per-item expiry now returns terminal status `timed_out`.
- Stage timeout must be at least 30 seconds longer than the batch timeout.
- The data-plane manifest and public run status preserve timeout, not-started,
  batch-expiry, and batch-budget fields.

## Verification

- Four review regressions: 4 passed.
- Affected test set: 218 passed.
- Full suite: 1,205 passed, 1 skipped, 23 deselected in 35.11 seconds.
- Package preflight: passed.
- Shell syntax: passed.
- Python compile check: passed.
- `git diff --check`: passed.

No live deployment has occurred. Security review and corrected-commit review
remain ahead of the Phase 1 staging gate.

## Security Rectification

### Red

Focused regressions proved that child stderr could preserve a configured API
key, stage exceptions could publish the same value, worker counts above the
intended operational bound were accepted, and package preflight did not reject
those regressions.

### Green

- Added a shared environment-derived diagnostic redactor.
- Redacted nonzero child stderr/stdout and product-market stage exceptions
  before they enter exceptions, summaries, stdout, or stage ledgers.
- Enforced a hard product-surface worker range of 1 through 8 in both direct and
  environment-driven entry points.
- Extended package preflight to require the redaction module, redaction calls,
  and worker hard cap.

### Verification

- Security regression selection: 6 passed.
- Package-contract tests: 68 passed after four expected RED failures.
- Affected test set: 228 passed.
- Full suite JUnit: 1,216 tests, 0 failures, 0 errors, 1 skipped.
- Independent security re-review: GO; no Critical, High, or Medium findings.
- Live read-only service check: CI-OS application services and runtime paths use
  the dedicated `cios` account and `cios:hermes` ownership.

Corrected-commit code review remains ahead of deployment. Phase 1 still requires
two consecutive real Hermes-triggered runs before its gate can pass.

## Corrected-Commit Review Rectification

### Red

Six regressions failed against `46dc778`: daily process-tree timeout cleanup,
safe uncaught errors, generic ledger redaction, missing executable accounting,
timeout diagnostic retention, and the corresponding package-preflight guard.

### Green

- Daily child commands now use registered process groups and bounded group
  termination.
- All explicit daily exception persistence/printing uses centralized redaction;
  the process entrypoint catches and sanitizes any remaining uncaught error.
- Product-surface spawn failures produce failed terminal results.
- Timeout results include bounded redacted child diagnostics.
- Package preflight requires daily process-group supervision.

### Verification

- Six exact review regressions: 6 passed.
- Daily-run module: 112 passed.
- Affected test set: 234 passed.
- Full suite: 1,221 passed, 1 skipped, 23 deselected in 35.08 seconds.
- Package preflight: passed.
- Shell syntax, Python compilation, and `git diff --check`: passed.

Final security and code re-review remain mandatory before deployment.

### Review-three failure

The final code review ran a wider focused selection and reproduced a timing
race that the exact and full-suite runs had not consistently exposed. Repeating
the reviewer's command in the primary session produced 3 failed and 214 passed:
both detached-descendant late-marker tests and the runtime preflight probe
failed.

The process-table snapshot cannot provide atomic containment because a target
may fork and detach after discovery. This rectification is therefore rejected,
`b8ee261` must not be deployed, and the development-loop three-strike circuit
breaker is active pending a human architecture decision.

## Approved Cgroup Reset Rectification

### Red

- Four process-containment tests failed to collect because the cgroup backend
  and launcher did not exist.
- Five run-boundary tests failed on the old oneshot service, PID watchdog,
  multi-request activation, and missing finalizer.

### Green

- Added delegated cgroup v2 discovery, launch-before-exec handshake, atomic
  `cgroup.kill`, empty-group verification, and fail-closed deployment mode.
- Routed both daily and product-surface commands through the shared contained
  spawn boundary.
- Replaced the shell PID watchdog with a systemd runtime ceiling and full-unit
  `KillMode=control-group`.
- Added active-request-scoped post-stop finalization and blocked timeout status.
- Extended deployed preflight with service, launcher, finalizer, delegation,
  and continuous fork-at-timeout runtime checks.

### Verification

- Affected runtime/deploy/preflight selection: 249 passed, 2 skipped.
- Full suite: 1,237 passed, 3 skipped, 23 deselected in 36.18 seconds.
- Package preflight with source checks: passed.
- Python compilation, shell syntax, and `git diff --check`: passed.

Independent security and code review remain mandatory before deployment.

## Detached-Session Rectification

### Red

Three initial regressions failed against `d5cc5d4`: daily and product-surface
detached descendants wrote late markers, and package preflight accepted a
supervisor without descendant discovery. Two additional preflight tests were
red because the dynamic runtime probe did not yet exist.

### Green

- Shared supervision now snapshots the descendant tree before termination and
  signals detached groups/PIDs alongside the root process group.
- Both execution paths kill a real detached, TERM-resistant descendant before
  it can write after timeout.
- Full package preflight executes a bounded detached-descendant cleanup probe.
- The probe accepts the current implementation and rejects an intentionally
  unsafe process-group-only supervisor.

### Verification

- Five exact regressions: 5 passed.
- Affected test set: 239 passed in 32.00 seconds.
- Full suite: 1,226 passed, 1 skipped, 23 deselected in 40.18 seconds.
- Package preflight: passed.
- Shell syntax, Python compilation, and `git diff --check`: passed.

Final security and code re-review remain mandatory before deployment.
