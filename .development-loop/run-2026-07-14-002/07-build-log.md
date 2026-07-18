# Build Log

## Scope delivered

- Added one wrapper-owned `CIOS_RUN_ID` and propagated it through daily run,
  source coverage, dashboard, data-plane manifest, public status, and verdicts.
- Added `cios.publication` contracts for allowlisted artifacts, canonical
  manifests, recursive safety scanning, independent final-tree validation,
  immutable release/diagnostic storage, serialized promotion, atomic pointers,
  and status-last replacement.
- Routed both the Hermes wrapper and local admin refresh through the shared
  publisher behind `CIOS_PUBLICATION_V2`.
- Added one stable router for root and `/v2`, including the exact served
  `publication-manifest.json` bytes.
- Replaced PASS strings with fresh, run-bound package, publication, click, and
  launch verdicts. Launch now binds the publication verdict digest to the
  served decision manifest.
- Added current-run product extraction arithmetic and uniquely identified
  source dispositions.
- Added the unprivileged `cios-static.service` with cgroup and systemd sandbox
  limits plus the `/opt/cios/public-store` ownership contract.

## TDD evidence

Observed RED before implementation for:

- tampered stable router link;
- missing process-wide publication lock;
- absent manifest routes;
- `/tmp`, `/private/var`, `/app`, Windows-user path leaks;
- nested credential containers;
- missing source disposition reference;
- missing publication verdict and exact manifest digest binding.

All corresponding tests passed after the focused implementations. The review
also added a RED test for a symlinked generation bucket; the store now rejects
it before writing outside its root.

## Verification

- Focused publication, security, launch, and package checks: `131 passed`.
- Full repository suite: `1312 passed, 3 skipped, 23 deselected in 34.42s`.
- Ruff over all changed Python surfaces: `All checks passed!`.
- `python3 -m compileall -q src scripts`: passed.
- `sh -n deploy/cios-daily-app.sh deploy/cios-host-permissions.sh`: passed.
- Actual-checkout package preflight: `PASS: CI-OS Hermes package contract satisfied`.
- `git diff --check`: passed.

No production route, Caddy config, firewall, Hermes core, credential, or live
service was changed in Build.

## Gate

PASS. The full suite is green, so Build auto-advances to Code Health.
