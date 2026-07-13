# CI-OS Dashboard Operator Handoff

Status: completed

Goal: make the public dashboard consume the Hermes-produced `argus-operator-handoff.json` so business users can immediately see whether Argus is actionable, blocked, or limited, and what evidence/action is next.

Current slice:

- Add a typed dashboard state field for the operator handoff.
- Render it in the Argus proof-chain/run-read area.
- Preserve the handoff through the daily Hermes wrapper before publish.
- Verify locally and on the deployed Hermes package.

Verification:

- Local focused tests: 54 passed.
- Local full suite: 870 passed, 21 deselected.
- Remote focused tests: 6 passed.
- Remote full suite: 863 passed, 1 skipped, 21 deselected, 1 warning.
- Live Hermes wrapper: completed and published to `https://ci.chowmes.com/`.
- Live smoke: public JSON includes `operator_handoff.status=blocked_on_evidence`; public HTML renders `Argus operator handoff`; internal command href is not exposed in public HTML.

## 2026-07-12 Demand Blocker Consistency Repair

Status: deployed and live-validated.

The handoff builder now creates a synthetic demand work item from
`argus-demand-readiness.json` when demand readiness is action-blocking and the
generic evidence work queue only contains weaker limiting items. The dashboard
attach step now mirrors a blocking handoff into the public
`intelligence_spine` so the proof-chain next action and operator handoff cannot
contradict the public latest-run status.

Verification:

- RED focused tests first failed with `limited_by_evidence` and stale
  conversation-source next action.
- Local focused tests: `2 passed`.
- Local affected tests: `52 passed`.
- Local full suite: `1146 passed, 23 deselected, 1 warning`.
- Remote backup:
  `/root/.hermes/backups/cios-handoff-demand-sync-20260712T230847Z.tgz`.
- Remote focused tests: `2 passed`.
- Remote affected tests: `52 passed`.
- Remote full suite: `1145 passed, 1 skipped, 23 deselected, 1 warning`.
- Remote package contract: `PASS: CI-OS Hermes package contract satisfied`.
- Public refresh preserved `publish_status=blocked`.
- Live public JSON now has:
  `operator_handoff.status=blocked_on_evidence`,
  `operator_handoff.top_blocker.evidence_plane=demand`,
  `operator_handoff.next_operator_action="Configure GA4 or upload a GA / Looker export."`,
  and matching `intelligence_spine.next_operator_action`.
- Live dashboard E2E click validation: `PASS dashboard_click_validation`.
