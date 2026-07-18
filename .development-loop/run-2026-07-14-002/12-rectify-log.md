# Rectify Log

## Important finding: private runtime provenance

RED evidence:

- `runtime_provenance` did not exist.
- run-ledger start/finish metadata omitted package and model route.
- the app wrapper allowed publication v2 with an empty package release ID.
- Five focused tests failed before implementation.

Fix:

- Added bounded private runtime provenance with package version,
  `claude-shim` provider, and effective model alias.
- Publication v2 now requires a nonempty conservative
  `CIOS_PACKAGE_VERSION`; legacy/local runs remain explicitly `unversioned`.
- Added provenance to run-stage ledger start and completion metadata only.
- Added a package-preflight invariant for the wrapper requirement.
- No provenance field was added to public dashboard, status, data-plane, or
  publication manifest contracts.

GREEN evidence:

- Focused provenance and package verifier set: `87 passed`.
- Ruff: `All checks passed!`.
- Shell syntax: passed.
- Actual checkout package preflight: passed.
- Full repository suite: `1316 passed, 3 skipped, 23 deselected in 34.45s`.

No Critical or Important review item remains. Rectify auto-advances to
Validate.
