# Internal Code Review Findings

Review mode: inline pre-PR review. The `gsd-code-reviewer` dispatch could not be
created because the active agent-thread limit was exhausted. The review traced
the approved requirements through wrapper, daily runner, dashboard state,
public exporter, publication module, admin refresh, static service, package
preflight, and launch gate.

## Critical

None.

## Important

1. **Private runtime provenance is incomplete.** The completion plan requires
   the exact package version and model route in private run metadata. The
   current ledger records tenant and product-market ledger ID but neither
   value. Publication hashes prove artifact identity, but an operator cannot
   reconstruct which release/model produced the run from the private ledger.
   Rectify by requiring a package release identifier when publication v2 is
   enabled and persisting package version, model provider, and effective model
   route in the run-stage ledger only.

## Important findings closed during Build

1. Publication was atomic per file but not serialized across wrapper/admin
   processes. Closed with an exclusive store lock.
2. Existing wrong router links and symlinked internal buckets were accepted.
   Closed with exact target and real-directory validation.
3. Launch readiness did not consume publication integrity or bind to served
   manifest bytes. Closed with a fresh structured verdict and digest equality.
4. Scanner coverage omitted common local path forms and nested credential
   containers. Closed with planted-defect tests and expanded rules.
5. Source dispositions were not uniquely accountable. Closed with stable
   non-secret source references and uniqueness validation.
6. Expected validation failures logged noisy tracebacks and internal stage
   paths. Closed with bounded validation warnings.

## Minor

- The launch evaluator is intentionally verbose and linear. Keep the explicit
  checklist until another gate family creates real duplication.
- The legacy mutable publisher remains behind the default-off v2 flag as the
  Phase 2 rollback path. Remove it only after staging and phase acceptance.

## Assessment

NEEDS ONE RECTIFICATION. No merge or staging until private runtime provenance
is tested and the full suite is rerun.
