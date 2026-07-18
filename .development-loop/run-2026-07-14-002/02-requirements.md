# Requirements

1. Generate one validated run ID at the app-wrapper boundary and propagate it
   through the daily runner, stage ledger, source coverage, product-market
   summary, demand artifacts, manifest, dashboard, briefs, public status, and
   validation outputs.
2. Build each public generation under an immutable versioned run directory.
3. Produce a canonical manifest with run ID, relative path, media type, byte
   size, and SHA-256 for every published artifact.
4. Reject missing, extra, empty, symlinked, non-regular, hash-mismatched, or
   run-mismatched artifacts before promotion.
5. Recursively scan final HTML, JSON, CSV, and brief artifacts for local paths,
   file URLs, credential-shaped fields, and configured secret values without
   logging any secret value.
6. Promote a successful decision generation with one atomic pointer swap and
   atomically write final status last.
7. Publish a blocked run as an immutable diagnostic generation plus final
   status while leaving the successful decision pointer unchanged.
8. Replace PASS-substring and self-attested safety checks with structured JSON
   verdicts, explicit exit codes, freshness windows, and matching run IDs.
9. Fail readiness when any active source lacks a current-run checked outcome or
   an explicit bounded disposition reason.
10. Fail product readiness when current-run extraction completeness is absent,
    even if historical event counts are nonzero.
11. Preserve root and `/v2` route compatibility without duplicate mutable
    copies that can disagree.
12. Keep all runtime writes owned by `cios`; run the static CI server as `cios`
    after the gated cutover.
13. Preserve the existing mutable public directory and service definition as a
    tested rollback target until Phase 2 is accepted.
14. Add regression tests before implementation, run focused and full suites,
    and verify one real Hermes run plus planted-defect tests before passing the
    phase gate.
