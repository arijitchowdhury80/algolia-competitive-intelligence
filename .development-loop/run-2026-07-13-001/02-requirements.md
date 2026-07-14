# Requirements

1. Reject contradictory timeout configuration before execution where possible.
2. Bound the product-surface batch independently from single-item commands.
3. Terminate direct children and descendants on timeout or cancellation.
4. Write a structured result for every planned product-surface item, including
   completed, failed, empty, timed-out, and not-started work.
5. Preserve stage timestamps, elapsed time, error type, and bounded error text.
6. Keep runtime health distinct from evidence/readiness status.
7. Keep the public decision surface blocked when required evidence is absent.
8. Keep all changes inside the separately versioned CI-OS package.
9. Add regression tests before implementation and run the full suite.
10. Verify through two consecutive real Hermes cron executions as the deployed
    app user, with no root intervention or orphan processes.
