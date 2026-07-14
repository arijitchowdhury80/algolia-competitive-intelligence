# Validate Debug Log

## Failure

The real-Postgres integration run reproduced two order-dependent failures in
`tests/integration/test_demand_to_dashboard_flow.py`: the first test observed
two demand signals instead of one and the second hit the competitor uniqueness
constraint.

## Reproduction and classification

- Minimal reproduction: run both demand-flow integration tests against a fresh
  loopback Postgres database.
- Deterministic result before the fix: `2 failed`.
- Category: test infrastructure and shared database state, not production
  product logic.

## Trace and hypothesis

`_schema_applied` reset the schema once per session. Function-scoped
`app_conn` fixtures used `with psycopg.connect(...)`, whose installed
`Connection.__exit__` implementation commits on a successful exit. Rows from
one test therefore became the next test's starting state.

Hypothesis: resetting the guarded test schema per test preserves deliberate
within-test commits while preventing cross-test leakage.

## Fix and regression evidence

Changed `_schema_applied` from session to function scope. This is preferable to
wrapping each connection in an outer transaction because several RLS tests
intentionally commit through one connection and verify through another.

- Exact prior failures: `2 passed in 0.68s`.
- Full real-Postgres integration suite: `23 passed, 1319 deselected in 5.14s`.
- Full non-integration suite: `1316 passed, 3 skipped, 23 deselected in 35.04s`.

No Debug strike was recorded: the first root-cause hypothesis was confirmed by
the installed Psycopg source and the focused regression run.
