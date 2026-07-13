# CI-OS Dashboard Run Trace

Status: in progress

Goal: make the public dashboard state carry the same Hermes/Argus product-market run evidence as the admin Run Console, so business users can see what the system actually ran and why Argus prioritized specific product surfaces.

Current slice:

- Add typed dashboard state for the product-market run summary.
- Build it from the daily runner's `product_market_summary`.
- Render it as a compact proof strip in the cockpit.
- Keep raw detail in JSON; keep visible UI bounded.
- Extend `ProductMarketRunStatus` with replay counts for product events,
  conversation themes, demand signals, patterns, and recommendations.
- Render a public `Ledger replay read` line in the cockpit run trace so the
  public UI shows the stored evidence replay, not only a prose conclusion.
- Promote and render the Argus 7-day versus 30-day `window_comparison` so the
  run trace can answer what is new this week versus what belongs to the
  broader month.

Verification:

- Local focused dashboard contract tests: 3 passed.
- Local dashboard suite: 124 passed.
- Local package contract: passed.
- Local full suite: 875 passed, 21 deselected.
- Remote focused dashboard contract tests: 3 passed.
- Remote dashboard suite: 124 passed.
- Remote package contract: passed.
- Remote full suite: 868 passed, 1 skipped, 21 deselected, 1 warning.
- Live publish: rerendered cockpit from live DB state, attached operator
  handoff, and published to `https://ci.chowmes.com/`.
- Live validation: public HTML contains `Ledger replay read` and `Argus
  operator handoff`; public JSON contains replay counts
  `product_event_count=318`, `conversation_theme_count=500`,
  `demand_signal_count=0`, `pattern_count=2`, `recommendation_count=0`.
- Live click validation: `PASS dashboard_click_validation`.
- Latest local verification after window comparison:
  - Focused dashboard contracts: `2 passed`.
  - Product-market/dashboard subset: `103 passed`.
  - Dashboard suite: `124 passed`.
  - Full local suite: `878 passed, 21 deselected`.
  - Package contract: `PASS`.
- Production verification after window comparison:
  - Remote focused window/state/render tests: `3 passed`.
  - Remote product-market/dashboard subset: `103 passed`.
  - Remote dashboard suite: `124 passed`.
  - Remote full suite: `871 passed, 1 skipped, 21 deselected, 1 warning`.
  - Remote package contract: `PASS`.
  - Hermes daily wrapper completed and published in `893.1s`.
  - Live public JSON is schema `18`, generated at
    `2026-07-11T22:03:35.987108Z`.
  - Live `product_market_run.window_comparison.summary` says:
    `Last 7 days: 348 product events, 500 conversation themes, 0 demand signals. Last 30 days: 348 product events, 500 conversation themes, 0 demand signals.`
  - Live HTML contains `Evidence window` and `Last 7 days`.
  - Live click validation: `PASS dashboard_click_validation`.

Current reliability gap:

- Hermes cron now runs the CI-OS package through the real container runtime:
  `/opt/data/scripts/cios-daily.sh` inside the `hermes` container.
- Runtime repair completed on 2026-07-11:
  - package wrapper and cron script are synced;
  - app/output/public dashboard directories are writable by `hermes`;
  - CI-OS runtime dependencies are installed in the active container venv;
  - `cron.script_timeout_seconds` is `1200`.
- Forced scheduler run now records `ok`:
  `cios-v2-daily` last run at `2026-07-11T18:35:58.479350-04:00`.
- Public dashboard publish came from the scheduler path, not a root manual
  publish:
  `dashboard published to ci.chowmes.com from /opt/data/apps/cios`.
- Live validation after scheduler publish:
  - `https://ci.chowmes.com/` returned `200`, `364838` bytes.
  - `semantic-dashboard.json` returned `200`, `367224` bytes.
  - `generated_at=2026-07-11T22:35:57.365715Z`.
  - `product_market_run.status=ran`.
  - `product_market_run.window_comparison.summary` says:
    `Last 7 days: 393 product events, 500 conversation themes, 0 demand signals. Last 30 days: 393 product events, 500 conversation themes, 0 demand signals.`
  - Live click validation: `PASS dashboard_click_validation`.
- The daily run is still one monolithic script. The next hardening slice should
  segment the run trace so each stage can succeed, fail, retry, and publish its
  own evidence ledger independently.
- The inward demand plane remains empty in the published window comparison.
