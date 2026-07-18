# Best-Practices Synthesis

## Patterns that worked

- Process timeouts are lifecycle contracts: create a process group, register
  it, terminate the group, reap it, and preserve a terminal result.
- Timeout layers need explicit ordering and cleanup margin: item before batch,
  batch before stage, stage before daily.
- Every planned item needs one terminal state, including spawn failures and
  work that never starts.
- Error redaction belongs at shared process and exception boundaries, not in a
  handful of downstream log statements.
- Deployment preflight should encode safety behavior, not merely file presence.

## Anti-patterns found

- `subprocess.run(timeout=...)` was treated as process-tree supervision.
- Tests mocked a standard-library implementation detail instead of the
  application command-execution boundary.
- Error strings were formatted independently in many catch blocks.
- A passing full suite was treated as stronger evidence than a targeted
  adversarial process-tree reproduction.

## Test gaps closed

- Grandchild ignores `SIGTERM` and attempts a late write after daily timeout.
- Missing executable becomes a terminal failed item.
- Timeout stderr survives in redacted form.
- Generic ledger and process-boundary errors do not expose configured secrets.
- Package preflight rejects a daily runtime without process-group supervision.

## Follow-through

Future subprocess entry points should reuse the supervised boundary. A broader
structured error-envelope refactor may replace text invariants later, but it is
not required to prove the Phase 1 execution gate.
