# Security Review

## Scope

Phase 1 runtime supervision, subprocess diagnostics, concurrency bounds,
deployment preflight, and the dedicated CI-OS service-user boundary.

## Verdict

GO. Independent corrected-worktree review found no Critical, High, or Medium
findings. The two prior Medium findings are closed.

## Closed Findings

1. Subprocess diagnostic leakage: closed. Sensitive environment-derived values
   are redacted before child stderr/stdout or stage errors enter exceptions,
   summaries, stdout, or stage ledgers.
2. Unbounded product-surface workers: closed. The runtime and environment
   parser both enforce a hard range of 1 through 8 workers; deployment
   preflight rejects packages missing that cap.

## STRIDE Validation

| Threat | Result | Evidence |
|---|---|---|
| Spoofing | PASS | Hermes remains the scheduler; systemd executes CI-OS as `cios`, while the localhost model shim runs as `cios-shim`. |
| Tampering | PASS | Package preflight requires supervision, redaction, worker-cap, service-user, and ownership invariants before the daily wrapper proceeds. |
| Repudiation | PASS | Per-stage events and terminal execution summaries preserve failures, timeouts, and not-started work without dropping diagnostic state. |
| Information disclosure | PASS | Sensitive environment values are removed from the changed subprocess and stage-error paths; tests prove raw test secrets do not survive. |
| Denial of service | PASS | Per-item, batch, stage, and daily deadlines are bounded; worker concurrency is capped at eight. |
| Elevation of privilege | PASS | CI-OS services run as dedicated non-login accounts with `NoNewPrivileges`; runtime trees are `cios:hermes`, not admin- or root-owned. |

## Residual Low Risks

- Redaction is exact-value based and cannot identify transformed, partial, or
  incorrectly named secrets.
- Older daily-ledger exception paths outside this Phase 1 subprocess surface
  still use bounded raw exception strings. The changed subprocess paths redact
  before reaching them; a broader error-envelope redesign belongs in a later
  security-hardening slice.
- Product-surface plan command vectors remain trusted package-local input. They
  are executed without a shell, but Phase 1 does not introduce a command
  allowlist or output-root policy redesign.

## Verification

- Independent security re-review: GO; 0 Critical, 0 High, 0 Medium.
- Security reviewer focused tests: 188 passed.
- Main-agent affected tests: 228 passed.
- Full suite JUnit evidence: 1,216 tests, 0 failures, 0 errors, 1 skipped.
- Package preflight without deployed imports: passed.
- Python compilation, shell syntax, and `git diff --check`: passed.
- Live read-only ownership check: `cios-admin` and runner configured as `cios`;
  app, queue, output, temp, and env paths owned by `cios:hermes`.

The goal charter authorizes autonomous continuation when no explicit human
decision boundary remains. Security may advance to corrected-commit review;
live deployment and two Hermes-triggered runs are still required for Phase 1.
