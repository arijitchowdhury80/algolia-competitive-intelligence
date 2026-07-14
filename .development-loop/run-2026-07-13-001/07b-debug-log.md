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
