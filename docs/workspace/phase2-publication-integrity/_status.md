# Phase 2 Publication Integrity Status

Status: staging failed and rolled back; awaiting phase-order decision
Development-Loop run: `.development-loop/run-2026-07-14-002/`
Current step: Development-Loop Stage 12 failed gate

All eight local validation layers passed. Production remains unchanged. The
full product, risk, specification, architecture, validation evidence, staging
sequence, and rollback drill live in the Development-Loop run.

Draft PR #1 targets `ci-os-package-main`. Candidate `47d3bd7` failed live
staging and was rolled back without changing public bytes. One repaired Hermes
run produced a valid blocked diagnostic, but no decision pointer because the
GA4/manual demand source is not ready. The staging report contains the run IDs,
repairs, rollback evidence, and required phase-order decision.
