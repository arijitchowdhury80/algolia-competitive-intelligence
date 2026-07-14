# Debug Log

## Failure

The real Hermes cron path returned code 2. The ownership handoff worked, all 43
active outward sources were fetched, then `product_surface_export` timed out.

## Reproduction and characterization

Category: process supervision and timeout configuration.

- Plan: 53 items.
- Workers: 3.
- Outer stage timeout: 240 seconds.
- Per-item executor timeout: 300 seconds.
- Stage elapsed: 240.104 seconds.
- Product export files continued changing after the parent failure timestamp.
- No related process remained by the later inspection.

## Trace

`deploy/cios-daily.sh` supplies three workers. `daily_production_run.py` applies
the generic 240-second command timeout to `execute_product_surface_plan.py`.
The executor allows each worker command 300 seconds. Both layers use
`subprocess.run` timeout behavior without a dedicated process group.

## Confirmed hypothesis

The parent timeout is guaranteed to be able to fire before one child timeout,
and it kills only the executor process. Worker descendants can continue until
they finish or hit their own timeout. Live timestamps confirm both effects.

## Resolution

The executor now starts every item in a new process group and registers it with
a reusable supervisor. Item expiry, batch expiry, and executor shutdown all
terminate the process group, wait through a bounded grace period, and escalate
to `SIGKILL` when required.

The executor owns a 600-second batch deadline and reports every planned item as
`succeeded`, `empty`, `failed`, `timed_out`, or `not_started`. The enclosing
daily stage has a separate 630-second ceiling, so it cannot preempt normal
executor cleanup. The overall daily ceiling is 1,200 seconds.

A regression process whose descendant ignored `SIGTERM` exposed a cleanup edge
case during TDD. The supervisor was corrected to test the process group after
the grace period and force-kill the surviving group. The final regression set
passes and no late marker is written.

## Remaining proof

Local reproduction is resolved. The fix is not a Phase 1 pass until the exact
reviewed commit completes two consecutive real Hermes cron executions without
permission errors, timeout, orphan work, or stale-public fallback.

## Corrected-Commit Review Debug Cycle

### Failure

Independent review of `46dc778` reproduced two remaining runtime failures:

- `_run_checked()` timed out its direct child while a grandchild continued and
  wrote a late marker;
- a missing product-surface executable raised `FileNotFoundError` out of the
  executor instead of producing a terminal item result.

The review also found that timeout stderr was discarded and generic daily
exception paths persisted or printed unredacted exception text.

### Characterization and trace

Category: process supervision, error-boundary consistency, and test harness.

`_run_checked()` still used `subprocess.run(timeout=...)`, unlike the product
executor's process-group path. Error formatting was distributed across daily
stage catch blocks. The product executor called `Popen` before entering any
exception-to-result boundary, and its timeout branch ignored returned output.

### Confirmed hypothesis

The direct-child timeout API was the source of the orphan. Centralizing daily
subprocess execution behind `Popen(start_new_session=True)` plus the existing
process-group registry would terminate descendants. Centralizing exception
formatting would prevent individual catch blocks from bypassing redaction.

### Resolution

- Added a supervised daily command helper that registers a new process group,
  terminates the group on timeout, captures bounded redacted diagnostics, and
  unregisters it on every path.
- Added a safe process entrypoint that redacts uncaught errors before service
  logs receive them.
- Routed explicit daily exception persistence and printing through centralized
  redaction helpers.
- Converted product-surface spawn failures into terminal failed results.
- Preserved redacted child diagnostics on item and batch timeouts.
- Extended deployment preflight to require daily process-group supervision.

The first affected-suite retry exposed eight tests that mocked
`subprocess.run` directly. Those tests were coupled to the old implementation,
so the supervised executor was placed behind an injectable module boundary and
the tests were moved to that boundary. No production behavior was weakened.

### Regression evidence

- Six exact review regressions: passed.
- Daily-run test module: 112 passed.
- Affected runtime/deploy set: 234 passed.
- Full suite: 1,221 passed, 1 skipped, 23 deselected.
- Late descendant marker: absent after the timeout grace window.

## Detached-Session Review Debug Cycle

### Failure

Independent review of `d5cc5d4` proved that a descendant calling `setsid()`
could leave the original process group and write a late marker after both the
daily and product-surface timeout handlers returned. The static package guard
also accepted the incomplete supervisor.

### Confirmed hypothesis

Process-group cleanup is sufficient only while descendants remain in the
group. Snapshotting the trusted command's descendant tree before termination,
then signaling detached descendant groups and PIDs as well as the root group,
closes the reproduced escape without changing Hermes or adding a dependency.

### Resolution

- The supervisor snapshots PID, parent PID, and process-group ID with a bounded
  `ps` call before root termination.
- Detached descendant groups and PIDs receive bounded TERM/KILL handling.
- Daily and product-surface regressions now launch a real `setsid()` child and
  prove no late marker is written.
- Deployed package preflight now runs the same behavior as a runtime self-test;
  an intentionally unsafe process-group-only supervisor is rejected.

### Regression evidence

- Five detached-session and preflight regressions: passed.
- Affected runtime/deployment set: 239 passed.
- Full suite: 1,226 passed, 1 skipped, 23 deselected.
- Package contract, Python compilation, shell syntax, and diff checks: passed.

### Concurrency reproduction and circuit breaker

The exact independent-review command later reproduced three failures after the
same tests had passed in smaller selections. Under load, the target parent can
create a detached child after the supervisor's one-time process-table snapshot
but before the root process group is terminated. The detached child is absent
from the snapshot and survives.

Evidence: 3 failed, 214 passed. Failures were the daily detached-child test,
the product-surface detached-child test, and the deployed runtime self-test.

This invalidates the snapshot architecture for the Phase 1 no-orphan contract.
The third rectification attempt reached the development-loop circuit breaker.
No deployment or push occurred. An explicit human architecture decision is
required before another implementation attempt.

## Approved Cgroup Architecture Reset

Arijit approved the hierarchical cgroup design on 2026-07-14. The reset
replaces process discovery with containment before target execution:

- systemd owns the whole-run cgroup and runs the application as `cios`;
- `Delegate=yes` exposes only the unit's private subtree to `cios`;
- a launcher enters each command cgroup before `execvp`;
- command timeout uses `cgroup.kill` and waits for `populated 0`;
- systemd enforces the outer runtime ceiling and finalizes interrupted queue
  state only after control-group cleanup;
- macOS keeps process-group fallback for local compatibility, while deployed
  preflight fails closed without delegated cgroup v2.

The affected selection passed 249 tests with two Linux-only integration skips.
The complete local suite passed 1,237 tests, with three skips and 23 deselected.
No deployment or push has occurred.

## Linux Staging Namespace Debug Cycle

### Failure 1: host-only queue path

The first real Hermes trigger after deployment exited before enqueue with
`CI-OS runner queue is unavailable`. The queue existed on the host at
`/opt/cios/app/run-queue`; inside the Hermes container the same inode is visible
at `/opt/data/apps/cios/run-queue`, and `/opt/cios/app` is absent.

The red regression simulated a container with only the Hermes namespace and
reproduced the exact failure. The wrapper now selects only between two fixed,
non-symlinked trusted roots. Package preflight requires the actual fallback
branch, not merely both path strings.

### Failure 2: private app virtual environment

The next real trigger selected the correct queue but Python failed before
enqueue with `PermissionError` on
`/opt/data/apps/cios/.venv/pyvenv.cfg`. This was expected least-privilege
behavior: `hermes` may traverse the shared package but may not read the private
`cios` virtual environment.

The red regression made the simulated CI-OS interpreter exit 91 and proved the
wrapper must use the fixed Hermes runtime interpreter for queue-client work.
Host application execution remains on the private CI-OS interpreter as `cios`.

### Verification

- Focused runtime/wrapper/package selection: 111 passed.
- Full suite: 1,251 passed, 3 skipped, 23 deselected.
- Package preflight, shell syntax, compilation, and diff checks: passed.
- Independent re-review after each correction: APPROVE, no findings.
- Two later real Hermes runs returned 0 and passed the Phase 1 live gate.
