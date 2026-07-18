# Build Plan

1. Add failing unit tests for run-ID generation/validation and propagation from
   the wrapper into the daily runner, manifest, status, and validation output.
2. Add failing publication tests for immutable run directories, canonical
   manifests, stable root and `/v2` routes, successful pointer promotion,
   blocked diagnostic promotion, status-last ordering, and fault rollback.
3. Add planted-defect tests for missing, extra, empty, symlinked, stale,
   mismatched, tampered, path-leaking, secret-leaking, and self-attested-safe
   artifacts.
4. Add readiness tests proving arbitrary PASS strings have no authority,
   structured verdicts must be fresh and run-bound, unchecked sources require
   dispositions, and historical product counts cannot satisfy current-run
   extraction completeness.
5. Implement a focused `cios.publication` module for allowlisted staging,
   manifesting, scanning, validation, immutable generation install, pointer
   promotion, and status-last replacement.
6. Replace shell and admin-refresh copy sequences with thin calls to the shared
   module behind `CIOS_PUBLICATION_V2`.
7. Propagate the wrapper run ID through existing structured artifacts with the
   smallest compatible schema additions; preserve existing consumers.
8. Add structured JSON outputs to package, click, publication, and launch
   checks; migrate launch readiness away from log substring and caller safety
   booleans.
9. Run focused tests after each red-green slice, then shell syntax, compile,
   package contract, all publication/readiness tests, and the full suite.
10. Perform code-health, security, and independent code review; rectify every
    important finding and rerun the complete validation stack.
11. Build an immutable release and rehearse both the publication-store rollback
    and static-service rollback without changing the live route.
12. At the staging gate, seed the sibling store, run the static service as
    `cios`, cut its document root to `cios-public/served`, trigger one real
    Hermes run, inject the documented defect matrix, verify public hashes and
    access, and prove rollback.

Branch: `codex/ci-os-phase1-runtime` in the existing isolated worktree. The
branch name is retained because it contains the reviewed Phase 1 release base;
Phase 2 will be separately versioned by commit and immutable package archive.

Gate basis: the goal charter pre-authorizes local implementation and review.
Production cutover remains blocked until Development-Loop staging evidence is
shown and approved.
