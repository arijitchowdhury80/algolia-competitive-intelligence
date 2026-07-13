# CI-OS Dashboard Intelligence Spine UI

Status: deployed and live-validated

## Current slice

Expose the backend `intelligence_spine` contract in the cockpit so Argus is not
only present in JSON. The UI must show the evidence planes, what each plane
proved or missed, whether action is blocked, and the next operator action.

## Constraints

- CI-OS remains a Hermes extension package. No Hermes core edits.
- Existing dashboard visual system is preserved unless a full IA rebuild is
  explicitly started.
- The mounted Algolia design-system folder referenced by the workspace
  instructions was not found at the documented Gmail path. Google Drive is
  mounted under the Algolia account, but targeted searches did not locate an
  `Algolia-Design-System` folder during this slice.
- The UIUX SOP path referenced by `frontend-builder` was not found on disk.

## Evidence log

- RED renderer test:
  `python3 -m pytest tests/dashboard/test_cockpit_renderer.py::test_cockpit_renders_intelligence_spine_as_argus_proof_chain -q --tb=short`
  failed because `id="intelligence-spine"` was not rendered.
- GREEN renderer test:
  focused renderer tests passed.
- Local dashboard verification:
  `python3 -m pytest tests/dashboard -q --tb=short`
  `122 passed in 0.39s`.
- Local full verification:
  `python3 -m pytest -q --tb=short`
  `803 passed, 21 deselected in 5.68s`.
- Local package contract:
  `python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  `PASS: CI-OS Hermes package contract satisfied`.
- Remote deployment:
  backup `/root/.hermes/backups/cios-app-20260711T171953Z-cockpit-intelligence-spine-ui.tgz`;
  `deployed_cockpit_intelligence_spine_ui=yes`.
- Remote renderer verification:
  focused tests `3 passed in 0.30s`;
  cockpit renderer suite `23 passed in 0.18s`.
- Remote package contract:
  `PASS: CI-OS Hermes package contract satisfied`.
- Live publish:
  re-rendered cockpit `355197` bytes from live DB state and published.
- Live public validation:
  `python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/`
  ended with `PASS dashboard_click_validation`.
  `curl -fsS https://ci.chowmes.com/` confirmed the public HTML contains
  `id="intelligence-spine"`, `data-nav-link="intelligence-spine"`,
  `How Argus earned this read`, and `Next operator action`.
