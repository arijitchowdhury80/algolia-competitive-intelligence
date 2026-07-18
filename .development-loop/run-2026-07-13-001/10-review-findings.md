# Code Review Findings

Reviewer: independent `gsd-code-reviewer`

Base: `12b97ae6c6fb121a308e9755e7076b6291a04302`

Reviewed commit: `8b0e800eb5d3e6914f10953c96d654aebc2263b7`

## Critical

None.

## Important

1. Per-item command expiry was emitted as generic `failed`, so the structured
   `timed_out` count represented only batch-deadline cancellation.
2. Stage timeout validation required only `stage > batch`; a tight override
   could preempt process-group cleanup and terminal summary writing.

## Minor

1. The new timeout and not-started fields were present in the daily run summary
   but omitted from the data-plane manifest and public run status.

## Disposition

All findings are technically applicable to the Phase 1 runtime and
observability contracts. They were accepted for test-first rectification.

## Corrected-Commit Review

Reviewed commit: `46dc7781469bbb4f5fe8e4c67869f816293c7aa9`

Verdict: CHANGES REQUIRED.

### Critical

1. The generic daily subprocess helper used direct-child timeout semantics and
   left a reproduced grandchild alive after timeout.
2. Generic daily stage ledgers, run error arrays, and output paths still had
   raw exception formatting outside the product-market-specific redaction.

### Important

1. Product-surface executable spawn failures escaped the executor and aborted
   complete terminal accounting.
2. Item timeout paths discarded captured stdout/stderr instead of preserving
   bounded redacted diagnostic evidence.

### Minor

1. Deployment preflight did not require process-group supervision in the
   generic daily subprocess path.

### Disposition

All findings were reproduced or confirmed against the code. They are within
the Phase 1 process-safety contract and were accepted for immediate TDD
rectification. No deployment was attempted.

## Detached-Session Re-review

Reviewed commit: `d5cc5d49a613a26c805383ea7c0c26f7ed548aa8`

Verdict: CHANGES REQUIRED.

### Critical

1. Both timeout paths killed only the original process group. A descendant that
   created a new session survived cleanup and wrote a reproduced late marker.

### Important

1. Package preflight's source-text guard passed despite the detached-session
   escape and therefore did not prove deployed cleanup behavior.

### Disposition

Both findings violate the Phase 1 no-orphan-work gate. They were reproduced,
accepted for a second bounded rectification cycle, and resolved with real
process regressions plus a dynamic deployed-package probe. No deployment was
attempted.

## Final Review Of `b8ee261`

Verdict: CHANGES REQUIRED.

### Critical

1. A one-time descendant snapshot races with descendants created immediately
   before root-group termination. The reviewer reproduced late writes in both
   execution paths; the exact command reproduced the same three failures in
   the primary session.
2. Whole-daily-run timeout still relies on shell PID-tree cleanup. The daily
   entrypoint does not install the shared shutdown handlers, and an already
   detached/reparented descendant can evade `pgrep -P` traversal.

### Disposition

Commit `b8ee261` is not deployable. The same design has exhausted the bounded
rectification allowance. Phase 1 is paused at an architecture decision between
kernel-enforced cgroup containment and explicitly weakening the no-orphan gate.
