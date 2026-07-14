# Build Plan

1. Add failing tests proving a timed-out export cannot leave a descendant and
   that every planned item receives a terminal result.
2. Add failing tests proving the daily chain passes a coherent dedicated batch
   timeout rather than the generic 240-second command timeout.
3. Add a wrapper regression test for runtime success with truthful blocked
   demand readiness.
4. Implement the smallest process-group and timeout-budget changes that pass.
5. Run focused tests, shell syntax, package contract, and the full suite.
6. Review security and operational failure paths.
7. Deploy the exact reviewed bundle with rollback backup.
8. Trigger two consecutive runs through Hermes cron and verify users, exit
   codes, source disposition, process cleanup, package identity, and artifacts.

Branch: `codex/ci-os-phase1-runtime` in an isolated worktree. This avoids the
separate active dashboard worktree and preserves its changes.
