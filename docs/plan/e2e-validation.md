# CI-OS E2E Validation And Launch Readiness Plan

Status: active gate plan

This plan defines what must be true before Argus / CI-OS can be called launch-ready. It exists because isolated green tests, a pretty UI, or a successful publish command do not prove that Hermes actually ran the system, that Argus has trustworthy evidence, or that a business user can click through the product without confusion.

No launch claim is allowed until the executable readiness gate passes against the current deployed state.

## Launch Readiness Command

The final gate is:

```bash
python3 scripts/check_e2e_launch_readiness.py \
  --public-status out/argus-latest-run-status.json \
  --click-validation-log out/dashboard-click-validation.log \
  --package-contract-log out/hermes-package-contract.log \
  --min-active-sources 1 \
  --max-failed-sources 0 \
  --output out/cios-e2e-launch-readiness.json
```

For production, the inputs must come from the deployed Hermes package and the live dashboard:

- `scripts/verify_hermes_package_contract.py --app-dir /root/.hermes/apps/cios`
- `scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/ --tenant algolia`
- `https://ci.chowmes.com/data/argus-latest-run-status.json`

The gate passes only when the public status is published, the dashboard was updated by the latest run, source coverage is complete, failed sources are within the explicit launch budget, inward demand was processed, product reality is present, the public payload is safe, dashboard click validation passed, and the Hermes package contract passed.

## Hermes Execution Gate

Purpose: prove that CI-OS is an extension package executed by Hermes, not a detached standalone app.

Required evidence:

- `deploy/cios-daily.sh` is the execution wrapper used by Hermes cron.
- `scripts/verify_hermes_package_contract.py` passes for the installed package.
- The wrapper runs the daily producer, product-market spine, demand readiness, demand intake, operator handoff, data-plane manifest, public status export, dashboard publish or blocked publish path, and final artifact copy.
- Timeout handling kills the run tree and writes a public-safe blocked status without updating dashboard HTML.
- The package contract verifies all required scripts, admin service files, source paths, product surface extraction controls, product muscle queue hooks, demand import hooks, and wrapper hooks.

Failure examples:

- Hermes wrapper missing or not executable.
- CI-OS code requires editing Hermes core.
- Package contract fails.
- Public status exists but does not trace to the current Hermes run.
- Timeout path leaves orphan work or silently publishes stale dashboard HTML.

## Frontend E2E Gate

Purpose: prove the public dashboard is usable and every key click routes to the right state.

Required evidence:

- `scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/ --tenant algolia` prints `PASS dashboard_click_validation`.
- Navigation links land on distinct sections and update hash/current state.
- Partner selector updates selected competitor, active panel, role implications, and hash.
- Priority move selection updates the selected competitor panel and role implications.
- Competitor-specific brief links open competitor-specific brief pages, not a shared wrong brief.
- Timeline, semantic layer, heat map, confidence rubric, evidence coverage, source health, and market coverage sections render on desktop, tablet, and mobile.
- Quiet run state is explicit when no material priority move exists.
- Evidence appendix exposes source health and failed sources.

Failure examples:

- All nav buttons land on the same section.
- Constructor opens Elastic content.
- Selected competitor does not update the role sections.
- Confidence rubric is renderer-invented instead of backend scorecard or explicit `Not scored`.
- Mobile hides the partner selector, evidence, or selected competitor context.

## Backend and Data Gate

Purpose: prove Argus is reasoning from evidence planes, not UI copy.

Required evidence:

- Product reality exists in `product_change_events` and feature positions.
- Conversation themes exist only with evidence URLs.
- Demand signals exist only from GA / Looker / equivalent inward evidence.
- Pattern observations and recommendations carry evidence and scorecards.
- `argus-latest-run-status.json` reports source coverage, product-market counts, planes, blockers, and safety state.
- `semantic-dashboard.json` contains no `/root/`, `/tmp/`, secret values, or admin-only write URLs.
- `product_market_run.decision_read` or equivalent run intelligence explains market direction, priority reason, confidence basis, blockers, and actions.
- Missing demand blocks action promotion rather than fabricating urgency.

Failure examples:

- A recommendation exists with zero demand evidence when demand is required.
- A claim lacks source URLs.
- Public JSON leaks local artifact paths.
- Product proof and conversation proof are merged without plane separation.

## Competitor Registry Gate

Purpose: prove users can see and manage the monitored universe.

Required evidence:

- Local-only admin lists active competitors, domains, statuses, source counts, source health, product surfaces, and latest checked state.
- Admin supports add, edit, pause, retire for competitors.
- Admin supports add, edit, pause, retire for source URLs.
- Admin supports add, edit, pause, retire for product surface URLs.
- Public dashboard shows the monitored universe read-only and does not expose anonymous writes.
- Feature comparison and product muscle work queue include all active competitors with current evidence or explicit unknown states.

Failure examples:

- Only Elastic and Constructor appear without explaining the monitored universe.
- Unknown capabilities disappear from the matrix.
- Adding a competitor requires raw SQL or editing YAML.
- Public users can mutate the registry.

## Demand, GA4, and Looker Gate

Purpose: prove Argus can merge outward market/product evidence with inward audience response.

Required evidence:

- GA4 connector readiness explicitly reports required keys and never says `Missing: None` when disabled.
- Manual GA / Looker upload queues, validates, previews, prepares, refreshes, archives on success, and preserves source files on failed refresh.
- Demand import status reports coverage against the active Argus demand work order.
- Prepared demand rows carry Argus capability metadata, related competitors, evidence URLs, matched/off-plan state, and suggested filters.
- Demand refresh updates the ledger, dashboard, demand readiness, operator handoff, data-plane manifest, and public run status.
- Launch readiness fails while demand plane is `blocked_missing_demand_source`.

Failure examples:

- Demand is missing but Argus still recommends action.
- Uploaded Looker data is accepted without coverage feedback.
- Refresh consumes raw files before downstream dashboard refresh succeeds.
- GA4 export ignores the current Argus demand plan.

## Intelligence and Learning Gate

Purpose: prove Argus has a learning loop and not just a reporting loop.

Required evidence:

- User challenges, rejected reads, and saved learnings become durable learning events.
- Learning proposals target concrete policies such as source coverage, scoring, extraction priority, and next-sweep instructions.
- Approved learning changes affect the following run through explicit policy/application artifacts.
- Argus can explain why it prioritized a competitor, what evidence was weak, what it needs next, and what it learned.

Failure examples:

- Chat repeats the same canned answer.
- Saved learning does not affect the next run.
- Argus cannot distinguish a blocked evidence plane from a quiet market day.

## Production Acceptance

Production is acceptable only when:

- Hermes package contract passes on `/root/.hermes/apps/cios`.
- Hermes daily wrapper exits successfully for a non-timeout run.
- All active sources are checked or explicitly skipped.
- Public latest-run status is `published`.
- `public_dashboard_updated` is `true`.
- Source failures are zero or within an explicitly approved degradation budget.
- Audience demand is processed or the release is explicitly scoped as a non-actionable watch-mode demo.
- Dashboard click validation passes against `https://ci.chowmes.com/`.
- Public payloads are path/secret safe.
- `scripts/check_e2e_launch_readiness.py` exits `0`.

If any item fails, the product may be shown as a blocked diagnostic/operator surface, but it must not be called a launch-ready Competitive Intelligence Operating System.
