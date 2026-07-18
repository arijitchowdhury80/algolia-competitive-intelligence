# Architecture Review

## Important findings

1. A generic 240-second timeout encloses a batch whose individual children are
   each allowed 300 seconds. The budgets are structurally inconsistent.
2. `subprocess.run(..., timeout=...)` kills the direct child, not an arbitrary
   descendant tree. Live files proved descendants outlived the failed stage.
3. Increasing the generic timeout alone would hide the process-supervision bug
   and still provide no complete terminal summary on cancellation.
4. Treating missing GA4 as a runtime crash couples a Phase 4 business-readiness
   gate to the Phase 1 infrastructure-health gate.

## Decision

Use explicit process-group supervision and a dedicated bounded batch deadline.
Keep evidence readiness blocked in data/status artifacts, while reserving
nonzero runtime exit for execution or artifact-integrity failure.

Verdict: acceptable to build under the approved Phase 1 boundary.
