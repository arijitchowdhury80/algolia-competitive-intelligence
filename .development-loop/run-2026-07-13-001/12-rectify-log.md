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
