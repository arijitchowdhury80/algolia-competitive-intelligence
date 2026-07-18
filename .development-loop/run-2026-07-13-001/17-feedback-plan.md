# Phase 1 Feedback Plan

Window: first 48-72 hours after the 2026-07-14 gate
Owner: CI-OS operator / Argus, supervised through Hermes

## Monitoring

| Check | Cadence | Rollback or reopen trigger |
|---|---|---|
| `cios-v2-daily` terminal result | Every scheduled run | Nonzero result or missing result |
| Runtime identity and root-owned count | Every scheduled run | Any app workload not owned by `cios`; any root-owned runtime/public artifact |
| Runner and shim cleanup | After every run | Remaining job process, populated runner cgroup, or `active-run` after terminal state |
| Permission/traceback indicators | After every run | Any permission denial or uncaught traceback |
| Runtime duration | Every run | Approaches or reaches the 25-minute ceiling |
| Public latest-run status freshness | Every run | Status timestamp does not advance or misrepresents retained dashboard as current |
| Queue health | Daily | Pending request starvation, invalid result, or unexpected stale `.running` growth |

## Iteration Inputs

Record the next natural 09:00 ET run result, runtime, source coverage, public
status, cleanup state, and any operator intervention in `17b-iteration-input.md`
after the observation window. Reopen Phase 1 immediately on any trigger above;
otherwise route publication issues to Phase 2.
