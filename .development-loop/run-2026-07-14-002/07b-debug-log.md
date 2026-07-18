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

## GitHub package-contract failure

The first package CI run later failed after static checks and tests because
`verify_package.py` expected the deployment `.venv/bin/python`, while Actions
uses an editable checkout install in the runner Python. This was CI environment
configuration, not a package/runtime defect. A workflow contract test was
changed first and failed, then the CI-only verifier invocation added
`--skip-python-imports`. Importability remains independently covered by `pip
check`, Pyright, MyPy, and the full suite. GitHub run `29326371217` passed both
jobs after the fix.

## Stage 12 live failures

The first approved staging run (`ea34d298445944edb8ab3cae9022b81c`)
failed before publication. Secret-redacted evidence isolated two independent
deployment defects:

1. `cios-claude-shim.service` could not execute a mode-`0750` `uvicorn` from a
   virtualenv shared with the `cios` account. A dedicated `cios-shim`
   virtualenv restored least-privilege execution and returned a healthy live
   Claude probe.
2. `cios-runner.service` finalization returned `203/EXEC` because the release
   archive stored `deploy/cios-run-finalize.sh` as non-executable.

After those changes, the second Hermes request
`f9a040a200384c3799ce7fed233ecfd4` completed with runner and finalizer exit
code 0. Run `cios-20260714T135025Z-1989449` produced passing package and
publication verdicts, but correctly emitted only a blocked diagnostic because
the demand source gate had zero ready rows. No decision pointer was created.

Rollback then exposed a third latent defect: the installed localhost admin
could not import the src-layout package after restart because its systemd unit
omitted `PYTHONPATH=/opt/cios/app/src`. A localhost-only drop-in restored HTTP
200. TDD reproduced all three package-contract failures; the versioned admin
unit, executable archive mode, and preflight checks are being corrected.

## Phase-order blocker resolved

Arijit authorized read-only Looker Studio inspection and manual CSV export on
2026-07-14. The current seven-day page export contains a directly mappable,
nonzero `Agent Search` signal: `/products/ai-search` with 786 sessions from
2026-07-07 through 2026-07-13. Raw analytics remain private and untracked. A
prior landing-page pivot contains 751 sessions for the same path, but its chart
dimension differs from the current page export, so no change percentage will
be inferred from those two values.

This is a changed hypothesis for the next staging attempt: preserve the failed
candidate as evidence, validate and import the one-row real demand input, then
build a fresh immutable candidate from the post-tag package fixes and rerun the
complete Stage 12 matrix.

## Fresh-release output marker failure

Candidate `707fee5` passed GitHub CI, off-route package preflight, mounted
package preflight, and demand preparation with one ready row, one normalized
row, no skipped rows, and explicit partial coverage of the 12-topic live Argus
plan. The app mount was activated while the legacy public service retained its
exact root hash. A narrow bind exposed the existing Hermes-owned queue to the
versioned candidate without moving application execution under Hermes.

Real Hermes request `332b3a51ef0a4c8ca4eb032a28d0f5b8` crossed the queue
boundary but exited 2 before a CI-OS run ID was created:
`refusing to clean unmarked CIOS output directory: /opt/cios/app/out`.
The release initializer created an empty writable `out/` directory but did not
create the `.cios-output-dir` marker required by `cios-daily-app.sh` before any
cleanup. No decision pointer moved and the legacy public service remained
active with SHA-256
`280b721bb5276394abac2d4ea1547c1883d1b2b6e94a993a919d4b316dff5db7`.

The changed hypothesis is now package-enforced initialization: the host
permissions script creates the marker with `cios:hermes` ownership and mode
`0660`, and the package verifier rejects releases that omit that contract. The
new regression test failed before the fix, then the focused suite passed 87
tests. Full verification passed `1322 passed, 3 skipped, 23 deselected`, scoped
Ruff, Pyright, strict MyPy, and the package contract. Candidate `707fee5` is
retained as failed evidence and must not be mutated or retried.

## Public-artifact adapter failure

Candidate `1ea8c68` passed GitHub Actions run `29350795379`, off-route and
mounted package preflight, marker ownership, and demand preparation. Real
Hermes request `db7adb02342f46c8968e88d99de79188` ran as `hermes -> cios`
within the systemd runtime ceiling and completed source collection, model
generation, learning, product-surface export, demand import, dashboard render,
brief render, and data-plane manifest generation. Run
`cios-20260714T164836Z-2116876` recorded one audience-demand signal and a watch
decision, but publication validation failed before install or pointer movement.

The exact off-route validator reproduction reported
`unsafe artifact data/semantic-dashboard.json: local_path`. A key-path-only
audit found internal filesystem references in the internal semantic dashboard
and data-plane manifest, while HTML artifacts contained none. The internal
artifacts are legitimate runbook evidence; the defect was that
`publish_generation.py` copied them directly into the public generation instead
of creating a redacted public JSON view.

The changed hypothesis is a publication-boundary adapter: recursively remove
local-path JSON keys and values into temporary copies, preserve internal source
bytes, then keep the existing immutable scanner as the final rejecting gate for
HTML paths, credentials, secrets, malformed JSON, and symlinks. The regression
test failed before the fix and then the focused publication suite passed 25
tests. Full verification passed `1322 passed, 3 skipped, 23 deselected`, scoped
Ruff, Pyright, strict MyPy, and package preflight. Candidate `1ea8c68` remains
failed evidence and is ineligible for retry.

The run also proved why demand coverage must remain explicit: the current
product scan regenerated a different 12-topic Argus plan, so the truthful
`Agent Search` row remained a processed but unmapped signal instead of being
silently reassigned. The data-plane manifest reported one audience-demand
signal and blocked action on incomplete plan coverage. No synthetic topic or
week-over-week claim was introduced.
