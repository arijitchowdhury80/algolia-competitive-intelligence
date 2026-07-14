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
