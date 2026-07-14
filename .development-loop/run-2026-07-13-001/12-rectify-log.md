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
