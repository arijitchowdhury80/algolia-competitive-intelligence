# Intake

## Problem and users

CI-OS cannot be trusted as an operating system while a normal Hermes run can
be killed by contradictory timeout budgets or leave work running after the
stage has failed. The immediate users are the CI operator, Argus, and the
business teams that depend on a fresh scheduled run.

## Success

- The runtime and every child process have coherent, bounded time budgets.
- A timeout terminates the entire child process group and records diagnostics.
- A missing future evidence plane remains visible as product blockage without
  falsely reporting an infrastructure crash.
- Two consecutive real Hermes cron executions finish without permission
  errors, timeout, orphan work, or stale-public fallback.

## Explicitly out of scope

Phase 2 atomic publication, Phase 3 Scout completeness, Phase 4 GA4/Looker,
Phase 5 Argus recommendation work, and Phase 6 production UI.

## Systems and constraints

This slice touches CI-OS scripts, the CI-OS Hermes wrapper, host-runner service,
Postgres-backed execution, Scout child processes, and deployment packaging.
Hermes core is off limits. Secrets must not enter source or logs.

## Scope classification

`FULL`. The slice changes production process supervision, scheduled-execution
semantics, and failure reporting across external process boundaries.

The approved goal charter authorizes autonomous progress through this safe
gate and reserves explicit human decisions for credentials, public exposure,
recommendation acceptance, release ownership, and destructive infrastructure.
