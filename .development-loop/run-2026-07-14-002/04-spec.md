# Publication Integrity Spec

## Builder

`module-builder`, because the core is a backend publication and verification
module with shell adapters and no new frontend surface.

## Run identity contract

The app wrapper generates `CIOS_RUN_ID` once using UTC time and process-unique
entropy, validates it against a conservative ASCII identifier grammar, and
exports it before preflight or pipeline work. `daily_production_run.py` uses
that value instead of creating a second identity. Every structured artifact
that represents run state carries `run_id`; rendered HTML/CSV/brief files are
bound to the run by the signed-by-hash publication manifest.

## Release-store contract

Use a sibling store that is not reachable from the current static root during
staging:

```text
cios-public/
  releases/<run_id>/
  diagnostics/<run_id>/
  current -> releases/<run_id>
  latest-diagnostics -> diagnostics/<run_id>
  latest-status.json
  served/
```

`served/` contains stable relative symlinks for the existing root and `/v2`
routes. Decision artifacts resolve through `current`; the two latest-status
URLs resolve to the single `latest-status.json` inode. Diagnostic helpers may
resolve through `latest-diagnostics`. The static service continues to expose
the same URLs but uses `cios-public/served` as its document root.

## Generation and manifest contract

The publisher copies only allowlisted artifacts into a temporary directory on
the release-store filesystem, rejecting symlinks and unsafe relative paths. It
then writes `publication-manifest.json` with schema version, run ID, tenant,
kind (`decision` or `diagnostic`), generated time, and sorted file records with
path, content type, bytes, and SHA-256.

Validation re-enumerates the final tree independently. Required and optional
sets are explicit. Extra, missing, empty, non-regular, symlinked, duplicate,
hash-mismatched, stale, or run-mismatched content fails closed.

## Safety contract

Safety is derived from bytes in the complete staged generation. Scannable
formats are HTML, JSON, CSV, and text briefs. Findings contain only rule ID,
relative path, and structural location where safe; they never include matched
secret values. Public status safety fields are computed from the scanner
verdict and cannot be supplied by the caller.

## Promotion contract

For a successful decision run:

1. Build and validate an immutable release directory.
2. Atomically replace the `current` symlink.
3. Atomically replace `latest-status.json` last.

For a blocked run:

1. Build and validate an immutable diagnostic directory.
2. Atomically replace `latest-diagnostics` only.
3. Leave `current` unchanged.
4. Atomically replace `latest-status.json` last.

Any failure before the final status replace leaves the prior status and prior
decision pointer intact. Existing immutable generations are never overwritten.

## Structured readiness contract

Package, publication, click, and launch checks use JSON verdicts with
`schema_version`, `gate`, `run_id`, `generated_at`, `status`, `exit_code`, and
named checks. The launch evaluator rejects stale verdicts, differing run IDs,
nonzero embedded exit codes, missing required checks, and mismatched artifact
digests. Literal PASS text has no authority.

Publication integrity and product launch readiness are separate verdicts. A
fresh blocked run may pass publication integrity while launch readiness remains
failed on missing product or demand evidence.

## Source and product readiness

Source coverage must include current-run totals for active, checked, failed,
and explicitly disposed sources. Every active source must be checked or carry
a nonempty bounded disposition reason. Product readiness requires the same run
ID plus planned, attempted, terminal, successful, failed, timed-out, and
not-started extraction counts whose arithmetic proves completeness.

## Compatibility and rollback

The existing URLs remain unchanged. The existing public directory and static
service definition are backed up and retained. Rollback restores the prior
service unit/document root and restarts only `ci-dashboard-static.service`.
No Caddy, firewall, Hermes core, credential, or database change is required.

## Feature flag

`CIOS_PUBLICATION_V2=1` controls local and staged activation. The legacy path
remains available only for rollback during Phase 2 and is removed from normal
execution after acceptance.
