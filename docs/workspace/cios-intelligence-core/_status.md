# CI-OS Intelligence Core

Status: in progress
Date: 2026-07-12

## Current Slice

Build the backend intelligence layer behind the Argus screen so the UI is not an empty shell. The current architecture contract is `02-muscle-brain-architecture.md`: CI-OS must supply Hermes with five evidence planes, a durable run-stage ledger, product muscle, inward demand, scoring, recommendations, quality gates, and explicit learning loops. The next build slice should keep hardening the Hermes-run evidence spine before adding more UI.

Demand work-order guide slice: the local-only admin API now exposes a
structured Argus demand work-order guide at
`/api/tenants/{tenant}/argus/demand-imports/work-order`. The guide is built
from the active Hermes data-plane demand plan and gives operators the exact
template link, upload action, refresh action, accepted file types, required
GA/Looker columns, matching fields, per-topic filter terms, related
competitors, evidence counts, and step sequence needed to unblock the inward
demand plane. It deliberately omits `why_collect` rationale and does not
invent metric values.

Verification: RED focused tests first failed with
`ImportError: cannot import name 'demand_collection_plan_operator_guide'`.
After implementation, local focused tests passed `3 passed`; local
admin/demand suite passed `94 passed`; local full suite passed
`1180 passed, 23 deselected`; and local package contract passed. Deployed to
`/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-demand-work-order-guide-20260713T022403Z.tgz`.
Remote focused tests passed `3 passed, 1 warning`; remote admin/demand suite
passed `94 passed, 1 warning`; remote package contract passed; `cios-admin`
was restarted active. Remote localhost smoke returned `/health` `{"status":
"ok"}` and the new work-order endpoint returned `status=ready`,
`topic_count=12`, `template_href=/api/tenants/algolia/argus/demand-imports/template?planned=1`,
and first topic `Channel Assistant (AI Agent)`. Public click validation still
passes. Launch readiness still fails correctly on `public_status_publishable`
and `audience_demand_processed`, with next action
`configure_ga4_or_upload_demand_export`.

Public status refresh-path repair: admin/dashboard refresh now regenerates the
public-safe latest-run status artifact and the staged publisher copies it to
`data/argus-latest-run-status.json` and `v2/data/argus-latest-run-status.json`.
This closes the gap where a DB/source repair could correctly rerender
`semantic-dashboard.json` but leave the launch gate reading a stale
`argus-latest-run-status.json`.

Live source-health repair: Coveo sources that return the AWS WAF challenge from
the VPS are classified as blocked source URLs rather than active fetch failures.
After deploying the refresh-path repair and rerendering public artifacts from
the repaired DB state, live status now reports `active_source_count=43`,
`checked_source_count=43`, and `failed_source_count=0`. The live semantic
dashboard still carries the full 48-row source ledger, with 43 active rows and
5 blocked rows. Live click validation still passes.

Verification: RED regression first failed because
`AdminDashboardRefreshRunner` produced no `public_run_status` sidecar. After
implementation, focused local regression passed `1 passed`; affected local
admin/publisher/public-status/launch-gate suite passed `26 passed`; local
package contract passed. Deployed package focused regression passed
`1 passed`; deployed package contract passed. Production refresh published the
sidecar set from `/root/.hermes/apps/cios/out` to the public dashboard. The
current launch gate still fails correctly on `public_status_publishable` and
`audience_demand_processed`, because inward demand remains
`blocked_missing_demand_source` with `demand_signal_count=0`. Production has no
queued manual demand upload under `data/looker`, and the demand source gate
reports `ga4_ready=false`, `manual_export_ready=false`,
`manual_inbox_file_count=0`, and next action
`configure_ga4_or_upload_demand_export`.

Demand operator gate usability slice: the demand readiness exporter and
standalone demand-source gate now load `<app-dir>/out/argus-dashboard.json` by
default when `--dashboard` is omitted. The Hermes wrapper still passes the
dashboard explicitly, but manual/operator checks now preserve the current
Argus demand work order instead of reporting `demand_plan_topic_count=0`.

Verification: RED CLI tests first failed because the default no-dashboard
path produced zero planned topics. After implementation, focused local tests
passed `2 passed`; adjacent local demand-readiness/import/gate suite passed
`35 passed`; local package contract passed. Deployed to
`/root/.hermes/apps/cios`; remote focused tests passed `2 passed`. A remote
no-`--dashboard` production gate check now fails honestly with
`readiness_status=blocked_missing_demand_source`, `source_ready=false`, and
`topic_count=12`; top topics include `Channel Assistant (AI Agent)`,
`Complete Discovery Plan`, `Conversational Assistant (AI Agent)`,
`AI Feed Audits (Channel Assistant)`, and `Flexible Pricing`.

Public demand work-order CSV slice: the public artifact publisher and Hermes
daily wrapper now publish `argus-demand-plan-template.csv` alongside the public
status and data-plane artifacts. This makes the current Argus demand work order
downloadable from `https://ci.chowmes.com/data/argus-demand-plan-template.csv`
instead of only naming the filename in JSON. The file is public-safe: it
contains the GA/Looker import columns plus Argus topic, capability key,
assessment, suggested filters, related competitors, why-collect rationale, and
evidence URLs.

Verification: RED tests first failed because neither admin refresh nor the
Hermes wrapper copied `argus-demand-plan-template.csv` to public `data/`.
After implementation, focused local tests passed `3 passed`; adjacent
admin/deploy/package-contract tests passed `72 passed`; package contract
passed. Deployed to `/root/.hermes/apps/cios` and synced
`/root/.hermes/scripts/cios-daily.sh`; remote focused tests passed `3 passed`
and remote package contract passed. Production refresh published the CSV.
Live verification fetched
`https://ci.chowmes.com/data/argus-demand-plan-template.csv` with `12` rows and
top topics `Channel Assistant (AI Agent)`, `Complete Discovery Plan`,
`Conversational Assistant (AI Agent)`, `AI Feed Audits (Channel Assistant)`,
and `Flexible Pricing`. Live click validation still passes. Launch readiness
still fails correctly because `audience_demand.status=blocked_missing_demand_source`
and `demand_signal_count=0`.

Demand import plan-match parity slice: the standalone
`scripts/import_demand_and_refresh.py` operator fast lane now loads the active
Argus demand collection plan from current output artifacts
(`argus-demand-readiness.json`, `argus-data-plane-manifest.json`, or an
explicit `--demand-plan`) and passes it into the same upload/prepare hooks used
by the admin app. This closes the parity gap where admin demand uploads could
show plan coverage and attach `argus_*` metadata, but the CLI/Hermes fast lane
prepared generic GA / Looker exports with empty plan coverage. The import
summary now reports whether a demand plan was loaded, its source path, and topic
count, and prepared rows get `argus_plan_matched`,
`argus_capability_key`, related competitors, assessment, filters, and evidence
metadata when they match the active work order.

Verification: RED regression first failed with `KeyError: 'demand_plan'` and
empty `demand_plan_coverage` for a generic GA / Looker export even though
`out/argus-demand-readiness.json` contained the current Argus work order. After
implementation, the focused local regression passed `1 passed`; the local
demand-import script suite passed `15 passed`; adjacent local admin/import and
demand-readiness suites passed `20 passed, 2 deselected` and `18 passed`; local
full suite passed `1176 passed, 23 deselected`; local package contract passed.
Deployed to `/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-demand-plan-cli-20260713T020245Z.tgz`. Remote
focused demand-import regression passed `2 passed`, remote demand-import script
suite passed `15 passed`, remote package contract passed, and live click
validation passed `PASS dashboard_click_validation`. Launch readiness still
fails correctly on `public_status_publishable` and `audience_demand_processed`
because production still has `audience_demand.status=blocked_missing_demand_source`
and `demand_signal_count=0`.

Demand intake explicit plan-handoff slice: `scripts/run_argus_demand_intake.py`
now passes the exact `demand_collection_plan` returned by demand readiness into
the queued manual import path, not only into GA4 export. `scripts/import_demand_and_refresh.py`
now accepts a direct `demand_plan` object in addition to discovering a plan from
current artifacts. This removes another brittle filesystem dependency from the
Hermes demand intake coordinator: the readiness decision and the import
normalization now use the same work order when Hermes finds queued manual
exports. Production inspection before the change confirmed the live blocker is
real, not a hidden processing failure: GA4 is disabled/unconfigured,
`CIOS_GA4_PROPERTY_ID` is absent, credentials are absent, and the manual
`data/looker/algolia` drop folder has no files.

Verification: RED regression first failed with `KeyError: 'demand_plan'`
because the manual import call did not include the readiness plan. After
implementation, focused local tests passed `2 passed`; affected local demand
intake/import/readiness suites passed `41 passed`; local full suite passed
`1178 passed, 23 deselected`; local package contract passed. Deployed to
`/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-demand-intake-plan-handoff-20260713T020946Z.tgz`.
Remote focused tests passed `2 passed`, remote affected demand intake/import
suite passed `25 passed`, and remote package contract passed. Live click
validation passed `PASS dashboard_click_validation`. Live launch readiness
still fails correctly on `public_status_publishable` and
`audience_demand_processed`, with production reporting
`audience_demand.status=blocked_missing_demand_source`,
`demand_signal_count=0`, `looker_ready_count=0`, and next action
`configure_ga4_or_upload_demand_export`.

Feature comparison work-order slice: the product-muscle matrix now includes
capabilities from the current Hermes/Argus demand collection plan even when the
feature ledger has no captured product proof for those capabilities. This fixes
the blind spot where planned capabilities could be present in the demand work
order but absent from the feature comparison matrix. Planned rows render as
`unknown` across monitored companies until Scout/product-surface extraction or
ledger replay captures product proof.

Verification: RED focused tests first failed because the feature comparison API
never called the data-plane manifest store and the admin HTML omitted planned
capabilities. After implementation, local focused tests passed `2 passed`;
local affected admin/product-muscle/export suite passed `104 passed`; local
full suite passed `1155 passed, 23 deselected`; and local package contract
passed. Remote deployment backup:
`/root/.hermes/backups/cios-feature-comparison-plan-20260713T003121Z.tgz`.
Remote focused tests passed `2 passed, 1 warning`; remote affected suite
passed `104 passed, 1 warning`; remote full passed
`1154 passed, 1 skipped, 23 deselected, 1 warning`; remote package contract
passed; `cios-admin.service` is active and `/health` returned `{"status":"ok"}`.
Live admin/API smoke showed `company_count=28`, `row_count=189`, and planned
rows including `AI Shopping Agent`, `Channel Assistant (AI Agent)`,
`Complete Discovery Plan`, and `Conversational Assistant (AI Agent)`.

Targeted product-muscle work queue slice: planned unknown capability cells now
become actionable product-muscle work items. When Argus asks for proof of a
capability from the current demand/product work order and a competitor with
active product surfaces still has an unknown matrix cell, CI-OS emits a
targeted extraction task for that company and capability. The Hermes-callable
export script now accepts `--demand-readiness` and derives planned
capabilities from `argus-demand-readiness.json`, so the daily wrapper and
manual demand-refresh sidecar produce the same plan-aware product-muscle
artifact as the admin API.

Verification: RED focused tests first failed because no targeted work item was
emitted and the export script had no demand-readiness helper. After
implementation, local focused tests passed `3 passed`; local affected
product-muscle/wrapper/import/preflight suite passed `99 passed`; local full
suite passed `1158 passed, 23 deselected`; and local package contract passed.
Remote deployment backup:
`/root/.hermes/backups/cios-product-muscle-planned-capabilities-20260713T004051Z.tgz`.
Remote focused tests passed `3 passed`; remote affected suite passed
`99 passed`; remote full passed `1157 passed, 1 skipped, 23 deselected,
1 warning`; remote package contract passed; `cios-admin.service` is active and
`/health` returned `{"status":"ok"}`. Live admin/API and Hermes export smoke
both produced `45` targeted capability work items from the current
`argus-demand-readiness.json`.

Demand refresh archive-on-success slice: the local-only admin/API demand refresh
paths now move consumed GA4 / Looker demand uploads out of the active tenant
drop folder after the complete downstream chain succeeds. The raw upload is
archived only after demand preparation, demand-ledger persistence, Argus ledger
replay, and dashboard refresh all complete. If dashboard refresh fails, the
source file remains in the inbox for operator retry. This closes the admin/API
parity gap where the manual fast lane archived consumed uploads, but
`/argus/demand-imports/refresh` and `/argus/ga4-export/refresh` could leave
already-consumed evidence queued for future reprocessing.

Verification: RED focused tests first failed with missing `archive` payloads
and raw `ga-pages.csv` / `ga4-demand.json` files still present after successful
refresh (`4 failed, 2 passed`). After implementation, the exact focused local
set passed `6 passed, 1 warning`; the adjacent local admin/import/integration
suite passed `98 passed, 2 deselected, 1 warning`; local compile passed; and
the local full suite passed `1144 passed, 23 deselected, 1 warning`. Remote
deployment backup:
`/root/.hermes/backups/cios-demand-refresh-archive-20260712T225031Z.tgz`.
Remote focused regression passed `6 passed, 1 warning`; remote adjacent suite
passed `98 passed, 2 deselected, 1 warning`; remote full passed
`1143 passed, 1 skipped, 23 deselected, 1 warning`; remote package contract
passed; `cios-admin.service` restarted active and `/health` returned
`{"status":"ok"}`.

Public handoff consistency slice: the Argus operator handoff now promotes a
blocking `argus-demand-readiness` state into the work queue when the generic
evidence queue only reports a weaker limiting item. This closes the live
contradiction where `argus-latest-run-status.json` said the run was blocked by
missing GA4 / Looker demand evidence while `semantic-dashboard.json` told the
operator to repair conversation sources. The dashboard attachment step now also
syncs a blocking handoff into `intelligence_spine.next_operator_action`, keeps
`can_recommend=false`, and appends the handoff blocker into
`blocked_actions`/`confidence_limits`.

Verification: RED focused tests first failed because the handoff stayed
`limited_by_evidence` and the dashboard spine kept the conversation-source next
action. After implementation, local focused tests passed `2 passed`; local
affected suite passed `52 passed`; local full suite passed
`1146 passed, 23 deselected, 1 warning`. Remote deployment backup:
`/root/.hermes/backups/cios-handoff-demand-sync-20260712T230847Z.tgz`.
Remote focused tests passed `2 passed`; remote affected suite passed
`52 passed`; remote full suite passed
`1145 passed, 1 skipped, 23 deselected, 1 warning`; remote package contract
passed. Public artifacts were refreshed from the current run with
`publish_status=blocked`. Live JSON now shows
`operator_handoff.status=blocked_on_evidence`,
`operator_handoff.top_blocker.evidence_plane=demand`,
`operator_handoff.next_operator_action="Configure GA4 or upload a GA / Looker export."`,
and the same value in `intelligence_spine.next_operator_action`. Live click
validation passed `PASS dashboard_click_validation`.

Public demand work-order slice: `argus-latest-run-status.json` now promotes the
active audience-demand work order to top-level public-safe fields:
`demand_collection_plan` and `demand_plan_template`. The data was already
available under `planes.audience_demand`, but monitors/operators should not
need to spelunk nested plane details to see which Argus-prioritized topics must
be collected before recommendations can become actionable. The promoted fields
strip local paths and internal `why_collect` rationale while preserving status,
topic count, source dashboard field, top topics, suggested filters, related
competitors, evidence URL counts, and the current CSV template filename.

Verification: RED public-status test first failed with
`KeyError: 'demand_plan_template'` because no top-level demand work order was
published. After implementation, the focused test passed `1 passed`; local
public-status/data-plane/wrapper/preflight subset passed `86 passed`; local
full suite passed `1146 passed, 23 deselected, 1 warning`. The live public
artifact was refreshed from the deployed manifest/dashboard on 2026-07-12 and
verified through `https://ci.chowmes.com/data/argus-latest-run-status.json`:
`status=blocked_on_evidence`, `publish_status=blocked`,
`demand_collection_plan.status=needs_demand_source`, `topic_count=12`,
`demand_plan_template.filename=argus-demand-plan-template.csv`, and
`unsafe_paths=False`.

Public demand work-order UI slice: the Argus operator handoff now preserves
and renders the current `demand_collection_plan` instead of dropping it during
dashboard model validation. When the run is blocked on inward demand, the
public dashboard's Argus handoff shows a compact "Demand work order" with the
topic count, generated template filename, top planned topics, related
competitors, and evidence-reference counts. This turns the blocker from a
generic "configure GA4" message into an operator-visible collection queue while
still keeping admin hrefs and local artifact paths out of the public HTML.

Verification: RED renderer regression first failed because `"Demand work
order"` was absent from the generated cockpit HTML. After implementation,
focused local attach/render tests passed `5 passed`; affected local
dashboard/script/deploy tests passed `119 passed`; local full suite passed
`1146 passed, 23 deselected, 1 warning`. Deployed to
`/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-dashboard-demand-workorder-20260712T232940Z.tgz`.
Remote focused attach/render tests passed `5 passed`; remote affected suite
passed `119 passed`; remote full suite passed
`1145 passed, 1 skipped, 23 deselected, 1 warning`. The live public dashboard
was re-rendered and verified through `https://ci.chowmes.com/`: HTML contains
`Demand work order`, `argus-demand-plan-template.csv`, `Channel Assistant`,
and the current next operator action; public semantic JSON preserves
`operator_handoff.demand_collection_plan`; no `/root/` or `/tmp/` paths appear
in public HTML. Live click validation still passes
`PASS dashboard_click_validation`.

Public semantic JSON redaction slice: the dashboard publisher now recursively
removes local filesystem artifact paths from the public semantic dashboard JSON
while preserving public evidence URLs such as `https://...` and safe logical
evidence references such as `looker://...`. This closes the leak where
`semantic-dashboard.json` exposed internal `/root/.hermes/...` and
`/tmp/cios-product-market/...` paths through product-market run metadata,
demand readiness, and operator handoff artifact refs. The typed internal
dashboard state can still carry runbook paths before publication; redaction
happens at `to_json_dict`.

Verification: RED publisher regression first failed because serialized public
JSON still contained `/root/`. After implementation, focused local publisher
test passed `1 passed`; affected local dashboard/script/deploy suite passed
`120 passed`; local full suite passed
`1147 passed, 23 deselected, 1 warning`. Deployed to
`/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-public-semantic-redaction-20260712T233632Z.tgz`.
Remote focused verification passed `6 passed`; remote affected suite passed
`120 passed`; remote package preflight passed
`PASS: CI-OS Hermes package contract satisfied`; remote full suite passed
`1146 passed, 1 skipped, 23 deselected, 1 warning`. The live public dashboard
was re-rendered and verified through `https://ci.chowmes.com/` and
`https://ci.chowmes.com/data/semantic-dashboard.json`: demand work-order HTML
still renders, `operator_handoff.demand_collection_plan` is still present,
`demand_plan_template.filename=argus-demand-plan-template.csv`, and public
semantic JSON now has `json_root_count=0` and `json_tmp_count=0`. Live click
validation still passes `PASS dashboard_click_validation`.

Newest verified slice: `ProductMarketIntelligenceBrief` now carries a structured
`decision_read` object. The read turns deterministic product-market evidence
into the business answer the screen needs: market direction, why the priority
exists, strategic insight, tactical action, confidence basis for product,
conversation, and demand planes, blockers, and evidence URLs. When inward
demand is missing, the decision read stays in watch mode, withholds owner
actions, marks the audience-demand plane missing, and explains the blocker
instead of pretending the recommendation is actionable.

Follow-up verified slice: the cockpit now renders the backend `decision_read`
inside the Hermes / Argus run trace. The trace shows the Argus decision status,
market direction, priority reason, evidence-plane confidence, first strategic
insight, promoted tactical action, and blocker when action is withheld. This
keeps the UI tied to the backend intelligence contract rather than a browser
heuristic.

Decision-contract promotion slice: dashboard state schema is now v25 and
`ProductMarketRunStatus` exposes `decision_read` as a first-class field
promoted from `intelligence_brief.decision_read`. Public dashboard JSON now
has `product_market_run.decision_read`, and the Hermes-facing
`argus-data-plane-manifest.json` carries a compact `argus_decision` summary
with status, market direction, priority reason, action count, blocker count,
evidence URL count, and evidence-plane confidence basis. This lets Hermes and
operator surfaces consume the current Argus judgment without scraping nested
brief prose.

Newest verified slice: the Hermes daily wrapper now publishes a public-safe
latest-run status artifact even when the main dashboard publish is blocked.
`data/argus-latest-run-status.json` and `v2/data/argus-latest-run-status.json`
now expose the current run's blocked/published status, data-plane status,
source coverage, product-market counts, blockers, and next Hermes action while
redacting internal artifact paths. The main dashboard and semantic state still
remain gated until the publish criteria clear.

Reliability hardening slice: the Hermes daily wrapper now enforces
`CIOS_DAILY_RUN_TIMEOUT_SECONDS` around `scripts/daily_production_run.py`
instead of waiting forever before the blocked-status path can run. If the
runner exceeds the budget, the wrapper kills the process tree, writes a minimal
`blocked_runtime_timeout` data-plane manifest, publishes only the public-safe
`argus-latest-run-status.json` files, and exits `124` without touching the
dashboard HTML or semantic JSON. The package preflight contract now rejects a
wrapper that removes the daily-run timeout guard.

Public-status correctness slice: `scripts/export_public_run_status.py` now
computes source coverage from the current list-shaped `source_health` dashboard
payload as well as the older summary shape. Live blocked-run status can now
show active, checked, and failed source counts from the actual source-health
rows instead of reporting zero coverage after a real 48-source sweep.

Demand-plan actionability slice: `scripts/export_argus_demand_readiness.py`
now derives demand collection topics from product-market pattern rows when the
product-feature comparison read is empty. Hermes still prefers the feature
comparison matrix when available, but a blocked demand plane can now fall back
to current Argus pattern observations and decision-read actions, carrying
capability topics, related competitors, evidence URLs, suggested filters, and
the action rationale into `demand_collection_plan` instead of publishing a
generic no-topic demand blocker.

Demand-plan status surfacing slice: the data-plane manifest now enriches
audience-demand blockers with sanitized planned demand topics even when the
evidence work queue already created a generic `Demand plane missing` blocker.
The public latest-run status now exposes a reduced demand collection plan:
status, topic count, source field, top planned topics, related competitors,
suggested filters, and evidence URL counts. It intentionally strips local
paths, admin hrefs, and internal `why_collect` rationale while still making the
blocked run operationally intelligible.

Demand-plan work-order artifact slice: the Hermes daily wrapper now exports
`out/argus-demand-plan-template.csv` from the same
`argus-demand-readiness.json` produced in the current run, on both successful
and blocked daily-run paths. The CSV reuses the admin demand-import plan
template builder, so the admin download and cron artifact stay on one contract.
The package preflight now requires the exporter script and wrapper hook, and
wrapper tests verify the artifact is generated before publish-side artifacts
continue.

Manual demand fast-lane parity slice: `scripts/import_demand_and_refresh.py`
now refreshes `out/argus-demand-plan-template.csv` immediately after
`argus-demand-readiness.json` during manual or queued demand imports. This
keeps operator-triggered Argus refreshes aligned with the Hermes daily wrapper:
both paths leave the same current-run demand work order before attaching
summaries, work queues, operator handoff, data-plane manifest, or public
artifacts.

Manual demand preview coverage slice: the local-only admin demand import path
now evaluates queued GA / Looker files against the current Argus
`demand_collection_plan` from the Hermes data-plane manifest before refresh.
Each preview reports `demand_plan_coverage` with covered, partial, off-plan, or
not-evaluated status plus matched and missing planned topics. This makes the
inward demand blocker more actionable: an operator can see whether an upload
actually covers Argus' requested topics before persisting demand signals and
refreshing the Argus read.

Verification: RED tests first failed because demand previews did not accept a
plan, the admin API never consulted the data-plane manifest for import status,
and the HTML preview table had no plan-coverage column. After implementation,
focused tests passed `3 passed, 1 warning`; affected admin/import/demand-plan
tests passed `99 passed, 1 warning`; local full suite passed
`1150 passed, 23 deselected, 1 warning`; local package contract passed
`PASS: CI-OS Hermes package contract satisfied`.

Deployment verification: deployed to `/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-demand-preview-coverage-20260713T000154Z.tgz`.
Remote package contract passed; remote focused coverage tests passed
`3 passed, 1 warning`; remote affected admin/import/demand-plan tests passed
`99 passed, 1 warning`; remote full suite passed
`1149 passed, 1 skipped, 23 deselected, 1 warning`; `cios-admin.service`
restarted active and `/health` returned `{"status":"ok"}`. Live admin smoke
confirmed the demand imports surface now renders `Plan coverage`; production
currently has `queued_previews=0`, so no live queued file exists to annotate.

Manual demand prepare metadata slice: demand import preparation now applies the
same Argus demand work order to normalized manual GA / Looker rows before they
enter the product-market ledger. Matching rows receive
`argus_capability_key`, assessment, suggested filters, related competitors,
why-collect rationale, evidence URLs, and `argus_plan_matched=true`. The
prepare manifest also stores per-file `demand_plan_coverage`, so refresh
results can explain whether imported evidence covered the requested demand
topics.

Verification: RED tests first failed because `DemandImportStore.prepare()` did
not accept `demand_plan` and the prepare API did not load the data-plane
manifest. After implementation, focused tests passed `2 passed, 1 warning`;
affected admin/import/demand refresh tests passed `115 passed, 1 warning`;
local full suite passed `1152 passed, 23 deselected, 1 warning`; local package
contract passed `PASS: CI-OS Hermes package contract satisfied`.

Deployment verification: deployed to `/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-demand-prepare-metadata-20260713T001108Z.tgz`.
Remote package contract passed; remote focused prepare-metadata tests passed
`2 passed, 1 warning`; remote affected admin/import/demand refresh tests passed
`115 passed, 1 warning`; remote full suite passed
`1151 passed, 1 skipped, 23 deselected, 1 warning`; `cios-admin.service`
restarted active and `/health` returned `{"status":"ok"}`. Live admin smoke
confirmed the demand imports surface still renders `Plan coverage`; production
currently has `queued_previews=0`, so no live queued file exists to annotate or
prepare.

Manual demand upload coverage slice: the upload API and HTML upload form now
load the current Hermes data-plane demand plan before queuing a GA / Looker
file. The JSON upload response reports immediate `demand_plan_coverage`, so an
operator can tell at upload time whether the file is on-plan, partial, or
off-plan before running prepare or refresh.

Verification: RED test first failed because the upload route never consulted
the data-plane manifest. After implementation, focused upload test passed
`1 passed, 1 warning`; affected admin/import/demand refresh tests passed
`116 passed, 1 warning`; local full suite passed
`1153 passed, 23 deselected, 1 warning`; local package contract passed
`PASS: CI-OS Hermes package contract satisfied`.

Deployment verification: deployed to `/root/.hermes/apps/cios` with backup
`/root/.hermes/backups/cios-demand-upload-coverage-20260713T001733Z.tgz`.
Remote package contract passed; remote focused upload test passed
`1 passed, 1 warning`; remote affected admin/import/demand refresh tests passed
`116 passed, 1 warning`; remote full suite passed
`1152 passed, 1 skipped, 23 deselected, 1 warning`; `cios-admin.service`
restarted active and `/health` returned `{"status":"ok"}`. Live admin smoke
confirmed the demand imports surface still renders `Plan coverage`; production
currently has `queued_previews=0`.

Admin refresh parity slice: `src/cios/admin/dashboard_refresh.py` now refreshes
`out/argus-demand-plan-template.csv` immediately after
`argus-demand-readiness.json` during admin-triggered dashboard refreshes. This
closes the third refresh path: Hermes cron, manual/operator demand import, and
admin refresh now all leave the same current-run demand work order before
running demand intake, attaching summaries, building work queues, writing the
operator handoff, exporting the data-plane manifest, or publishing.

Package preflight refresh-path parity slice: `scripts/verify_hermes_package_contract.py`
now verifies that both `scripts/import_demand_and_refresh.py` and
`src/cios/admin/dashboard_refresh.py` contain the demand-plan template export
hook and produce `argus-demand-plan-template.csv`. The deployed package can no
longer pass preflight if Hermes cron is correct but the manual fast lane or
admin refresh silently regresses and stops emitting the current-run demand work
order.

Demand work-order manifest slice: the Hermes-facing
`argus-data-plane-manifest.json` now carries `artifact_refs.demand_plan_template`
and an `audience_demand.details.demand_plan_template` summary for
`argus-demand-plan-template.csv`. The public-safe latest-run status exposes the
same work order as filename/status/format only, stripping internal paths. Hermes
cron, manual demand refresh, and admin refresh all pass the demand-plan template
artifact into the manifest export, and package preflight now rejects a daily
wrapper that omits `--demand-plan-template`.

Demand work-order operator-handoff slice: the Argus operator handoff now accepts
`--demand-plan-template`, records `artifact_refs.demand_plan_template`, and
publishes a public-safe `demand_plan_template` summary with status, format, and
filename only. Hermes cron, manual demand refresh, and admin refresh all pass the
current-run `argus-demand-plan-template.csv` into the handoff builder before the
handoff is attached to the dashboard or consumed by the data-plane manifest.
Package preflight now rejects a deployed CI-OS package whose handoff builder no
longer accepts or summarizes the demand work order.

Demand-source contract work-order slice: the inward-demand source contract now
carries a compact, public-safe `demand_plan` summary derived from the same Argus
collection plan that powers the demand-plan template. Hermes can now see not
only whether manual Looker or GA4 demand sources are ready, but which
Argus-prioritized topics those sources need to collect, the source dashboard
field, coverage status, top topics, related competitors, suggested filter
terms, evidence URL counts, and the current CSV work-order filename. The demand
source gate also promotes this into `readiness_summary` so cron/admin checks can
report the collection work order without opening the full readiness artifact.

GA4 demand-plan execution slice: GA4 export now accepts the current Argus demand
plan, tags matching analytics rows with Argus capability, assessment, filter,
competitor, rationale, and evidence metadata, writes an `argus_demand_plan`
coverage summary, and the Hermes demand-intake coordinator passes readiness
`demand_collection_plan` into GA4 export. The importer now preserves JSON-list
Argus metadata from GA4 exports as clean lists, so demand signals can carry the
plan context into the product-market ledger. Package preflight now rejects a
deployment where GA4 export drops `--demand-plan`/coverage summary or intake
stops handing the plan to GA4.

Product-surface row-truth slice: product-surface execution now distinguishes
command success from product proof. `scripts/execute_product_surface_plan.py`
counts extracted product rows, marks empty Scout outputs separately, reports
`product_plane_status`, aggregates row counts by company and surface family,
and only promotes non-empty Scout artifacts into `scout_paths`. The daily
product-market chain now carries `product_surface_execution_summary` and stops
before payload/synthesis when all product-surface outputs are empty, preserving
the blocked `skipped_no_product_surface_outputs` truth instead of pretending
that an empty JSON file is product muscle. Package preflight now rejects a
deployment where the executor stops reporting row counts, empty outputs, or
product-plane status.

Verification: RED tests first failed on missing `empty`, `product_row_count`,
`product_plane_status`, daily execution-summary retention, and preflight
executor invariants. Local focused suite passed `162 passed`; local full passed
`1098 passed, 23 deselected, 1 warning`. Remote focused suite passed
`162 passed`, remote full passed
`1097 passed, 1 skipped, 23 deselected, 1 warning`, remote package contract
preflight passed, and a remote smoke confirmed
`product_plane_status=degraded`, `product_row_count=1`, `succeeded=1`,
`empty=1`, `scout_paths=1`, `empty_scout_paths=1`, and
`company_rows=Constructor:1`. Remote backup:
`/root/.hermes/backups/cios-product-surface-row-truth-20260712T182047Z.tgz`.

Product-surface truth manifest/status slice: the row-truth summary now
propagates beyond the daily runner into the admin run status, dashboard state,
Hermes-facing data-plane manifest, and public latest-run status. Dashboard
state schema is now v26 and exposes
`product_market_run.product_surface_execution_summary`. The product-reality
plane uses that summary as run truth: empty product-surface outputs become
`empty_product_surface_outputs`, failed extraction becomes
`failed_product_surface_execution`, degraded extraction remains visible as
`degraded_product_surface_outputs`, and extracted row counts are promoted into
the plane counts. Empty-output blockers now name the affected company/surface
family without leaking local `output_path`, `/tmp`, or `/root` paths into the
public-safe status artifact.

Verification: RED tests first failed because `ArgusRunStatus` and
`ProductMarketRunStatus` did not preserve
`product_surface_execution_summary`, the data-plane manifest still treated
empty product-surface outputs as configured product coverage, and public status
did not expose sanitized `product_surface_execution`. After implementation,
the targeted local regression passed `4 passed`, local affected suite passed
`82 passed`, local compile check passed, and local full passed
`1100 passed, 23 deselected, 1 warning`. Remote targeted regression passed
`4 passed`, remote affected suite passed `82 passed`, remote compile check
passed, remote full passed
`1099 passed, 1 skipped, 23 deselected, 1 warning`, and remote package
contract preflight passed. Remote smoke confirmed
`manifest_product_status=empty_product_surface_outputs`,
`manifest_next_action=Repair or replace empty product-surface targets: Coveo docs.`,
`public_product_status=empty_product_surface_outputs`,
`public_empty_outputs=Coveo`, and `path_leak=False`. Remote backup:
`/root/.hermes/backups/cios-product-surface-truth-manifest-status-20260712T183621Z.tgz`.

Product-surface execution operator-handoff slice: the Argus operator handoff
now reads `product_market_run.product_surface_execution_summary` from the
dashboard state before calculating readiness. If explicit evidence queues are
empty but the same run says product-surface execution produced no product proof,
the handoff no longer reports `ready_for_operator_review`. It synthesizes a
product-muscle blocker with `work_item_id=product-surface-execution:<status>`,
names the empty company/surface-family targets, points the operator to product
surface repair, and keeps internal `output_path`, `/tmp`, and `/root` details
out of the blocker. This closes the ordering gap where the later data-plane
manifest could block on product reality while the earlier operator handoff
still looked actionable.

Verification: RED regression first failed because an empty product-surface
execution summary still produced `ready_for_operator_review`. The targeted
local regression then passed `1 passed`, the local handoff suite passed
`12 passed`, the local affected operator/publish suite passed `93 passed`,
local compile passed, and local full passed
`1101 passed, 23 deselected, 1 warning`. Remote targeted regression passed
`1 passed`, remote affected suite passed `93 passed`, remote compile passed,
remote full passed `1100 passed, 1 skipped, 23 deselected, 1 warning`, and
remote package contract preflight passed. Remote smoke confirmed
`handoff_status=blocked_on_evidence`,
`handoff_next_action=Repair or replace empty product-surface targets: Coveo docs.`,
`handoff_blocker=product-surface-execution:empty`,
`handoff_empty_output=Coveo`, and `handoff_path_leak=False`. Remote backup:
`/root/.hermes/backups/cios-product-surface-handoff-blocker-20260712T184424Z.tgz`.

Empty product-surface repair slice: `scripts/run_product_surface_repair.py` now
treats `status=empty` product-surface execution rows as repairable
`empty_extraction` targets. Before this change, the repair control could retry
failed Scout commands, but could not act on the newer row-truth failure mode
where Scout completed and wrote an artifact with zero product rows. The repair
script now selects empty outputs by company, surface, or category, preserves
the existing retry path with higher timeout / JS settings, and reports
`no_matching_repairable_surface` when no failed or empty product-surface row
matches the operator's filter.

Verification: RED regression first failed because an empty successful export
returned code `2` and selected no repair target. After implementation, local
repair/admin targeted suite passed `10 passed, 1 warning`, local affected
product-surface suite passed `91 passed`, local compile passed, and local full
passed `1102 passed, 23 deselected, 1 warning`. Remote targeted regression
passed `1 passed`, remote affected suite passed `91 passed`, remote compile
passed, remote full passed `1101 passed, 1 skipped, 23 deselected, 1 warning`,
and remote package contract preflight passed. Remote smoke confirmed
`selected_count=1`, `selected_status=empty`, and
`selected_category=empty_extraction`. Remote backup:
`/root/.hermes/backups/cios-empty-product-surface-repair-20260712T184954Z.tgz`.

Zero-row repair gate slice: product-surface repair retries now require actual
product rows before they are promoted as successful Scout proof. A retry command
that exits `0` and creates an output file with zero rows is classified as
`status=empty`, increments the repair `empty` count, keeps `failed` reserved
for command/runtime failures, and does not add the output to `scout_paths`.
This prevents the admin repair-and-refresh flow from feeding a second empty
artifact back into Argus as if product reality had been repaired.

Verification: RED regression first failed because a zero-row repair retry
returned exit code `0` and was promoted as a successful `scout_paths` artifact.
After implementation, local repair suite passed `5 passed`, local affected
repair/operator suite passed `96 passed, 1 warning`, local compile passed, and
local full passed `1103 passed, 23 deselected, 1 warning`. Remote targeted
regression passed `1 passed`, remote affected suite passed
`96 passed, 1 warning`, remote compile passed, remote full passed
`1102 passed, 1 skipped, 23 deselected, 1 warning`, and remote package
contract preflight passed. Remote smoke confirmed `repair_status=failed`,
`repair_empty=1`, `repair_failed=0`, `repair_scout_paths=0`, and
`repair_result_status=empty`. Remote backup:
`/root/.hermes/backups/cios-zero-row-repair-gate-20260712T185525Z.tgz`.

Verification: RED tests first failed on the missing coverage function, missing
admin-control helper, JSON-list metadata corruption, and missing preflight
invariants. Local focused suite passed `69 passed`, local adjacent suite passed
`192 passed, 1 warning`, and local full passed
`1094 passed, 23 deselected, 1 warning`. Remote focused suite passed
`69 passed`, remote adjacent suite passed `192 passed, 1 warning`, remote full
passed `1093 passed, 1 skipped, 23 deselected, 1 warning`, remote package
contract preflight passed, and a remote smoke confirmed
`matched_capability=ai assistant`, `plan_status=partial_coverage`,
`matched_plan_topic_count=1`, `off_plan_record_count=1`, and `path_leak=False`.
Remote backup:
`/root/.hermes/backups/cios-ga4-demand-plan-aware-export-20260712T180903Z.tgz`.

Verification: RED tests first failed for missing operator-handoff demand-plan
template input, summary preservation, wrapper/admin/manual propagation, and
preflight enforcement. Local affected suite passed `85` tests, local full passed
`1086 passed, 23 deselected, 1 warning`, remote affected suite passed `85`
tests, remote full passed `1085 passed, 1 skipped, 23 deselected, 1 warning`,
and a remote non-publishing smoke generated
`generated|csv|argus-demand-plan-template.csv` in the operator handoff with no
path leakage in the public-safe summary. Remote backup:
`/root/.hermes/backups/cios-operator-handoff-demand-plan-template-20260712T173831Z.tgz`.

Verification: RED tests first failed on the missing `demand_plan` contract
input/field and missing gate summary fields. Local focused suite passed
`15 passed`, adjacent artifact suite passed `110 passed, 1 warning`, and local
full passed `1088 passed, 23 deselected, 1 warning`. Remote focused suite passed
`15 passed`, remote adjacent suite passed `110 passed, 1 warning`, remote full
passed `1087 passed, 1 skipped, 23 deselected, 1 warning`, and a remote smoke
confirmed `contract_plan_status=needs_demand_source`,
`contract_top_topic=ai assistant`, `gate_plan_status=needs_demand_source`, and
`plan_path_leak=False`. Remote backup:
`/root/.hermes/backups/cios-demand-source-contract-plan-link-20260712T175228Z.tgz`.

Verification: RED tests first failed for missing manifest/status demand-plan
artifact exposure. Local affected suite passed `84` tests, local full passed
`1082 passed, 23 deselected, 1 warning`, remote affected suite passed `84`
tests, remote full passed `1081 passed, 1 skipped, 23 deselected, 1 warning`,
and a remote non-publishing smoke generated manifest/status payloads with
`generated|csv|argus-demand-plan-template.csv` and no public `/root/` or `/tmp/`
path leakage. Remote backup:
`/root/.hermes/backups/cios-demand-work-order-manifest-20260712T172508Z.tgz`.

Previous verified slice: `ProductMarketIntelligenceBrief` now carries a durable
`demand_recommendation_trace`. CI-OS links rising inward-demand rows to the
patterns, recommendation actions, scorecard dimensions, source files, row
numbers, and evidence URLs that used them. Manual demand imports also surface
that trace in `argus_read`, so Hermes/Argus can answer "why did this demand
change the recommendation?" after a refresh instead of only reporting that a
refresh succeeded.

Previous verified slice: Hermes/admin refresh now records every demand-intake
attempt, including blocked no-source attempts, under the durable
`work_root/{tenant}/demand-intake-runs/{timestamp}/demand-intake-summary.json`
history. The admin history reader now sorts mixed ISO `generated_at` values and
compact run-id timestamps by parsed UTC time, so the "latest" demand-intake run
matches the public data-plane manifest instead of drifting to an older compact
run id. Live production still correctly blocks the audience-demand plane until a
real GA4/Looker export or connector is supplied.

Latest slice: the Hermes-facing Argus data-plane manifest now consumes the
Argus demand-intake artifact. This lets the manifest show whether Hermes/Argus
actually attempted the inward-demand repair path, what the attempt returned,
and whether demand is still blocking action. A blocked no-source attempt stays
compact and does not pretend there were zero imported rows; successful intake
can promote the demand plane to `processed` using the persisted demand-import
counts and Argus replay insight.

Follow-up live-wrapper slice: the Hermes daily wrapper now runs
`scripts/run_argus_demand_intake.py` on both successful and blocked daily-run
paths, requires `out/argus-demand-intake.json` from the current run, and passes
that artifact into `scripts/export_argus_data_plane_manifest.py`. The package
preflight contract now rejects wrappers that omit the demand-intake coordinator
or the `--demand-intake` manifest input. The manifest also treats failed or
queued demand-intake states with no demand signals as action blockers instead
of silently inheriting a non-blocking readiness status.

Latest actionability slice: the data-plane manifest now carries sanitized
operator commands for the blocked demand plane. It preserves useful action
labels, surfaces, methods, and route kinds, but strips raw admin/API hrefs from
the public-safe manifest payload. Demand blockers now carry those commands too,
so Argus can say what the operator should do next instead of only naming the
missing inward-demand plane.

Follow-up cockpit actionability slice: the Argus operator handoff now consumes
`argus-demand-readiness.json`, carries the same public-safe demand operator
command summaries as the data-plane manifest, and the cockpit renders those
commands as operator choices without exposing raw admin/API hrefs. The Hermes
wrapper passes `--demand-readiness` into `scripts/build_argus_operator_handoff.py`
on both successful and blocked daily-run paths.

Manual/operator demand fast-lane parity slice: `scripts/import_demand_and_refresh.py`
now writes `out/argus-demand-intake.json` after a manual or queued demand import,
passes `--demand-readiness` into `scripts/build_argus_operator_handoff.py`, and
passes `--demand-intake` into `scripts/export_argus_data_plane_manifest.py`.
This keeps admin/operator refreshes aligned with the Hermes daily wrapper: the
operator handoff keeps demand repair commands, and the data-plane manifest can
prove the inward-demand plane was processed instead of silently falling back to
stale or missing demand truth.

Product-feature comparison intelligence slice: the feature matrix now has a
Hermes-facing product comparison read, not just admin plumbing. CI-OS fuses
product proof, competitor conversation, and rising inward demand into
capability rows that classify own product gaps, own narrative gaps, parity,
competitive pressure, demand without product proof, and conversation without
product proof. The runner embeds this read in `intelligence_brief` so persisted
run intelligence can answer where Algolia stands versus competitors and why
Argus is recommending action or withholding it.

Product-feature comparison dashboard surfacing slice: the persisted
`intelligence_brief.product_feature_comparison` read is now promoted into
`DashboardState.product_market_run.product_feature_comparison_read`, serialized
in public dashboard JSON, and rendered in the Hermes / Argus run trace as
`Product comparison read`. This makes the product-muscle judgment visible to
business users instead of hiding it in the backend run record.

Capability-hygiene slice: the product comparison read now filters obvious
non-feature market metadata (`product positioning`, `new content narrative`,
`new customer proof`, `academy`) and strips vendor/support scaffolding from
canonical capability keys. This reduces raw extraction clutter before Argus
compares product muscle.

Demand collection-plan slice: the inward-demand readiness artifact now turns
Argus's product-feature comparison read into a concrete demand collection plan.
When GA4/Looker demand is missing, Hermes gets ranked capability topics,
suggested page/title filters, related competitors, evidence URLs, required
template fields, and the manual drop folder. The same plan now flows into the
data-plane manifest under `planes.audience_demand.details` and into the Argus
operator handoff, so the next action is no longer a vague "upload demand" task.

Demand plan-coverage gate slice: the readiness artifact now scores imported
demand against the demand collection plan. It reports planned, covered,
missing, and off-plan topics, plus a coverage ratio. If demand rows exist but
only partially answer the Argus-prioritized topics, readiness becomes
`processed_partial_plan_coverage` and the data-plane manifest blocks action
instead of treating any demand row as sufficient evidence.

Demand plan-template slice: the admin demand template endpoint now supports a
plan-aware variant with `?planned=1`. The CSV keeps the normal GA/Looker import
columns but adds Argus topic, capability key, assessment, suggested filters,
related competitors, collection rationale, and evidence URLs. Admin also links
this template beside the generic blank template, and readiness operator actions
now offer `Download demand plan template` before the generic fallback.

Admin refresh sidecar parity slice: admin-triggered dashboard refresh now
rebuilds the same product-muscle work-queue sidecar as the Hermes daily wrapper
and demand fast lane before it can publish. The refreshed Argus operator
handoff receives `--product-muscle-queue`, and the data-plane manifest receives
`--product-muscle-work-queue`, so an admin refresh can no longer omit product
reality blockers while presenting the dashboard as current.

GA4 setup-checklist slice: the inward-demand readiness contract now carries a
public-safe `ga4_connector.setup_required` checklist. `missing_required` keeps
its narrower meaning of "GA4 is enabled but incomplete"; disabled GA4 now still
tells Hermes and the operator which setup keys are required before the demand
plane can run. The demand-source gate exposes the same checklist under
`readiness_summary.ga4_setup_required`.

Product-muscle relevance gate slice: the Hermes-facing product-reality work
queue no longer treats every active registry row as a product competitor.
Source/topic buckets with no domain, category, product surfaces, product
events, or feature evidence are skipped from product-muscle blockers, while
category-backed competitors and domain-only admin-added competitors still get
surface tasks. This removes false blockers such as CMSWire, Gartner MQ,
Community, and Martech Edge from the operator handoff without hiding real
product extraction gaps.

Demand plan-gap blocker slice: the Hermes-facing data-plane manifest now turns
partial/off-plan demand coverage into an operator-usable blocker. When the
demand-readiness plan coverage includes missing planned topics or off-plan
imported topics, `planes.audience_demand` still blocks action, but the blocker
now names the missing topics, carries the off-plan topics, and tells Hermes to
collect demand for those planned topics instead of showing a generic "Demand
plane missing" message.

Admin refresh demand-intake parity slice: admin-triggered dashboard refresh now
runs `scripts/run_argus_demand_intake.py`, requires the current
`argus-demand-intake.json` sidecar, tolerates structured blocked no-source
results, and passes `--demand-intake` into
`scripts/export_argus_data_plane_manifest.py`. This prevents an admin refresh
from overwriting the public manifest with a state that has lost Hermes's latest
inward-demand execution proof.

Demand-intake history recording slice: the Hermes-callable
`scripts/run_argus_demand_intake.py` coordinator now supports
`--record-history`. When enabled, the same current-run sidecar is also written
to `work_root/{tenant}/demand-intake-runs/{timestamp}/demand-intake-summary.json`
with `generated_at`, `summary_path`, and `run_output_dir`. The Hermes daily
wrapper and admin dashboard refresh both pass this flag, so blocked no-source
attempts become durable history instead of disposable output JSON.

## Progress

- Added `02-muscle-brain-architecture.md` as the concrete operating contract for the Argus brain and muscle:
  - product reality plane
  - market conversation plane
  - tenant demand plane
  - registry and coverage plane
  - operator learning plane
  - Hermes versus CI-OS ownership boundary
  - required run-stage ledger
  - acceptance test for real intelligence
- Implemented the first runtime stage-ledger slice:
  - `scripts/daily_production_run.py` now records a structured `stage_ledger` for every product-market stage already emitted as a `CIOS_PRODUCT_MARKET_STAGE` heartbeat.
  - Stage entries include tenant, stage, status, started timestamp, ended timestamp, elapsed seconds, and failure detail when a stage fails.
  - Failed product-market stages return a failed summary with the ledger so the trace is not lost.
  - `ProductMarketRunStatus` now exposes `stage_ledger`.
  - Dashboard state schema is now v19.
- Promoted the product-market stage ledger from summary JSON into durable Postgres state:
  - Added `run_stage_ledgers` parent rows and `run_stage_events` ordered child rows to the tenant-scoped schema.
  - Added RLS coverage for both tables.
  - Added product-market repository methods to save a stage ledger and read the latest saved ledger.
  - Updated the product-market schema patch script so existing deployments can receive the new tables.
  - The daily runner now persists the product-market stage ledger and records `stage_ledger_id` in `product_market_summary`.
- Added a coarse full daily-run ledger:
  - The tenant daily pass now persists a `cios.daily` ledger after dashboard-state persistence.
  - The daily ledger records registry resolution, source sweep, synthesis, quality review, false-negative audit, delivery, product-market chain, dashboard-state build, and publish-gate status.
  - The daily ledger metadata links to the product-market `stage_ledger_id` when that subchain ran.
  - This gives Hermes / Argus a durable run-level explanation, while keeping the product-market subtrace available for deeper inspection.
- Added the generic run-stage persistence primitive needed for a live run console:
  - Created `PgRunStageRepository` as the package-agnostic repository for CI-OS run ledgers.
  - Added `start_ledger`, `start_stage`, `finish_stage`, `finish_ledger`, and bulk `save_run_stage_ledger`.
  - Updated `run_stage_events` to allow `running` status, not only terminal statuses.
  - Switched the coarse `cios.daily` ledger to write through `PgRunStageRepository` instead of the product-market repository.
- Started making the daily run ledger live instead of post-facto only:
  - Added `DailyRunStageRecorder`.
  - Added `start_daily_run_stage_ledger(...)`.
  - `run_tenant(...)` now opens the `cios.daily` ledger immediately after creating `run_id`, before registry/source work starts.
  - If the run reaches the existing end-of-run ledger step, the running ledger is backfilled and finished instead of duplicating the daily ledger parent.
- Streamed the first real daily stages into the live ledger:
  - Added explicit `DailyRunStageRecorder.start_stage(...)` and `finish_stage(...)`.
  - Registry resolution now records live stage order `1`.
  - Source sweep now records live stage order `2`.
  - End-of-run backfill skips live-recorded stage orders so real live timings are not overwritten.
- Streamed the next decision stages into the live ledger:
  - Synthesis now records live stage order `3`.
  - Quality review now records live stage order `4`.
  - Synthesis metadata includes fact count, delta count, coverage state, synthesis target count, material signal count, verdict, and cold-start state.
  - Quality metadata includes pre-review signal count, quiet verdict, final quality status, required-fix count, and post-review signal count.
- Streamed the next execution stages into the live ledger:
  - Delivery now records live stage order `6`.
  - Product-market chain now records live stage order `7`.
  - Dashboard-state build now records live stage order `8`.
  - Delivery metadata includes report id, quality status, delivered flag, delivery count, and bot delivery outcomes.
  - Product-market metadata includes conversation record count, product-market status, product-market stage-ledger id, runner verdict, and error count.
  - Dashboard metadata includes dashboard artifact path, published delta count, delivery count, and dashboard-state presence.
- Streamed the delivered-tenant public publish gate into the live ledger:
  - Delivered tenant runs now defer stage order `9` from `run_tenant` so the daily ledger parent stays running until the actual public artifact gate.
  - `main()` now records `publish_gate` around the real cockpit, brief, JSON, and competitor-brief write.
  - Blocked publishes record the blocking reason and do not write public artifacts.
  - Successful publishes attach public artifact metadata to both the stage event and the final daily ledger metadata.
- Added explicit learning application instrumentation inside the product-market subledger:
  - `next_sweep_learning_plan` records approved-learning instruction generation.
  - `learning_apply_plan` records conversion into CI-OS package-scoped actions.
  - `learning_apply_execute` now runs `execute_learning_apply_plan.py` in proposal-only mode by default, records proposal/applied/skipped counts, and stays inside the CI-OS package boundary.
  - Automatic package mutation still requires explicit `CIOS_LEARNING_APPLY_APPROVED_BY`.
- Added backend market-movement map derivation from current and historical Argus product-market patterns.
- Embedded the map in `ProductMarketIntelligenceBrief`, which is persisted as run intelligence.
- Promoted the movement map to first-class `ProductMarketRunStatus` state.
- Rendered the movement summary in the Hermes / Argus run trace.
- Bumped the dashboard state schema from v11 to v12 for the new published contract field.
- Added a backend 7-day versus 30-day evidence-window comparison to `ProductMarketIntelligenceBrief`.
  - The comparison is derived from product event `observed_at`, conversation theme `observed_at`, and demand signal `period_end`.
  - It reports per-window product/conversation/demand counts, rising demand count, leading companies, hot capabilities, and evidence URLs.
  - It uses human evidence labels for capabilities while still relying on canonical capability keys internally.
  - This is the first durable answer to "what happened this week versus the broader month?"
- Extended the GA / Looker demand fast lane so a demand import + ledger refresh returns an `argus_read` summary with verdict, top insight, primary action, demand summary, conversion summary, and product/conversation/demand/pattern/recommendation counts. This gives operators a direct answer to "what did Argus learn after the inward demand plane arrived?" instead of only "refresh succeeded."
- Added the first durable demand-to-recommendation reasoning trace:
  - `intelligence_brief.demand_recommendation_trace` links rising demand topics to qualified patterns, recommendation actions, scorecard dimensions, source files, row numbers, and evidence URLs.
  - The trace uses canonical capability keys plus evidence URL overlap rather than UI-only labels.
  - Manual demand import refreshes now expose the same trace in `argus_read`, which lets Hermes/Argus explain why a refreshed inward-demand plane changed or did not change the recommendation.
- Added a public-safe latest-run status artifact for blocked publish gates:
  - `scripts/export_public_run_status.py` reduces the internal data-plane manifest into a path-redacted public contract.
  - Blocked wrapper runs now publish only `data/argus-latest-run-status.json` and `v2/data/argus-latest-run-status.json`; they do not overwrite `index.html`, `semantic-dashboard.json`, briefs, or competitor briefs.
  - Successful wrapper runs also stage the same status artifact as `published`, so the endpoint reflects the latest wrapper outcome.
  - The package contract now requires the script and wrapper hook.
- Added a `Latest ledger replay read` block to the local admin run console. It exposes the replay verdict, top insight, primary action, demand read, conversion diagnostics, blocker list, and product/conversation/demand/pattern/recommendation counts from `ledger_refresh_summary`.
- Added demand-intake artifact semantics to `scripts/export_argus_data_plane_manifest.py`.
  - The manifest accepts `--demand-intake`.
  - `artifact_refs.demand_intake` points to the intake sidecar.
  - `planes.audience_demand.details.demand_intake` records status, command status, exit code, mode, next Hermes action, summary path, and import counts only when those nested artifacts exist.
  - A successful intake with persisted demand rows upgrades the audience-demand plane to `processed` even if the dashboard run payload is stale.
  - A blocked no-source intake remains `blocked_missing_demand_source` and keeps the action blocker intact.

## Constraints

- CI-OS remains an extension package. Hermes core is not modified.
- Every intelligence claim carries evidence.
- The UI must read generated state, not invent semantic meaning.
- This slice is backend-first and test-first.

## Verification Update

- Public latest-run status validation on 2026-07-12:
  - RED focused tests before implementation:
    `.venv/bin/python -m pytest tests/scripts/test_export_public_run_status.py -q`
    -> `2 failed` because `scripts/export_public_run_status.py` did not exist.
    `.venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_writes_demand_source_gate_when_daily_blocks_publish -q`
    -> `1 failed` because the wrapper never wrote `public-run-status`.
  - Focused local after implementation:
    `.venv/bin/python -m pytest tests/scripts/test_export_public_run_status.py -q`
    -> `2 passed`.
    `.venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_writes_demand_source_gate_when_daily_blocks_publish -q`
    -> `1 passed`.
  - Affected local:
    `bash -n deploy/cios-daily.sh`
    -> pass.
    `.venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py -q`
    -> `15 passed`.
    `.venv/bin/python -m pytest tests/scripts/test_export_public_run_status.py tests/scripts/test_export_argus_data_plane_manifest.py tests/scripts/test_verify_hermes_package_contract.py -q`
    -> `40 passed`.
    `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-test-deps`
    -> `PASS: CI-OS Hermes package contract satisfied`.
  - Full local:
    `.venv/bin/python -m pytest -q`
    -> `1066 passed, 23 deselected, 1 warning`.
  - Remote deploy backup:
    `/root/.hermes/backups/cios-public-run-status-20260712T145400Z.tgz`.
  - Remote focused:
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/scripts/test_export_public_run_status.py tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_writes_demand_source_gate_when_daily_blocks_publish -q`
    -> `3 passed`.
    `bash -n deploy/cios-daily.sh`
    -> pass.
    `PYTHONPATH=src:. .venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-test-deps`
    -> `PASS: CI-OS Hermes package contract satisfied`.
  - Remote affected:
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/deploy/test_cios_daily_wrapper.py -q`
    -> `15 passed`.
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/scripts/test_export_public_run_status.py tests/scripts/test_export_argus_data_plane_manifest.py tests/scripts/test_verify_hermes_package_contract.py -q`
    -> `40 passed`.
  - Remote full:
    `PYTHONPATH=src:. .venv/bin/python -m pytest -q`
    -> `1065 passed, 1 skipped, 23 deselected, 1 warning`.
  - Hermes wrapper / live gate:
    `./deploy/cios-daily.sh` with `CIOS_APP_DIR=/root/.hermes/apps/cios`,
    `CIOS_OUTPUT_DIR=/root/.hermes/apps/cios/out`, and
    `CIOS_PUBLIC_DIR=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public`
    attempted 48 active sources, fetched 42, failed 6, produced 461 facts and
    461 deltas, ran the product-market chain, and exited `2` because the
    inward-demand source is still missing. The wrapper published
    `data/argus-latest-run-status.json` and `v2/data/argus-latest-run-status.json`
    but did not update the main public dashboard.
  - Live public status:
    `https://ci.chowmes.com/data/argus-latest-run-status.json`
    returned `publish_status=blocked`, `status=blocked_on_evidence`,
    `public_dashboard_updated=False`,
    `manifest_generated_at=2026-07-12T15:02:06.925098Z`,
    `audience_demand.status=blocked_missing_demand_source`, and no `/root/` or
    `/tmp/` path leakage.
  - Live dashboard click validation:
    `.venv/bin/python scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/`
    -> `PASS dashboard_click_validation`.
- Demand-to-recommendation trace validation on 2026-07-12:
  - RED focused tests before implementation:
    `.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_traces_demand_into_recommendation tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_surfaces_refreshed_argus_read -q`
    -> `2 failed`, proving the brief had no trace field and the import handoff discarded the trace.
  - Focused local after implementation:
    `.venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_traces_demand_into_recommendation tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_surfaces_refreshed_argus_read -q`
    -> `2 passed`.
  - Affected local:
    `.venv/bin/python -m pytest tests/intelligence/test_runner.py -q`
    -> `16 passed`.
    `.venv/bin/python -m pytest tests/scripts/test_import_demand_and_refresh.py -q`
    -> `14 passed`.
    `.venv/bin/python -m pytest tests/intelligence/test_product_market_synthesizer.py tests/integration/test_demand_to_dashboard_flow.py -q`
    -> `9 passed, 2 deselected`.
  - Full local:
    `.venv/bin/python -m pytest -q`
    -> `1064 passed, 23 deselected, 1 warning`.
  - Local package contract:
    `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-test-deps`
    -> `PASS: CI-OS Hermes package contract satisfied`.
  - Remote focused after deploy:
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_traces_demand_into_recommendation tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_surfaces_refreshed_argus_read -q`
    -> `2 passed`.
  - Remote affected:
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/intelligence/test_runner.py -q`
    -> `16 passed`.
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/scripts/test_import_demand_and_refresh.py -q`
    -> `14 passed`.
    `PYTHONPATH=src:. .venv/bin/python -m pytest tests/intelligence/test_product_market_synthesizer.py tests/integration/test_demand_to_dashboard_flow.py -q`
    -> `9 passed, 2 deselected`.
  - Remote full:
    `PYTHONPATH=src:. .venv/bin/python -m pytest -q`
    -> `1063 passed, 1 skipped, 23 deselected, 1 warning`.
  - Remote package contract:
    `PYTHONPATH=src:. .venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-test-deps`
    -> `PASS: CI-OS Hermes package contract satisfied`.
  - Remote trace drill:
    synthetic ledger replay returned `status=linked_to_recommendations`,
    `demand_signal_count=1`, `matched_demand_topic_count=1`,
    `recommendation_count=1`, topic `agentic product discovery`, canonical
    key `shopping agent`, scorecard dimensions
    `audience_demand,evidence_breadth`, and the PMM narrative action.
  - Hermes wrapper / live publish gate:
    `./deploy/cios-daily.sh` with `CIOS_APP_DIR=/root/.hermes/apps/cios`,
    `CIOS_OUTPUT_DIR=/root/.hermes/apps/cios/out`, and
    `CIOS_PUBLIC_DIR=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public`
    attempted 48 active sources, fetched 42, failed 6, produced 461 facts and
    461 deltas, ran the product-market chain, then exited `2` because the
    demand plane had no ready source and no ledger demand signals. The wrapper
    generated current out artifacts at `2026-07-12T14:44:19Z` but correctly did
    not publish them.
  - Live public validation:
    local click suite against `https://ci.chowmes.com/` passed structure, nav
    targets, timeline, semantic layer, priority selection, Constructor/Elastic/
    Algonomy brief routing, appendices, and 390/768/1280 viewports.
    Live JSON remains the previous public artifact with
    `argus-data-plane-manifest.generated_at=2026-07-12T14:17:24.965900Z`,
    `audience_demand.status=blocked_missing_demand_source`,
    `audience_demand.blocks_action=True`, and
    `semantic-dashboard.product_market_status=ran`,
    `semantic-dashboard.demand_signal_count=0`.
  - Remote backup:
    `/root/.hermes/backups/cios-demand-recommendation-trace-20260712T142905Z.tgz`.
- Demand-intake history recording validation on 2026-07-12:
  - RED focused script contract before implementation:
    `.venv/bin/python -m pytest tests/scripts/test_run_argus_demand_intake.py::test_run_argus_demand_intake_main_records_history_copy_for_blocked_attempt -q`
    -> failed because `--record-history` was not a recognized argument.
  - Focused local after implementation:
    `.venv/bin/python -m pytest tests/scripts/test_run_argus_demand_intake.py::test_run_argus_demand_intake_main_records_history_copy_for_blocked_attempt tests/admin/test_dashboard_refresh.py::test_admin_dashboard_refresh_runner_rerenders_and_publishes tests/deploy/test_cios_daily_wrapper.py::test_hermes_wrapper_executes_product_muscle_gap_discovery_before_publish tests/scripts/test_verify_hermes_package_contract.py -q`
    -> `31 passed`.
  - Affected local demand/admin/deploy/manifest suite:
    `.venv/bin/python -m pytest tests/scripts/test_run_argus_demand_intake.py tests/admin/test_demand_intake.py tests/admin/test_dashboard_refresh.py tests/admin/test_app.py tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_export_argus_data_plane_manifest.py -q`
    -> `142 passed, 1 warning`.
- Admin refresh demand-intake parity validation on 2026-07-12:
  - RED admin refresh suite before implementation:
    `.venv/bin/python -m pytest tests/admin/test_dashboard_refresh.py -q`
    -> `2 failed, 3 passed`; failures proved admin refresh had no
    `demand_intake` sidecar and did not block when the demand-intake artifact
    was missing.
  - Focused local after implementation:
    `.venv/bin/python -m pytest tests/admin/test_dashboard_refresh.py -q`
    -> `5 passed`.
  - Affected local admin/app/manifest suite:
    `.venv/bin/python -m pytest tests/admin/test_dashboard_refresh.py tests/admin/test_app.py tests/scripts/test_export_argus_data_plane_manifest.py tests/scripts/test_run_argus_demand_intake.py -q`
    -> `96 passed, 1 warning`.
  - Full local suite:
    `.venv/bin/python -m pytest -q`
    -> `1059 passed, 23 deselected, 1 warning`.
  - Deployed exactly:
    `src/cios/admin/dashboard_refresh.py`,
    `tests/admin/test_dashboard_refresh.py`, and this status file to
    `/root/.hermes/apps/cios`; remote backup:
    `/root/.hermes/backups/cios-admin-refresh-demand-intake-20260712T133852Z.tgz`.
  - Remote focused admin refresh suite:
    `5 passed`.
  - Remote affected admin/app/manifest suite:
    `96 passed, 1 warning`.
  - Remote full suite:
    `1058 passed, 1 skipped, 23 deselected, 1 warning`.
  - Remote package contract:
    `PASS: CI-OS Hermes package contract satisfied`.
  - Production admin refresh/publish:
    `status=published`, publish `published`, sidecars returned
    `demand_readiness=0`, `demand_intake=2`, `evidence_work_queue=0`,
    `product_muscle_work_queue=0`, `operator_handoff=0`,
    `attach_operator_handoff=0`, and `data_plane_manifest=0`.
  - Live public manifest after refresh:
    `manifest_status=blocked_on_evidence`,
    `manifest_generated_at=2026-07-12T13:40:24.159088Z`,
    `audience_demand_status=blocked_missing_demand_source`,
    `demand_intake_status=blocked_missing_demand_source`,
    `demand_intake_exit_code=2`,
    `demand_intake_mode=blocked`,
    `demand_intake_next_action=configure_ga4_or_upload_demand_export`.
  - Production click validation against `https://ci.chowmes.com/`:
    `PASS dashboard_click_validation`.
- Demand plan-gap blocker validation on 2026-07-12:
  - RED focused contract before implementation:
    `.venv/bin/python -m pytest tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_blocker_names_missing_and_off_plan_demand_topics -q`
    -> failed because the blocker title was still `Demand plane missing`.
  - Focused local after implementation:
    `.venv/bin/python -m pytest tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_blocker_names_missing_and_off_plan_demand_topics -q`
    -> `1 passed`.
  - Affected local manifest/readiness/operator suite:
    `.venv/bin/python -m pytest tests/scripts/test_export_argus_data_plane_manifest.py tests/scripts/test_export_argus_demand_readiness.py tests/scripts/test_build_argus_operator_handoff.py -q`
    -> `25 passed`.
  - Full local suite:
    `.venv/bin/python -m pytest -q`
    -> `1058 passed, 23 deselected, 1 warning`.
  - Deployed exactly:
    `scripts/export_argus_data_plane_manifest.py`,
    `tests/scripts/test_export_argus_data_plane_manifest.py`, and this status
    file to `/root/.hermes/apps/cios`; remote backup:
    `/root/.hermes/backups/cios-demand-plan-gap-blocker-20260712T132845Z.tgz`.
  - Remote focused regression:
    `1 passed`.
  - Remote affected manifest/readiness/operator suite:
    `25 passed`.
  - Remote full suite:
    `1057 passed, 1 skipped, 23 deselected, 1 warning`.
  - Remote package contract:
    `PASS: CI-OS Hermes package contract satisfied`.
  - Admin refresh/publish:
    `status=published`, publish `published`, and sidecars
    `demand_readiness`, `evidence_work_queue`, `product_muscle_work_queue`,
    `operator_handoff`, `attach_operator_handoff`, and `data_plane_manifest`
    all returned `0`.
  - Production click validation against `https://ci.chowmes.com/`:
    `PASS dashboard_click_validation`.
  - Live public manifest after refresh:
    `manifest_status=blocked_on_evidence`,
    `manifest_generated_at=2026-07-12T13:31:40.448708Z`,
    `audience_demand_status=blocked_missing_demand_source`,
    `audience_demand_blocks_action=True`,
    `next_hermes_action=configure_ga4_or_upload_demand_export`.
    This proves the live site is honestly blocked on missing inward demand
    rather than inventing confidence. The new missing/off-plan topic blocker is
    covered by the regression test and will appear when imported demand only
    partially covers the Argus demand plan.
- Local focused admin brain-trace test: 1 passed.
- Local admin/demand/daily/importer path tests: 139 passed.
- Local full suite: 875 passed, 21 deselected.
- Remote focused admin brain-trace test: 1 passed, 1 warning.
- Remote admin/demand/daily/importer path tests: 139 passed, 1 warning.
- Remote full suite: 868 passed, 1 skipped, 21 deselected, 1 warning.
- Demand-intake manifest focused local suite: `5 passed`.
- Demand-intake manifest affected local suite: `53 passed`.
- Demand-intake manifest full local suite: `1019 passed, 22 deselected, 1 warning`.
- Demand-intake manifest affected remote suite: `53 passed`.
- Demand-intake manifest full remote suite: `1018 passed, 1 skipped, 22 deselected, 1 warning`.
- Remote package contract after demand-intake manifest slice:
  `PASS: CI-OS Hermes package contract satisfied`.
- Live manifest smoke using the latest production demand-intake attempt:
  `manifest_status=blocked_on_evidence`,
  `demand_status=blocked_missing_demand_source`,
  `demand_intake_status=blocked_missing_demand_source`,
  `demand_intake_zero_noise_keys=`. This proves the manifest records the
  attempt without inventing zero-row import evidence.
- Demand-intake wrapper contract local validation:
  `bash -n deploy/cios-daily.sh` -> pass;
  `.venv/bin/pytest tests/deploy/test_cios_daily_wrapper.py tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_export_argus_data_plane_manifest.py -q`
  -> `49 passed`;
  `.venv/bin/pytest -q` -> `1020 passed, 22 deselected, 1 warning`;
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir . --require-scout --scout-bin scripts/scout_http_shim`
  -> `PASS`.
- Demand-intake wrapper contract remote validation after deployment to
  `/root/.hermes/apps/cios` and `/root/.hermes/scripts/cios-daily.sh`:
  focused suite -> `49 passed`;
  remote full suite -> `1019 passed, 1 skipped, 22 deselected, 1 warning`;
  remote package contract -> `PASS`.
- Admin refresh sidecar parity validation on 2026-07-12:
  - RED local contract before implementation:
    `tests/admin/test_dashboard_refresh.py` -> `2 failed, 2 passed`; failures
    proved the missing `product_muscle_work_queue` sidecar and missing publish
    block on its failure.
  - Focused local after implementation:
    `.venv/bin/python -m pytest tests/admin/test_dashboard_refresh.py -q`
    -> `4 passed`.
  - Affected local artifact/wrapper suite:
    `.venv/bin/python -m pytest tests/admin/test_dashboard_refresh.py tests/scripts/test_import_demand_and_refresh.py tests/scripts/test_export_argus_data_plane_manifest.py tests/deploy/test_cios_daily_wrapper.py -q`
    -> `37 passed`.
  - Full local suite after implementation:
    `.venv/bin/python -m pytest -q`
    -> `1043 passed, 23 deselected, 1 warning`.
  - Deployed exactly:
    `src/cios/admin/dashboard_refresh.py` and
    `tests/admin/test_dashboard_refresh.py` to `/root/.hermes/apps/cios`;
    remote backup:
    `/root/.hermes/backups/cios-admin-refresh-product-muscle-20260712T114905Z.tgz`.
  - Remote focused artifact/wrapper suite:
    `37 passed`.
  - Remote full suite after deployment:
    `1042 passed, 1 skipped, 23 deselected, 1 warning`.
  - Remote package contract:
    `PASS: CI-OS Hermes package contract satisfied`.
  - Restarted `cios-admin.service`; service returned `active`.
  - Remote no-public-publish refresh with `/root/.hermes/cios-env` loaded:
    `status=rerendered`,
    sidecars included `product_muscle_work_queue`,
    `out_schema=24`,
    `out_manifest_status=blocked_on_evidence`,
    `out_product_reality_status=blocked_missing_product_surfaces`,
    `out_product_work_items=17`,
    `out_demand_status=blocked_missing_demand_source`,
    `out_blockers=13`.
  - Public publish was intentionally not run from this slice because inward
    demand evidence remains missing; publishing stays gated until the demand
    plane is backed by GA4/Looker evidence.
- GA4 setup-checklist validation on 2026-07-12:
  - RED focused local tests before implementation:
    `.venv/bin/python -m pytest tests/scripts/test_export_argus_demand_readiness.py::test_export_argus_demand_readiness_creates_manual_drop_folder tests/scripts/test_export_argus_demand_readiness.py::test_export_argus_demand_readiness_reports_missing_inward_contract_without_secrets tests/scripts/test_check_argus_demand_source_gate.py::test_gate_fails_when_no_manual_or_ga4_demand_source_is_ready -q`
    -> `3 failed`; failures proved `setup_required` was absent from readiness
    and gate output.
  - Focused local after implementation:
    same command -> `3 passed`.
  - Affected local demand/admin/wrapper suite:
    `.venv/bin/python -m pytest tests/scripts/test_export_argus_demand_readiness.py tests/scripts/test_check_argus_demand_source_gate.py tests/scripts/test_export_argus_data_plane_manifest.py tests/scripts/test_attach_post_run_summaries.py tests/admin/test_app.py tests/admin/test_demand_imports.py tests/deploy/test_cios_daily_wrapper.py -q`
    -> `119 passed, 1 warning`.
  - Full local suite:
    `.venv/bin/python -m pytest -q`
    -> `1043 passed, 23 deselected, 1 warning`.
  - Deployed exactly:
    `src/cios/admin/types.py`,
    `src/cios/admin/demand_imports.py`,
    `scripts/export_argus_demand_readiness.py`,
    `scripts/check_argus_demand_source_gate.py`,
    `tests/scripts/test_export_argus_demand_readiness.py`, and
    `tests/scripts/test_check_argus_demand_source_gate.py`.
    Remote backup:
    `/root/.hermes/backups/cios-ga4-setup-checklist-20260712T115857Z.tgz`.
  - Remote affected demand/admin/wrapper suite:
    `119 passed, 1 warning`.
  - Remote full suite:
    `1042 passed, 1 skipped, 23 deselected, 1 warning`.
  - Remote package contract:
    `PASS: CI-OS Hermes package contract satisfied`.
  - Restarted `cios-admin.service`; service returned `active`.
  - Remote no-public-publish refresh with `/root/.hermes/cios-env` loaded:
    `status=rerendered`,
    sidecars included `demand_readiness` and `data_plane_manifest`,
    `readiness_status=blocked_missing_demand_source`,
    `ga4_status=disabled`,
    `ga4_missing_required=[]`,
    `ga4_setup_required=['CIOS_GA4_EXPORT_ENABLED', 'CIOS_GA4_PROPERTY_ID', 'CIOS_GA4_CREDENTIALS_JSON or GOOGLE_APPLICATION_CREDENTIALS']`,
    `manifest_status=blocked_on_evidence`,
    `manifest_demand_status=blocked_missing_demand_source`, and
    manifest carried the same `ga4_setup_required` checklist.
  - Public publish was intentionally not run from this slice because no demand
    source or current demand rows exist yet.
- Product-muscle relevance-gate validation on 2026-07-12:
  - RED focused local tests before implementation:
    `.venv/bin/python -m pytest tests/admin/test_product_muscle_work_queue.py -q`
    -> `2 failed, 6 passed`; failures proved unclassified source buckets and
    media/publication categories were incorrectly becoming missing-surface
    blockers.
  - Focused local after implementation:
    same command -> `8 passed`.
  - Affected local suite:
    `.venv/bin/python -m pytest tests/admin/test_product_muscle_work_queue.py tests/scripts/test_export_argus_product_muscle_work_queue.py tests/scripts/test_build_argus_operator_handoff.py tests/scripts/test_export_argus_data_plane_manifest.py -q`
    -> `29 passed`.
  - Full local suite:
    `.venv/bin/python -m pytest -q`
    -> `1046 passed, 23 deselected, 1 warning`.
  - Deployed exactly:
    `src/cios/admin/product_muscle_work_queue.py` and
    `tests/admin/test_product_muscle_work_queue.py`.
    Remote backup:
    `/root/.hermes/backups/cios-product-muscle-relevance-20260712T120833Z.tgz`.
  - Remote affected suite:
    `29 passed`.
  - Remote full suite:
    `1045 passed, 1 skipped, 23 deselected, 1 warning`.
  - Remote package contract:
    `PASS: CI-OS Hermes package contract satisfied`.
  - Remote no-public-publish refresh with `/root/.hermes/cios-env` loaded:
    product-muscle queue changed from `work_item_count=17`,
    `blocking_count=12`, `limiting_count=5` to `work_item_count=5`,
    `blocking_count=0`, `limiting_count=5`.
    Remaining product-reality limits are Athos Commerce, Coveo, Searchspring,
    Meilisearch, and Typesense, all with product surfaces but no extracted
    feature evidence.
  - Data-plane manifest after refresh:
    `status=blocked_on_evidence`,
    `planes.product_reality.status=limited_by_product_surface_evidence`,
    `planes.audience_demand.status=blocked_missing_demand_source`,
    `blocker_count=1`, and the only action blocker is the demand plane.
  - Restarted `cios-admin.service`; service returned `active`.
  - Public publish was intentionally not run from this slice because no demand
    source or current demand rows exist yet.
- Live Hermes wrapper smoke on 2026-07-12:
  source sweep reported `active_sources=48 attempted=48 fetched=43 failed=5`;
  product-market run reported `product_event_count=500`;
  demand intake wrote `out/argus-demand-intake.json` with
  `status=blocked_missing_demand_source`, `exit_code=2`, and
  `next_hermes_action=configure_ga4_or_upload_demand_export`;
  manifest wrote `status=blocked_on_evidence`,
  `planes.audience_demand.status=blocked_missing_demand_source`, and
  `planes.audience_demand.blocks_action=True`.
- Demand operator-command manifest slice local validation:
  targeted RED failed on missing `operator_commands`; focused GREEN
  `.venv/bin/pytest tests/scripts/test_export_argus_data_plane_manifest.py -q`
  -> `7 passed`; affected local suite -> `50 passed`; full local suite ->
  `1021 passed, 22 deselected, 1 warning`.
- Demand operator-command manifest slice remote validation:
  affected remote suite -> `50 passed`; remote full suite ->
  `1020 passed, 1 skipped, 22 deselected, 1 warning`; package contract ->
  `PASS`.
- Live manifest regeneration after deployment:
  `operator_command_count=3`; commands are `Download demand template`,
  `Open demand admin`, and `Run GA4 export now`; `commands_have_href=False`;
  first blocker includes the sanitized operator commands.
- Demand operator-command cockpit slice local validation:
  targeted RED failed because `build_operator_handoff_payload(...)` rejected
  `demand_readiness` and the cockpit did not render `Open demand admin`;
  targeted GREEN -> `3 passed`; affected local suite ->
  `95 passed`; full local suite -> `1022 passed, 22 deselected, 1 warning`;
  package contract -> `PASS`.
- Demand operator-command cockpit slice remote validation:
  targeted remote suite -> `3 passed`; affected remote suite ->
  `95 passed`; full remote suite -> `1021 passed, 1 skipped, 22 deselected,
  1 warning`; package contract -> `PASS`.
- Remote regenerated artifact smoke:
  `operator_command_count=3`; rendered HTML contains `Download demand template`,
  `Open demand admin`, and `Run GA4 export now`; handoff command summaries have
  no `href`; rendered HTML does not contain the raw demand template API href,
  demand admin hash URL, or GA4 admin URL.
- Manual/operator demand fast-lane parity local validation:
  targeted RED failed because `build_argus_operator_handoff.py` was invoked
  without `--demand-readiness` and `out/argus-demand-intake.json` was missing;
  focused GREEN -> `9 passed`; affected local suite -> `71 passed`; Python
  compile -> pass; package contract ->
  `PASS: CI-OS Hermes package contract satisfied`; full local suite ->
  `1022 passed, 22 deselected, 1 warning`.
- Manual/operator demand fast-lane parity remote validation after deployment to
  `/root/.hermes/apps/cios`:
  focused remote suite -> `9 passed`; affected remote suite -> `71 passed`;
  remote package contract -> `PASS`; remote full suite ->
  `1021 passed, 1 skipped, 22 deselected, 1 warning`.
- Product-feature comparison intelligence local validation:
  targeted RED failed because `build_product_feature_comparison_read` did not
  exist; focused GREEN -> `20 passed`; affected local suite ->
  `244 passed, 1 deselected, 1 warning`; Python compile -> pass; full local
  suite -> `1026 passed, 22 deselected, 1 warning`.
- Product-feature comparison intelligence remote validation after deployment to
  `/root/.hermes/apps/cios`:
  focused remote suite -> `20 passed`; affected remote suite ->
  `244 passed, 1 deselected, 1 warning`; remote package contract -> `PASS`;
  remote full suite -> `1025 passed, 1 skipped, 22 deselected, 1 warning`.
- Product-feature comparison dashboard surfacing local validation:
  targeted RED failed because `ProductMarketRunStatus` did not expose
  `product_feature_comparison_read`, the publisher omitted that key, and the
  cockpit did not render `Product comparison read`;
  targeted GREEN ->
  `3 passed`; affected local suite ->
  `114 passed`; Python compile -> pass; full local suite ->
  `1027 passed, 22 deselected, 1 warning`.
- Product-feature comparison copy-quality repair:
  live ledger replay exposed the summary text `162 capabilitys compared`;
  targeted RED ->
  `tests/intelligence/test_feature_matrix.py::test_product_feature_comparison_summary_uses_capabilities_plural`
  failed on the expected typo; targeted GREEN -> `1 passed`; affected local
  suite -> `115 passed`; Python compile -> pass; full local suite ->
  `1028 passed, 22 deselected, 1 warning`.
- Product-feature comparison copy-quality repair remote validation after
  deployment to `/root/.hermes/apps/cios`:
  targeted remote regression -> `1 passed`; affected remote suite ->
  `115 passed`; remote package contract -> `PASS`; remote full suite ->
  `1027 passed, 1 skipped, 22 deselected, 1 warning`.
- Product-feature comparison stale-report repair:
  live ledger replay produced a fresh `intelligence_brief.product_feature_comparison`,
  but no-fetch dashboard rerender still preferred stale report metadata and
  hid the product comparison from the cockpit. Added a regression proving
  `DashboardStateBuilder` uses the latest persisted
  `product_market_run_intelligence` brain record when the saved report trace is
  stale. Targeted RED showed the stale top insight; targeted GREEN ->
  `1 passed`; affected local suite -> `122 passed`; Python compile -> pass;
  full local suite -> `1029 passed, 22 deselected, 1 warning`.
- Product-feature comparison stale-report repair remote validation after
  deployment to `/root/.hermes/apps/cios`:
  targeted remote regression -> `1 passed`; affected remote suite ->
  `122 passed`; remote package contract -> `PASS`; remote full suite ->
  `1028 passed, 1 skipped, 22 deselected, 1 warning`.
- Capability-hygiene local validation:
  targeted RED ->
  `tests/intelligence/test_capabilities.py` failed because non-feature metadata
  and vendor scaffolding still became capability keys; targeted GREEN ->
  `2 passed`; affected local suite -> `133 passed`; Python compile -> pass;
  full local suite -> `1031 passed, 22 deselected, 1 warning`.
- Capability-hygiene remote validation after deployment to
  `/root/.hermes/apps/cios`:
  targeted remote suite -> `2 passed`; affected remote suite -> `133 passed`;
  remote package contract -> `PASS`; remote full suite ->
  `1030 passed, 1 skipped, 22 deselected, 1 warning`.
- Product-feature comparison dashboard surfacing remote validation after
  deployment to `/root/.hermes/apps/cios`:
  focused remote suite -> `3 passed`; affected remote suite ->
  `114 passed`; remote package contract -> `PASS`; remote full suite ->
  `1026 passed, 1 skipped, 22 deselected, 1 warning`.
- Demand collection-plan local validation:
  targeted RED failed because `argus-demand-readiness.json` had no
  `demand_collection_plan`; manifest and handoff targeted REDs failed because
  neither carried that plan downstream. Focused GREEN:
  `tests/scripts/test_export_argus_demand_readiness.py` -> `5 passed`;
  `tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_carries_demand_collection_plan_into_audience_plane`
  -> `1 passed`;
  `tests/scripts/test_build_argus_operator_handoff.py::test_build_operator_handoff_includes_demand_collection_plan`
  -> `1 passed`; affected local suite ->
  `32 passed`; Python compile -> pass; full local suite ->
  `1034 passed, 22 deselected, 1 warning`.
- Demand collection-plan remote validation after deployment to
  `/root/.hermes/apps/cios`:
  affected remote suite -> `32 passed`; remote full suite ->
  `1033 passed, 1 skipped, 22 deselected, 1 warning`; remote package contract
  -> `PASS`.
- Demand collection-plan live artifact/public validation:
  regenerated `argus-demand-readiness.json`, attached readiness to
  `argus-dashboard.json`, rebuilt the operator handoff, rebuilt
  `argus-data-plane-manifest.json`, and published the staged artifacts to
  `ci.chowmes.com`. Live filesystem and public URL smoke both show
  `plan_status=needs_demand_source`, `plan_topic_count=12`, and
  `first_topic=AI Assistant` in the dashboard JSON and manifest. Public click
  validator against `https://ci.chowmes.com/` passed all sections, nav, brief
  routing, appendices, and 390/768/1280 viewport checks.
- Demand plan-coverage gate local validation:
  targeted RED failed because readiness had no `coverage` object; targeted
  GREEN proves partial coverage changes readiness to
  `processed_partial_plan_coverage` with `next_hermes_action=collect_missing_plan_demand`.
  A second targeted RED proved the data-plane manifest still treated demand
  rows as `processed`; targeted GREEN now blocks action on partial/off-plan
  demand coverage. Affected local suite -> `34 passed`; Python compile -> pass;
  full local suite -> `1036 passed, 22 deselected, 1 warning`.
- Demand plan-coverage gate remote/public validation after deployment to
  `/root/.hermes/apps/cios`:
  affected remote suite -> `34 passed`; remote package contract -> `PASS`;
  remote full suite -> `1035 passed, 1 skipped, 22 deselected, 1 warning`.
  Live artifact regeneration and publish show current truth:
  `readiness_status=blocked_missing_demand_source`,
  `plan_status=needs_demand_source`, `coverage_status=not_evaluated`,
  `coverage_ratio=0.0`, and `missing_topic_count=12`. Public URL smoke for
  `https://ci.chowmes.com/data/semantic-dashboard.json` and
  `/data/argus-data-plane-manifest.json` returned the same coverage state.
  Public dashboard click validator passed structure, nav targets, timeline,
  semantic layer, priority selection, brief routing, appendices, and
  390/768/1280 viewport checks.
- Demand plan-template local validation:
  targeted RED proved the existing admin template endpoint ignored the Argus
  manifest and only returned a generic blank template. Targeted GREEN validates
  `/api/tenants/algolia/argus/demand-imports/template?planned=1` returns
  Argus topic, capability key, suggested filters, related competitors, and
  rationale while preserving empty GA/Looker metric columns. Admin HTML now
  links both the generic and Argus demand-plan templates. Readiness operator
  actions now put `Download demand plan template` first for missing demand.
  Affected local suite -> `132 passed, 1 warning`; Python compile -> pass;
  package contract -> `PASS`; full local suite ->
  `1037 passed, 22 deselected, 1 warning`.
- Demand plan-template remote/public validation after deployment to
  `/root/.hermes/apps/cios`:
  targeted remote admin/readiness tests -> `9 passed, 1 warning`; remote
  package contract -> `PASS`; remote full suite ->
  `1036 passed, 1 skipped, 22 deselected, 1 warning`. Regenerated and
  published public artifacts now expose operator actions in this order:
  `Download demand plan template`, `Download demand template`, `Open demand admin`,
  `Run GA4 export now`. Restarted localhost-only `cios-admin.service` so the
  endpoint code is live; local smoke against
  `http://127.0.0.1:8765/api/tenants/algolia/argus/demand-imports/template?planned=1`
  returned `row_count=12`, first topic `AI Assistant`, and filters
  `AI Assistant | assistant`. Public dashboard click validator still passes.

## Latest Verification

- Stage ledger focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats tests/scripts/test_daily_run.py::test_product_market_stage_ledger_records_failed_stage tests/scripts/test_daily_run.py::test_product_market_chain_returns_failed_summary_with_stage_ledger tests/dashboard/test_state_builder.py::test_product_market_run_status_populated_from_latest_run_summary tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace tests/dashboard/test_publisher.py::test_to_json_dict_includes_schema_version_and_quiet_flag tests/dashboard/test_publisher.py::test_publish_to_file_writes_readable_json -q`
  failed because `stage_ledger` was missing, `_run_product_market_stage` did not accept `stage_ledger`, and schema version was still 18.
- Stage ledger focused GREEN:
  same command -> `7 passed`.
- Broader local validation:
  `.venv/bin/python -m pytest tests/dashboard/test_state_builder.py tests/dashboard/test_publisher.py tests/scripts/test_daily_run.py -q`
  -> `127 passed`.
- Product-market/dashboard validation:
  `.venv/bin/python -m pytest tests/dashboard tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py tests/scripts/test_product_market_runner.py tests/intelligence/test_runner.py -q`
  -> `218 passed`.
- Full local suite:
  `.venv/bin/python -m pytest -q`
  -> `880 passed, 21 deselected, 1 warning`.
- Syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py src/cios/dashboard/types.py src/cios/dashboard/state_builder.py`
  -> pass.
- Durable stage-ledger focused GREEN:
  `.venv/bin/python -m pytest tests/db/test_product_market_schema_contract.py tests/db/test_product_market_repo.py::test_save_run_stage_ledger_targets_parent_and_event_tables tests/db/test_product_market_repo.py::test_get_latest_run_stage_ledger_rehydrates_parent_and_events tests/scripts/test_daily_run.py::test_persist_product_market_stage_ledger_writes_through_repo tests/scripts/test_daily_run.py::test_persist_product_market_stage_ledger_skips_empty_summary -q`
  -> `12 passed`.
- Durable stage-ledger broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `112 passed`.
- Durable stage-ledger full local suite:
  `.venv/bin/python -m pytest -q`
  -> `885 passed, 21 deselected, 1 warning`.
- Durable stage-ledger syntax validation:
  `python3 -m py_compile src/cios/db/repos/product_market.py scripts/daily_production_run.py scripts/apply_product_market_schema.py`
  -> pass.
- Coarse daily ledger focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_daily_run_stage_ledger_from_result_captures_core_run_state tests/scripts/test_daily_run.py::test_persist_daily_run_stage_ledger_writes_coarse_run_truth -q`
  failed because `daily_run_stage_ledger_from_result` and `persist_daily_run_stage_ledger` did not exist.
- Coarse daily ledger focused GREEN:
  same command -> `2 passed`.
- Daily-run module validation after coarse daily ledger:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q`
  -> `75 passed`.
- Daily-run syntax validation after coarse daily ledger:
  `python3 -m py_compile scripts/daily_production_run.py`
  -> pass.
- Coarse daily ledger broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `114 passed`.
- Coarse daily ledger full local suite:
  `.venv/bin/python -m pytest -q`
  -> `887 passed, 21 deselected, 1 warning`.
- Run-stage streaming primitive focused RED:
  `.venv/bin/python -m pytest tests/db/test_run_stage_repo.py tests/db/test_product_market_schema_contract.py::test_run_stage_events_have_parent_and_status_contract -q`
  first failed because `cios.db.repos.run_stage` did not exist.
- Run-stage streaming primitive focused GREEN:
  same command -> `5 passed`.
- Generic run-stage daily wiring focused RED:
  `.venv/bin/python -m pytest tests/db/test_run_stage_repo.py::test_save_run_stage_ledger_bulk_inserts_parent_and_ordered_events tests/scripts/test_daily_run.py::test_persist_daily_run_stage_ledger_writes_coarse_run_truth -q`
  failed because `PgRunStageRepository.save_run_stage_ledger` did not exist and `daily_production_run.py` did not expose `PgRunStageRepository`.
- Generic run-stage daily wiring focused GREEN:
  same command -> `2 passed`.
- Run-stage/db/daily focused validation:
  `.venv/bin/python -m pytest tests/db/test_run_stage_repo.py tests/db/test_product_market_schema_contract.py tests/db/test_product_market_repo.py::test_save_run_stage_ledger_targets_parent_and_event_tables tests/db/test_product_market_repo.py::test_get_latest_run_stage_ledger_rehydrates_parent_and_events tests/scripts/test_daily_run.py::test_persist_daily_run_stage_ledger_writes_coarse_run_truth tests/scripts/test_daily_run.py::test_persist_product_market_stage_ledger_writes_through_repo -q`
  -> `17 passed`.
- Run-stage syntax validation:
  `python3 -m py_compile src/cios/db/repos/run_stage.py scripts/daily_production_run.py scripts/apply_product_market_schema.py`
  -> pass.
- Run-stage broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `119 passed`.
- Run-stage full local suite:
  `.venv/bin/python -m pytest -q`
  -> `892 passed, 21 deselected, 1 warning`.
- Run-stage package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.
- Daily run live-ledger focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_persist_daily_run_stage_ledger_finishes_existing_running_ledger tests/scripts/test_daily_run.py::test_daily_run_stage_recorder_starts_running_ledger tests/scripts/test_daily_run.py::test_daily_run_stage_recorder_records_success_and_failure -q`
  failed because `DailyRunStageRecorder` did not exist and existing-ledger persistence still duplicated the parent ledger.
- Daily run live-ledger focused GREEN:
  same command -> `3 passed`.
- Daily run start hook focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_start_daily_run_stage_ledger_sets_result_id tests/scripts/test_daily_run.py::test_run_tenant_starts_daily_stage_ledger_before_registry_work -q`
  failed because `start_daily_run_stage_ledger` did not exist and `run_tenant` did not call it.
- Daily run start hook focused GREEN:
  same command -> `2 passed`.
- Daily-run module after live-ledger start hook:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q`
  -> `80 passed`.
- Daily run live-ledger syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py src/cios/db/repos/run_stage.py`
  -> pass.
- Daily run live-ledger broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `124 passed`.
- Daily run live-ledger full local suite:
  `.venv/bin/python -m pytest -q`
  -> `897 passed, 21 deselected, 1 warning`.
- Daily run live-ledger package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.
- Live stage preservation focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_daily_run_stage_recorder_exposes_explicit_start_and_finish tests/scripts/test_daily_run.py::test_persist_daily_run_stage_ledger_does_not_overwrite_live_recorded_stages -q`
  failed because `DailyRunStageRecorder` had no explicit start/finish stage API and backfill still rewrote live-recorded stage orders.
- Live stage preservation focused GREEN:
  same command -> `2 passed`.
- Registry/source-sweep streaming focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_run_tenant_streams_registry_resolution_stage_around_registry_work tests/scripts/test_daily_run.py::test_run_tenant_streams_source_sweep_stage_around_collection_loop -q`
  failed because `run_tenant` did not yet stream those stages.
- Registry/source-sweep streaming focused GREEN plus daily-run module:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_run_tenant_streams_registry_resolution_stage_around_registry_work tests/scripts/test_daily_run.py::test_run_tenant_streams_source_sweep_stage_around_collection_loop tests/scripts/test_daily_run.py -q`
  -> `84 passed`.
- Registry/source-sweep streaming syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py src/cios/db/repos/run_stage.py`
  -> pass.
- Registry/source-sweep streaming broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `128 passed`.
- Registry/source-sweep streaming full local suite:
  `.venv/bin/python -m pytest -q`
  -> `901 passed, 21 deselected, 1 warning`.
- Registry/source-sweep streaming package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.
- Synthesis/quality streaming focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_run_tenant_streams_synthesis_stage_around_synthesis_work tests/scripts/test_daily_run.py::test_run_tenant_streams_quality_review_stage_around_quality_work -q`
  failed because those live stage calls did not exist.
- Synthesis/quality streaming focused GREEN plus daily-run module:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_run_tenant_streams_synthesis_stage_around_synthesis_work tests/scripts/test_daily_run.py::test_run_tenant_streams_quality_review_stage_around_quality_work tests/scripts/test_daily_run.py -q`
  -> `86 passed`.
- Synthesis/quality streaming syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py src/cios/db/repos/run_stage.py`
  -> pass.
- Synthesis/quality streaming broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `130 passed`.
- Synthesis/quality streaming full local suite:
  `.venv/bin/python -m pytest -q`
  -> `903 passed, 21 deselected, 1 warning`.
- Synthesis/quality streaming package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.
- Window comparison focused RED:
  `python3 -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_embeds_7_and_30_day_window_comparison -q`
  failed because `ProductMarketIntelligenceBrief` had no `window_comparison`.
- Focused GREEN:
  `python3 -m pytest tests/intelligence/test_runner.py::test_run_product_market_ledger_refresh_embeds_7_and_30_day_window_comparison -q`
  -> `1 passed`.
- Product-market/dashboard subset:
  `python3 -m pytest tests/intelligence/test_runner.py tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py tests/dashboard/test_publisher.py tests/scripts/test_product_market_dashboard_wiring.py tests/scripts/test_product_market_runner.py -q`
  -> `103 passed`.
- Dashboard suite: `124 passed`.
- Full local suite: `878 passed, 21 deselected`.
- Package contract: `PASS: CI-OS Hermes package contract satisfied`.
- Live execution-stage streaming focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_run_tenant_streams_delivery_stage_around_delivery_work tests/scripts/test_daily_run.py::test_run_tenant_streams_product_market_stage_around_product_market_work tests/scripts/test_daily_run.py::test_run_tenant_streams_dashboard_state_stage_around_dashboard_build -q`
  failed because delivery, product-market chain, and dashboard-state build did not stream live daily-stage events from `run_tenant`.
- Live execution-stage streaming focused GREEN:
  same command -> `3 passed`.
- Daily-run module after live execution-stage streaming:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q`
  -> `89 passed`.
- Live execution-stage streaming syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py src/cios/db/repos/run_stage.py`
  -> pass.
- Live execution-stage streaming broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `133 passed`.
- Live execution-stage streaming full local suite:
  `.venv/bin/python -m pytest -q`
  -> `906 passed, 21 deselected, 1 warning`.
- Live execution-stage streaming package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.
- Publish-gate streaming focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_persist_daily_run_stage_ledger_can_defer_publish_gate_without_finishing tests/scripts/test_daily_run.py::test_main_defers_publish_gate_until_public_artifact_publish tests/scripts/test_daily_run.py::test_record_daily_publish_gate_stage_writes_artifacts_and_finishes_ledger tests/scripts/test_daily_run.py::test_record_daily_publish_gate_stage_blocks_without_writing_artifacts -q`
  failed because `persist_daily_run_stage_ledger` could not defer stage order `9`, `main` did not defer the delivered tenant publish gate, and `record_daily_publish_gate_stage` did not exist.
- Publish-gate streaming focused GREEN:
  same command -> `4 passed`.
- Daily-run module after publish-gate streaming:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q`
  -> `93 passed`.
- Publish-gate streaming syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py src/cios/db/repos/run_stage.py`
  -> pass.
- Publish-gate streaming broader validation:
  `.venv/bin/python -m pytest tests/db tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `137 passed`.
- Publish-gate streaming full local suite:
  `.venv/bin/python -m pytest -q`
  -> `910 passed, 21 deselected, 1 warning`.
- Publish-gate streaming package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.
- Learning-apply execution focused RED:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py::test_product_market_chain_runs_plan_execute_payload_and_runner tests/scripts/test_daily_run.py::test_product_market_chain_emits_hermes_stage_heartbeats -q`
  failed because the product-market chain still jumped from `learning_apply_plan` to product-surface planning and did not expose `learning_apply_execution_path` or `learning_apply_execution_summary`.
- Learning-apply execution focused GREEN:
  same command -> `2 passed`.
- Daily-run module after learning-apply execution:
  `.venv/bin/python -m pytest tests/scripts/test_daily_run.py -q`
  -> `93 passed`.
- Learning-apply execution syntax validation:
  `python3 -m py_compile scripts/daily_production_run.py scripts/execute_learning_apply_plan.py src/cios/learn/apply.py src/cios/db/repos/run_stage.py`
  -> pass.
- Learning-apply execution broader validation:
  `.venv/bin/python -m pytest tests/db tests/learn tests/scripts/test_execute_learning_apply_plan.py tests/scripts/test_daily_run.py tests/scripts/test_product_market_dashboard_wiring.py -q`
  -> `177 passed`.
- Learning-apply execution full local suite:
  `.venv/bin/python -m pytest -q`
  -> `910 passed, 21 deselected, 1 warning`.
- Learning-apply execution package contract:
  `.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
  -> `PASS: CI-OS Hermes package contract satisfied`.

## Production Verification

- Deployed package slice after backup:
  `/root/.hermes/apps/cios/.codex-backups/window-comparison-20260711T214637Z`.
- Remote focused window/state/render tests: `3 passed`.
- Remote product-market/dashboard subset: `103 passed`.
- Remote dashboard suite: `124 passed`.
- Remote full suite: `871 passed, 1 skipped, 21 deselected, 1 warning`.
- Remote package contract: `PASS: CI-OS Hermes package contract satisfied`.
- Live Hermes daily wrapper:
  - `algolia: active_sources=48 attempted=48 fetched=43 failed=5 skipped=0 facts=469 deltas=469 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=12`
  - `Run complete in 893.1s. LLM calls used: 12 / 35`
  - `dashboard published to ci.chowmes.com from /root/.hermes/apps/cios`
- Live public payload:
  - `schema_version=18`
  - `generated_at=2026-07-11T22:03:35.987108Z`
  - `product_market_run.status=ran`
  - `product_market_run.runner_verdict=watch`
  - `product_market_run.window_comparison.summary=Last 7 days: 348 product events, 500 conversation themes, 0 demand signals. Last 30 days: 348 product events, 500 conversation themes, 0 demand signals.`
  - `window_count=2`
  - `html_has_evidence_window=True`
- Live click validation: `PASS dashboard_click_validation`.

## Current Known Gap

- The window comparison proves the outside evidence windows, but both the
  7-day and 30-day windows still have `0 demand signals`. The inward demand
  plane remains blocked until GA4/Looker is configured or a real demand export
  is uploaded.
- The live Hermes scheduler path is now repaired and verified. The active
  runtime is the `hermes` container, where host `/root/.hermes` is mounted as
  `/opt/data`. The tested path is:
  `Hermes cron cios-v2-daily -> /opt/data/scripts/cios-daily.sh -> /opt/data/apps/cios`.
- Runtime fixes applied on 2026-07-11:
  - Synced `/opt/data/scripts/cios-daily.sh` with
    `/opt/data/apps/cios/deploy/cios-daily.sh`, including the Argus operator
    handoff attach step.
  - Restored `hermes:hermes` ownership for the CI-OS app/output and public
    dashboard publish directories.
  - Installed CI-OS runtime dependencies into
    `/opt/data/apps/cios/.venv` so the package contract passes as the `hermes`
    user.
  - Raised `cron.script_timeout_seconds` from `360` to `1200` because the
    measured full loop is several minutes and product-surface extraction is the
    current long pole.
- Forced Hermes scheduler run:
  - `cios-v2-daily` last run at `2026-07-11T18:35:58.479350-04:00`.
  - Scheduler status: `ok`.
  - Output file:
    `/opt/data/cron/output/107e64d347d9/2026-07-11_18-35-58.md`.
  - Run summary:
    `active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=5`.
  - Product-market export stage completed in `145.442s`.
  - Full run completed in `377.5s`.
- Live public payload after Hermes scheduler publish:
  - `schema_version=18`
  - `generated_at=2026-07-11T22:35:57.365715Z`
  - `product_market_run.status=ran`
  - `product_market_run.runner_verdict=watch`
  - `product_event_count=393`
  - `conversation_theme_count=500`
  - `demand_signal_count=0`
  - `pattern_count=2`
  - `recommendation_count=0`
  - `window_comparison.summary=Last 7 days: 393 product events, 500 conversation themes, 0 demand signals. Last 30 days: 393 product events, 500 conversation themes, 0 demand signals.`
- Remaining architecture gap: the product-market chain now has a durable
  Postgres-backed stage ledger, and the full daily run now has a persisted
  `cios.daily` ledger. Locally, the daily parent row starts live, and registry,
  source sweep, synthesis, quality review, delivery, product-market chain,
  dashboard-state build, and delivered-tenant publish gate stage events stream
  live. The product-market subledger now records learning application through
  next-sweep planning, apply-plan generation, and proposal-only apply
  execution. The newest live execution-stage, publish-gate, and learning-apply
  slices have not yet been deployed or verified through the live Hermes
  scheduler path.

## 2026-07-12 Live Hermes Package Verification

Problem found during the live Hermes wrapper proof:

- The previous deploy sync removed `/opt/data/apps/cios/.venv`, so the actual
  wrapper failed at `.venv/bin/python`.
- After restoring the venv, the live daily run exposed a real Postgres type
  boundary bug: `jsonb || json` in `PgRunStageRepository.finish_stage()` and
  `finish_ledger()`.
- The Sunday run then exposed two cadence problems:
  - `_deliver_cadence_report()` constructed `QualityReview` without
    `tenant_id`.
  - Weekly/monthly rollups ran by default inside the daily wrapper and could
    block daily publish.
- A quiet run exposed a quality-gate problem: clean quiet days with zero
  claims still called the LLM reviewer, so model variance could block an
  evidence-backed quiet dashboard.

Repairs applied and deployed to `/opt/data/apps/cios`:

- Restored the CI-OS app-local venv with runtime and dev dependencies.
- Cast run-stage JSON metadata parameters with `::jsonb`.
- Added tenant-scoped `QualityReview` construction for cadence delivery.
- Made weekly/monthly rollups opt-in via
  `CIOS_ENABLE_WEEKLY_ROLLUP` and `CIOS_ENABLE_MONTHLY_ROLLUP`.
- Made clean quiet coverage with zero claims pass deterministically without an
  LLM quality call.

Remote backups:

- `/root/.hermes/apps/cios/.codex-backups/runstage-jsonb-20260712T000536Z`
- `/root/.hermes/apps/cios/.codex-backups/live-fixes-20260712T001650Z`
- `/root/.hermes/apps/cios/.codex-backups/cadence-gate-20260712T003409Z`
- `/root/.hermes/apps/cios/.codex-backups/quality-quiet-20260712T005004Z`

Verification:

```text
local full:
.venv/bin/python -m pytest -q
913 passed, 21 deselected, 1 warning

remote package contract:
.venv/bin/python scripts/verify_hermes_package_contract.py --app-dir /opt/data/apps/cios --require-scout --scout-bin /opt/data/apps/cios/scripts/scout_http_shim
PASS: CI-OS Hermes package contract satisfied

remote full:
.venv/bin/python -m pytest -q -p no:cacheprovider
912 passed, 1 skipped, 21 deselected, 1 warning

actual Hermes wrapper:
timeout 900 /opt/data/scripts/cios-daily.sh
exit 0
active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=4
Run complete in 368.1s. LLM calls used: 4 / 35
Competitor briefs written: 27
dashboard published to ci.chowmes.com from /opt/data/apps/cios

live payload:
schema_version=19
generated_at=2026-07-12T00:56:51.390569Z
monitored_competitors=27
product_market_run.status=ran
product_market_stage_count=11

live click validation:
PASS dashboard_click_validation
```

Live routing evidence:

- Constructor brief:
  `./briefs/algolia/constructor-2026-07-11.html`, HTTP 200, contains
  `Constructor`.
- Elastic brief:
  `./briefs/algolia/elastic-2026-07-11.html`, HTTP 200, contains `Elastic`.
- Algonomy brief:
  `./briefs/algolia/algonomy-2026-07-11.html`, HTTP 200, contains `Algonomy`.

Current known gaps:

- Inward demand is still absent: the live payload continues to show no demand
  plane because GA4/Looker has not been configured with real exports.
- The Hermes cron registry still reports the previous scheduled run as last
  cron-owned execution. This session proved the same wrapper path manually;
  the next scheduled cron is `cios-v2-daily` at `2026-07-12T09:00:00-04:00`.

## 2026-07-12 Monitored Source Rows And Product-Muscle Post-Run Trace

Problem found:

- `PgMonitoredCompetitorsRepository` already returned `monitored_sources`, but
  `MonitoredCompetitor` dropped that field from dashboard state.
- Because the daily product-muscle gap planner receives monitored competitors
  from dashboard state, existing active docs/changelog/product URLs could not
  become evidence-backed source candidates.
- The wrapper generated post-run product-muscle discovery and promotion
  sidecars, but `rerender_dashboard.py` preferred report metadata and erased
  those post-run summaries before publication.

Repairs:

- Added `MonitoredCompetitor.monitored_sources` to the dashboard contract.
- Bumped the public dashboard payload to `schema_version=20`.
- Added publisher/state tests proving monitored source rows survive into JSON.
- Patched rerender to keep the latest report's Argus read while preserving
  post-run product-muscle discovery and promotion sidecars from the saved
  dashboard when report metadata lacks them.

Verification:

```text
local full:
.venv/bin/python -m pytest -q
916 passed, 21 deselected, 1 warning

remote focused:
tests/dashboard/test_publisher.py
tests/dashboard/test_state_builder.py::test_monitored_competitors_preserve_active_source_rows_for_product_muscle_gap_discovery
tests/scripts/test_product_market_dashboard_wiring.py::test_rerender_dashboard_preserves_post_run_sidecars_when_latest_report_lacks_them
all passed

actual wrapper:
timeout 900 /opt/data/scripts/cios-daily.sh
exit 0
active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=0 verdict=quiet quality=passed fn=clean delivered=True product_market=ran llm=9
product_surface_export elapsed_s=149.642
Run complete in 688.5s
dashboard published to ci.chowmes.com from /opt/data/apps/cios

live payload:
generated_at=2026-07-12T01:25:24.814854Z
schema_version=20
monitored_competitors=27
monitored_with_source_rows=25
source_health_count=48
product_market_run.status=ran
demand_plane_status=missing
feature_unknown_candidate_url_count=47
post_run_product_muscle_gap_discovery.status=completed
post_run_product_muscle_gap_discovery.candidate_url_count=47
post_run_product_muscle_gap_discovery.duplicate_source_count=47
post_run_product_muscle_gap_discovery.stored_candidate_count=0
post_run_product_surface_promotion.status=completed
post_run_product_surface_promotion.promoted_count=0
post_run_next_sweep_status=Hermes rechecked 47 already-monitored product surfaces; no new sweepable sources were added for the next sweep.

live click validation:
PASS dashboard_click_validation

process check:
no_cios_daily_processes
```

Interpretation:

- The product-muscle loop is no longer blind to active source rows carried by
  monitored competitors.
- The latest run did not add new product surfaces because the 47 candidate
  checks were duplicates of already monitored product surfaces.
- The remaining critical gap is still inward demand: GA4/Looker is not yet
  configured, so Argus correctly keeps the run non-actionable.

## 2026-07-12 Inward Demand Readiness Contract

Problem found:

- The product-market muscle had outward product/conversation evidence, but
  when tenant-side demand was absent the system only exposed
  `demand_plane_status=missing`.
- That made the live UI feel like an empty shell: Hermes/Argus could not say
  whether GA4 was ready, whether a manual Looker export was queued, which
  fields were expected, or what exact operator action should unblock synthesis.

Repairs:

- Added `scripts/export_argus_demand_readiness.py`, a Hermes-callable package
  script that emits a machine-readable inward-demand readiness contract.
- The contract reports latest demand-plane status, manual import previews and
  template fields, GA4 connector readiness, missing config keys, the next
  Hermes action, operator actions, and a safety assertion that secret values
  are not included.
- Added `ProductMarketRunStatus.demand_readiness` and bumped public dashboard
  JSON to `schema_version=21`.
- Patched `attach_post_run_summaries.py` and `rerender_dashboard.py` so the
  readiness sidecar is attached to `product_market_run` and preserved across
  no-fetch rerenders.
- Updated the cockpit run trace to show `Demand readiness` with status,
  next Hermes action, manual queued-file counts, and GA4 readiness.
- Updated the Hermes wrapper contract so `/opt/data/scripts/cios-daily.sh`
  now runs the demand-readiness exporter, requires its artifact before publish,
  and attaches it before public JSON publication.

Verification:

```text
local full:
.venv/bin/python -m pytest -q
920 passed, 21 deselected, 1 warning

remote focused:
50 passed
PASS: CI-OS Hermes package contract satisfied

actual wrapper:
timeout 900 /opt/data/scripts/cios-daily.sh
exit 0
active_sources=48 attempted=48 fetched=42 failed=6 skipped=0 facts=461 deltas=461 signals=1 verdict=signals quality=passed fn=clean delivered=True product_market=ran llm=10
product_surface_export elapsed_s=149.535
Run complete in 660.0s
dashboard published to ci.chowmes.com from /opt/data/apps/cios

live payload:
schema_version=21
generated_at=2026-07-12T01:55:56.197687Z
top_attention_level=watch
product_market_run.status=ran
demand_plane_status=missing
demand_readiness.status=blocked_missing_demand_source
demand_readiness.next_hermes_action=configure_ga4_or_upload_demand_export
manual_import.inbox_file_count=0
ga4_connector.enabled=False
ga4_connector.ready=False
operator_handoff.status=blocked_on_evidence
monitored_competitors=27
active_source_sum=48
signal_count=6

readiness artifact:
artifact_status=blocked_missing_demand_source
artifact_next=configure_ga4_or_upload_demand_export
artifact_secret_values=False
dashboard_attached_readiness=blocked_missing_demand_source configure_ga4_or_upload_demand_export

live click validation:
PASS dashboard_click_validation

process check:
no_cios_daily_processes
```

Interpretation:

- Argus now has an explicit brain contract for the inward demand plane. The
  current production truth is not "demand was processed"; it is "no demand
  source is ready."
- Next real build step: configure GA4 export credentials/windows or upload a
  current Looker export, then run the demand import/refresh fast lane so Argus
  can compare outward market moves against Algolia-side audience demand.

## 2026-07-12 UTC - Public product feature comparison deployed

Problem found:

- Product/feature evidence existed in the product-market ledger, but the
  public cockpit rendered only a few flat `feature_matrix` examples. That did
  not answer the business question: what has Algolia proved, what have
  competitors proved or claimed, and which monitored companies are still
  unknown in the current evidence set?

Repairs:

- Added a typed `product_feature_comparison` dashboard contract with company
  columns, capability rows, evidence cells, proof URLs, counts, row/company
  limits, and explicit `unknown` cells.
- Bumped public dashboard JSON to `schema_version=22`.
- Updated `DashboardStateBuilder` to derive a compact comparison from
  feature evidence plus the monitored competitor universe.
- Updated the cockpit semantic layer from "Product muscle matrix" examples to
  a real "Product feature comparison" table.

Verification:

```text
local focused:
3 passed

local dashboard:
128 passed

local full:
922 passed, 21 deselected, 1 warning

remote deployed smoke:
schema 22
state_has_product_feature_comparison True
html_has_product_feature_comparison True
html_has_ai_shopping_agent True

remote focused:
3 passed, 1 warning

rerender + publish:
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 391987 bytes from live DB state
status=published

live payload:
schema_version=22
generated_at=2026-07-12T02:15:26.999345Z
feature_comparison_rows=12
feature_comparison_total_rows=166
feature_comparison_total_companies=27
feature_comparison_companies=['Algolia', 'Bloomreach', 'Elastic', "Luigi's Box", 'Constructor', 'Lucidworks']
first_capability=Agent Studio

live click validation:
PASS dashboard_click_validation

browser check:
Product feature comparison visible at https://ci.chowmes.com/?v=20260712T021607#semantic-layer
First row shows Agent Studio with proven Algolia/Lucidworks proof and unknown
cells for competitors without captured proof in this evidence set.
```

## 2026-07-12 UTC - Demand-to-feature alignment contract deployed

Problem found:

- The dashboard had product feature proof and raw demand signal summaries, but
  no explicit bridge between the two. That meant Argus could show product
  muscle and separately say whether demand existed, but it could not answer:
  which customer/audience demand topic maps to which product capability and
  which companies have proof?

Repairs:

- Added typed `demand_feature_alignment` state with matched, partially matched,
  unmatched, and no-current-demand statuses.
- Added per-demand rows with metric, value, change, source label, demand proof
  URL, matched capability, related companies, product proof counts, summary,
  and next operator step.
- Used the shared product-market capability normalizer so phrases such as
  `AI shopping agent` and `AI Shopping Agent` map to the same comparison key.
- Added the cockpit semantic-layer block `Audience demand alignment`.
- Bumped public dashboard JSON to `schema_version=23`.

Verification:

```text
local focused:
4 passed

local dashboard:
131 passed

local full:
925 passed, 21 deselected

remote focused:
4 passed, 1 warning

rerender + publish:
brief.html written (state-first)
competitor briefs written: 27
re-rendered cockpit 393048 bytes from live DB state
attached operator handoff to dashboard for tenant_id=1
published=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public

live payload:
schema_version=23
generated_at=2026-07-12T02:31:40.874204Z
alignment_status=no_current_demand
alignment_rows=0
product_feature_rows=12

live click validation:
PASS dashboard_click_validation

live HTML:
Audience demand alignment
No demand-to-product alignment was published with this run.

browser check:
https://ci.chowmes.com/?v=20260712T023140#semantic-layer
```

Production meaning:

- Argus now has a first-class contract for connecting inward demand to product
  proof. This is one piece of the requested brain, not a finished brain.
- The current production state is honest: no current demand rows are available,
  so no demand-to-product alignment can be computed yet.
- Next real build step: connect GA4/Looker exports or upload current demand
  data, run the demand import/refresh lane, and require the live payload to
  move from `no_current_demand` to matched or unmatched rows with proof.

## 2026-07-12 UTC - Demand import fast lane now refreshes Argus sidecars

Problem found:

- The operator demand-import fast lane normalized and persisted exports, ran
  the product-market ledger refresh, rerendered, and could publish. It did not
  refresh the demand-readiness sidecar, evidence work queue, or Argus operator
  handoff before publishing.
- That gap let public state drift. The live readiness artifact was stale and
  pointed the manual demand drop folder at `/opt/data/apps/cios/data/looker`,
  while the active production CI-OS package root is
  `/root/.hermes/apps/cios`.

Repairs:

- Added a post-rerender artifact refresh step to
  `scripts/import_demand_and_refresh.py`.
- After every rerender, the fast lane now runs:
  `export_argus_demand_readiness.py`,
  `attach_post_run_summaries.py`,
  `export_argus_evidence_work_queue.py`,
  `build_argus_operator_handoff.py`, and
  `attach_operator_handoff_to_dashboard.py`.
- Publish now copies a complete Argus artifact set rather than only the raw
  rerender output.
- Refreshed and republished production demand readiness with the active app
  root.

Verification:

```text
local focused:
tests/scripts/test_import_demand_and_refresh.py
7 passed

local sidecar scripts:
21 passed

local full:
925 passed, 21 deselected

remote focused:
tests/scripts/test_import_demand_and_refresh.py
7 passed, 1 warning

live payload:
schema_version=23
alignment_status=no_current_demand
readiness_status=blocked_missing_demand_source
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
next_hermes_action=configure_ga4_or_upload_demand_export

live click validation:
PASS dashboard_click_validation

browser check:
https://ci.chowmes.com/?v=20260712T023926#semantic-layer
```

Follow-up hardening in the same slice:

- Found that the reported manual upload folder still did not exist after the
  readiness path was corrected.
- Patched `export_argus_demand_readiness.py` so the readiness artifact creates
  the tenant manual drop folder before reporting it.
- Added ownership alignment: if the exporter runs as root, the `data`,
  `data/looker`, and tenant drop folders are chowned to the CI-OS app root
  owner so app/admin upload can write there.

Verification:

```text
local focused:
11 passed

local full:
926 passed, 21 deselected

remote focused:
4 passed, 1 warning

remote folder:
/root/.hermes/apps/cios/data 10000:10000
/root/.hermes/apps/cios/data/looker 10000:10000
/root/.hermes/apps/cios/data/looker/algolia 10000:10000

public payload after republish:
schema_version=23
readiness_generated_at=2026-07-12T02:43:12.588897Z
readiness_status=blocked_missing_demand_source
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
next_hermes_action=configure_ga4_or_upload_demand_export
alignment_status=no_current_demand

live click validation:
PASS dashboard_click_validation

browser:
https://ci.chowmes.com/?v=20260712T024312#semantic-layer
```

Production meaning:

- The system still needs real GA4 or Looker demand rows. That is not solved by
  this slice.
- The path that will ingest those rows is now operationally safer: importing
  demand no longer risks publishing a dashboard with stale demand readiness or
  stale Argus handoff state.

## 2026-07-12 UTC - Admin refresh now rebuilds Argus sidecars before publish

Problem found:

- The admin dashboard refresh runner could rerender and publish the dashboard,
  but it did not rebuild the same Argus sidecars now used by the repaired
  demand import fast lane.
- That meant an operator using the admin path could still publish fresh HTML
  with stale demand readiness, stale evidence work queue, or stale Argus
  handoff state.

Repair:

- Patched `src/cios/admin/dashboard_refresh.py` so the admin refresh chain now
  runs these sidecars after rerender and before publish:
  `export_argus_demand_readiness.py`, `attach_post_run_summaries.py`,
  `export_argus_evidence_work_queue.py`,
  `build_argus_operator_handoff.py`, and
  `attach_operator_handoff_to_dashboard.py`.
- Sidecar failure now blocks publish instead of allowing a partial public
  dashboard update.
- Added admin runner tests for the happy path and the failed-sidecar publish
  gate.

Verification:

```text
local focused admin+demand tests:
76 passed

local full:
927 passed, 21 deselected, 1 warning

remote focused admin refresh tests:
3 passed, 1 warning

production admin runner smoke:
runner_status=published
publish_status=published
sidecar_steps=demand_readiness, attach_demand_readiness, evidence_work_queue, operator_handoff, attach_operator_handoff

public payload:
schema_version=23
generated_at=2026-07-12T02:50:53.792723Z
readiness_generated_at=2026-07-12T02:50:54.513953Z
readiness_status=blocked_missing_demand_source
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
alignment_status=no_current_demand
operator_handoff_status=blocked_on_evidence

live click validation:
PASS dashboard_click_validation
```

Production meaning:

- The admin refresh path is no longer a stale-sidecar publish hole.
- The public system still has no real inward demand feed connected. That is the
  next hard blocker for intelligence depth: GA4/Looker export ingestion must
  produce real rows before Argus can align demand to competitor changes.

## 2026-07-12 UTC - Demand importer now rejects incomplete pre-normalized rows

Problem found:

- The manual / GA demand importer accepted any row with `topic`, `metric`, and
  `value` as already normalized.
- That allowed rows with no period or stable source provenance to be marked
  `ready` in the operator manifest, even though the ledger persister requires
  period and evidence fields before it can create a valid `DemandSignal`.
- This was another potential empty-shell failure mode: the UI could say demand
  input was ready while Argus could not safely persist or cite it.

Repair:

- Tightened `src/cios/intelligence/importers.py` so pre-normalized demand rows
  must have a parseable period before they become normalized rows.
- Added stable provenance defaults for otherwise-valid pre-normalized rows:
  `source_label=Looker Studio GA4 export` and a `looker://<file>#row-<n>`
  source URL when the export did not provide one.
- Added importer and admin prepare regressions so incomplete pre-normalized rows
  become explicit skipped rows with `reason=missing_period` and never produce
  a ready payload.

Verification:

```text
red before fix:
3 failed

green focused:
3 passed

local importer/admin/fast-lane tests:
21 passed

local dashboard alignment regressions:
2 passed

local full:
930 passed, 21 deselected, 1 warning

production backup:
/root/.hermes/backups/cios-demand-importer-contract-20260712T025747Z.tgz

remote focused:
10 passed, 1 warning
```

Production meaning:

- Manual demand uploads and GA / Looker JSON exports now have a safer contract:
  if a row cannot become evidence-backed `DemandSignal` input, it is surfaced
  as skipped at prepare time instead of failing later inside synthesis.
- This still does not connect real Algolia GA4 / Looker data. It makes the
  ingestion lane trustworthy for the moment that real data is uploaded or the
  connector is configured.

## 2026-07-12 UTC - Demand file to dashboard smoke found and fixed Postgres dedupe bug

Problem found:

- A production-safe rollback smoke tried the real path:
  demand file -> `DemandImportStore.prepare` -> `DemandImportLedgerPersister`
  -> `PgProductMarketRepository.save_demand_signal` -> ledger refresh ->
  `DashboardStateBuilder`.
- The path failed inside Postgres with:
  `psycopg.errors.AmbiguousParameter: could not determine data type of parameter`
  on `%(source_fingerprint)s IS NOT NULL`.
- This meant demand imports could normalize correctly but fail at the real DB
  ledger boundary before Argus could synthesize demand-backed intelligence.

Repair:

- Patched `src/cios/db/repos/product_market.py` so the source fingerprint
  dedupe predicate casts the parameter as text:
  `%(source_fingerprint)s::text IS NOT NULL` and
  `metadata->>'source_fingerprint' = %(source_fingerprint)s::text`.
- Added repository regression coverage in
  `tests/db/test_product_market_repo.py`.
- Added a guarded integration harness in
  `tests/integration/test_demand_to_dashboard_flow.py` proving the intended
  chain against a resettable local Postgres fixture when the local integration
  DB is available.

Verification:

```text
red before fix:
tests/db/test_product_market_repo.py::test_save_demand_signal_targets_demand_signals
1 failed

local focused after fix:
41 passed

local full after fix:
930 passed, 22 deselected, 1 warning

production backup:
/root/.hermes/backups/cios-demand-ledger-postgres-cast-20260712T030537Z.tgz

remote focused:
tests/db/test_product_market_repo.py::test_save_demand_signal_targets_demand_signals
1 passed, 1 warning

remote rollback smoke:
prepared_ready_count=1
persisted_demand_signal_count=1
summary_verdict=actionable
summary_demand_signal_count=1
summary_pattern_count=2
summary_recommendation_count=1
alignment_status=matched
alignment_match_status=matched
alignment_matched_capability=AI Shopping Agent
demand_plane_status=present
recommendation_count=1
```

Production meaning:

- The package now has a verified path from an uploaded demand file through the
  real demand ledger, Argus ledger replay, recommendations, and dashboard
  semantic alignment.
- The proof did not publish fake intelligence: the VPS smoke ran inside a
  rollback transaction.
- The remaining production blocker is still real Algolia GA4 / Looker data
  availability. Once a real export is uploaded or the GA4 connector is
  configured, this path has now been proven to carry it into Argus instead of
  dying at the DB boundary.

## 2026-07-12 UTC - Hermes demand-source gate added

Problem:

- Argus now has a demand import path, but production still has no committed
  demand rows, no queued manual GA / Looker export, and GA4 disabled or
  unconfigured.
- Without an executable gate, Hermes could keep running a sweep and publish a
  dashboard that looks intelligent while the inward demand plane is empty.

Repair:

- Added `scripts/check_argus_demand_source_gate.py`.
- The gate reuses the existing readiness contract from
  `scripts/export_argus_demand_readiness.py` and turns it into a machine
  enforceable Hermes/admin exit code:
  - `0`: usable demand source is ready.
  - `2`: no usable demand source is ready.
  - `3`: a manual export exists but contains validation errors.
- Default mode passes when one of these is true:
  - current demand is already processed into dashboard state,
  - a valid manual export is queued,
  - GA4 export is configured and ready.
- Strict mode, via `--require-current-demand`, passes only when current demand
  has already been processed.
- Added regression coverage in
  `tests/scripts/test_check_argus_demand_source_gate.py`.

Verification:

```text
red before script/path fix:
6 failed

local focused:
6 passed

local adjacent readiness/import suite:
17 passed

local full:
936 passed, 22 deselected, 1 warning

production backup:
/root/.hermes/backups/cios-demand-source-gate-20260712T031620Z.tgz

remote focused:
6 passed, 1 warning

live production gate:
status=fail
exit_code=2
readiness_status=blocked_missing_demand_source
next_hermes_action=configure_ga4_or_upload_demand_export
source_ready=false
current_demand_processed=false
manual_export_ready=false
ga4_ready=false
processed_row_count=0
manual_drop_folder=/root/.hermes/apps/cios/data/looker/algolia
```

Production meaning:

- Hermes now has an enforceable stop condition for the inward-demand muscle.
- This does not make Argus intelligent by itself. It prevents Argus from
  pretending the demand layer exists when production has no real demand input.
- Next production action remains the same and is now machine-readable:
  configure GA4 or upload a real GA / Looker export into the tenant drop
  folder.

## 2026-07-12 UTC - Daily runner and Hermes wrapper obey demand-source gate

Problem:

- A standalone demand-source gate is useful, but not enough. Hermes daily
  execution also needed to treat missing demand as a publish blocker so the
  public dashboard cannot claim product-market intelligence on product and
  conversation evidence alone.
- The cron wrapper also exited immediately on a blocked daily run, which meant
  operators could miss the machine-readable reason unless they inspected logs.

Repair:

- Added a daily-run publish gate helper that blocks when
  `product_market_summary.status == ran` and explicit GA / Looker / ledger
  demand counts are all zero.
- The block is conservative:
  - it allows publish when demand is present in the ledger,
  - it allows publish when a manual Looker/GA export produced ready rows,
  - it preserves the existing behavior for disabled product-market runs,
  - it preserves existing non-demand product-market failure blocks.
- Updated `deploy/cios-daily.sh` so a non-zero
  `scripts/daily_production_run.py` exit triggers
  `scripts/check_argus_demand_source_gate.py` and writes
  `out/argus-demand-source-gate.json` before exiting with the original daily
  runner code.

Verification:

```text
red before runner fix:
test_dashboard_publish_blocks_product_market_run_without_demand_source
1 failed

local publish-gate focused:
8 passed, 91 deselected

local daily runner file:
99 passed

red before wrapper fix:
test_hermes_wrapper_writes_demand_source_gate_when_daily_blocks_publish
1 failed

local wrapper focused:
1 passed

local wrapper suite:
13 passed

local runner/wrapper/package/gate suite:
133 passed

local full:
940 passed, 22 deselected, 1 warning

production backup:
/root/.hermes/backups/cios-runner-demand-publish-gate-20260712T032243Z.tgz

remote publish-gate focused:
8 passed, 91 deselected, 5 warnings

remote wrapper+gate focused:
7 passed, 1 warning

production app path check:
/opt/data/apps/cios exists=no
/root/.hermes/apps/cios exists=yes

live demand-source gate after deploy:
status=fail
exit_code=2
readiness_status=blocked_missing_demand_source
source_ready=false
current_demand_processed=false
manual_export_ready=false
ga4_ready=false
```

Production meaning:

- Hermes now has two enforcement points:
  - the CI-OS daily runner blocks public dashboard artifact generation when
    product-market intelligence has no demand source,
  - the Hermes cron wrapper writes a demand-source gate artifact on blocked
    daily runs and exits non-zero before public copy.
- This is still not the full Argus brain. It is the first hard nervous-system
  reflex: no real inward demand evidence, no public product-market
  intelligence claim.

## 2026-07-12 UTC - Admin demand import accepts real export files

Problem:

- The demand plane could be supplied through the JSON API by posting
  `filename` and `content`, and through the admin HTML form by pasting rows.
- That is technically sufficient but operationally wrong for the actual user
  workflow: a GA / Looker operator has an exported `.csv`, `.json`, or `.jsonl`
  file and should be able to upload that file directly.

Repair:

- Updated the local admin demand import form to use
  `enctype="multipart/form-data"` with a real file input.
- Added a small dependency-free multipart parser in `src/cios/admin/app.py`
  for this local-only path, avoiding a new production package dependency.
- Preserved the existing JSON API upload path for automation.
- Multipart uploads still flow through `DemandImportStore.upload`, so the
  same filename safety checks and accepted suffix rules apply.

Verification:

```text
red before fix:
test_admin_html_uploads_argus_demand_export_file_to_tenant_drop_folder
test_admin_html_lists_competitors_sources_and_add_forms
2 failed

local focused:
4 passed, 1 warning

local admin folder:
67 passed, 1 warning

local demand/import readiness scripts:
17 passed

local full:
941 passed, 22 deselected, 1 warning

production backup:
/root/.hermes/backups/cios-admin-demand-file-upload-20260712T032817Z.tgz

remote focused:
4 passed, 2 warnings

remote admin folder:
67 passed, 2 warnings
```

Production meaning:

- The current production blocker is now cleanly external: a real GA / Looker
  export or GA4 credentials are needed.
- Once a real file is available, the operator path is:
  admin upload -> tenant drop folder -> prepare -> persist to demand ledger ->
  Argus ledger replay -> dashboard refresh.

## 2026-07-12 UTC - Public confidence rubric stops fabricating scores

Problem:

- The backend recommendation path already requires an explicit Argus scorecard,
  but the public cockpit renderer still invented a fallback "confidence" score
  from UI-side heuristics when no backend recommendation cleared the action
  gate.
- That made a blocked or incomplete run look more certain than it was, and it
  violated the product rule that every score must trace to the CI-OS brain, not
  the screen.

Repair:

- Updated `src/cios/dashboard/cockpit_renderer.py` so the semantic layer shows a
  numeric confidence rubric only when an `ArgusRecommendationSummary` has a real
  backend scorecard.
- When no scorecard exists, the rubric now renders `Not scored`, explains that
  no backend recommendation scorecard exists, and surfaces the first confidence
  limit or evidence blocker.
- Removed the old fallback rows such as source coverage, materiality
  separation, recency, and quality gate from the confidence rubric. Those facts
  still belong elsewhere in the dashboard, but they are not a recommendation
  score.
- Updated the live click validator so it accepts either:
  - a real backend scorecard with scorecard dimensions, or
  - an explicit `Not scored` state with a backend-scorecard blocker.

Verification:

```text
red before fix:
test_semantic_layer_refuses_confidence_score_without_backend_scorecard
1 failed

focused green:
test_semantic_layer_refuses_confidence_score_without_backend_scorecard
1 passed

dashboard renderer:
tests/dashboard/test_cockpit_renderer.py
27 passed

dashboard suite:
tests/dashboard
132 passed

validator focused:
tests/scripts/test_validate_dashboard_clicks_dependencies.py
5 passed

live click validation:
scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/
PASS dashboard_click_validation
```

## 2026-07-12 UTC - Production full-suite verification environment repaired

Problem:

- After the confidence-rubric deployment, the relevant remote focused suites
  passed, but the remote full package suite failed before executing many async
  tests because the production app venv had `pytest` but not `pytest-asyncio`.
- `pyproject.toml` already declares `pytest-asyncio` in the `dev` extra, so this
  was a production verification environment drift, not an application logic
  failure.

Repair:

- Added a validation-only `--require-test-deps` flag to
  `scripts/verify_hermes_package_contract.py`.
- The normal Hermes cron preflight remains runtime-focused and does not require
  test-only dependencies.
- Remote validation can now fail fast with
  `missing required test dependency: pytest_asyncio` before a misleading full
  suite run.
- Installed the declared dev dependency `pytest-asyncio>=0.23` into the live
  `/root/.hermes/apps/cios/.venv`.

Verification:

```text
red before verifier change:
test_preflight_can_require_async_pytest_plugin_for_remote_full_suite
failed because --require-test-deps did not exist

local verifier focused:
test_preflight_can_require_async_pytest_plugin_for_remote_full_suite
1 passed

local verifier suite:
tests/scripts/test_verify_hermes_package_contract.py
16 passed

remote validation preflight before install:
missing required test dependency: pytest_asyncio

remote install:
pytest-asyncio-1.4.0 installed into /root/.hermes/apps/cios/.venv

remote validation preflight after install:
PASS: CI-OS Hermes package contract satisfied

remote full package suite:
944 passed, 1 skipped, 22 deselected, 1 warning
```

## 2026-07-12 UTC - Hermes data-plane manifest sidecar added

Problem:

- The dashboard, demand readiness, evidence work queue, and operator handoff
  existed as separate artifacts, but Hermes and Argus did not have one compact
  machine-readable answer to the operating question: which intelligence planes
  fed this run, which storage tables back them, what is missing, and what blocks
  action.
- That made the screen easier to inspect than the actual intelligence machine.
  It also left non-cron refresh paths able to publish dashboard JSON without a
  current "brain and muscle" manifest.

Repair:

- Added `scripts/export_argus_data_plane_manifest.py`.
- The manifest derives from existing source-of-truth artifacts rather than
  inventing new claims:
  - `argus-dashboard.json`
  - `argus-demand-readiness.json`
  - `argus-evidence-work-queue.json`
  - `argus-operator-handoff.json`
- It publishes six explicit planes:
  - registry and coverage
  - product reality
  - market conversation
  - audience demand
  - operator learning
  - run truth
- It records source-of-truth ownership as Hermes runtime, CI-OS domain package,
  Postgres evidence ledger, and UI as derived readout only.
- It marks missing demand as an action blocker and carries the next Hermes
  action from demand readiness.
- Wired the manifest into:
  - `deploy/cios-daily.sh`
  - `scripts/verify_hermes_package_contract.py`
  - `scripts/import_demand_and_refresh.py`
  - `src/cios/admin/dashboard_refresh.py`
  - `src/cios/dashboard/artifacts.py`
- The public publish path now copies
  `argus-data-plane-manifest.json` to both:
  - `data/argus-data-plane-manifest.json`
  - `v2/data/argus-data-plane-manifest.json`

Verification:

```text
red before implementation:
tests/scripts/test_export_argus_data_plane_manifest.py
3 failed because export_argus_data_plane_manifest.py did not exist

red before wrapper/preflight wiring:
tests/scripts/test_verify_hermes_package_contract.py tests/deploy/test_cios_daily_wrapper.py
8 failed because preflight and wrapper did not require, generate, or publish the manifest

red before refresh/publish wiring:
tests/scripts/test_import_demand_and_refresh.py tests/admin/test_dashboard_refresh.py
4 failed because demand/admin refresh and shared publish did not handle the manifest

focused manifest contract:
tests/scripts/test_export_argus_data_plane_manifest.py
3 passed

wrapper/preflight:
tests/scripts/test_verify_hermes_package_contract.py tests/deploy/test_cios_daily_wrapper.py
31 passed

demand/admin refresh:
tests/scripts/test_import_demand_and_refresh.py tests/admin/test_dashboard_refresh.py
10 passed

combined focused bundle:
tests/scripts/test_export_argus_data_plane_manifest.py \
tests/scripts/test_verify_hermes_package_contract.py \
tests/deploy/test_cios_daily_wrapper.py \
tests/scripts/test_import_demand_and_refresh.py \
tests/admin/test_dashboard_refresh.py
44 passed
```

Remaining blocker:

- The manifest exposes the missing/blocked demand plane; it does not remove the
  production blocker. Real GA4 credentials or a usable GA / Looker export are
  still required before Argus can promote fully demand-backed recommendations.

## 2026-07-12 UTC - Demand plan-template ingestion metadata preserved

Problem:

- The admin demand-plan template exposed Argus planning columns such as topic,
  capability key, assessment, suggested filters, related competitors,
  collection rationale, and evidence URLs.
- The importer could normalize those rows, but the Looker/GA adapter only
  preserved generic source metadata. That meant a filled Argus plan template
  could become a `DemandSignal` while dropping the plan context Argus needs to
  explain why the demand row was collected and which product-market read it
  answers.

Repair:

- Added importer coverage for plan-template rows whose page title/path are
  blank but whose `Argus topic` and `Capability key` are filled.
- Preserved `argus_capability_key`, `argus_assessment`,
  `argus_suggested_filters`, `argus_related_competitors`,
  `argus_why_collect`, and `argus_evidence_urls` through
  `looker_row_to_demand_signal(...)` into `DemandSignal.metadata`.
- Preserved demand metadata in current-demand repository reads.
- Added a sanitized `DemandSignalSummary.argus_plan_context` public dashboard
  field and bumped the dashboard state schema to v24.
- Added full `DemandSignalAdminRecord.metadata` in the local admin evidence
  ledger for operator debugging.
- Rendered Argus demand-plan context in the cockpit demand response section:
  assessment, related competitors, and collection rationale.

Verification:

```text
red before adapter patch:
tests/intelligence/test_adapters.py::test_looker_row_preserves_argus_plan_metadata
failed because only source_file, source_row_number, and source_fingerprint were preserved

focused green:
tests/intelligence/test_adapters.py::test_looker_row_preserves_argus_plan_metadata
1 passed

affected demand/template suite:
tests/intelligence/test_adapters.py \
tests/intelligence/test_importers.py \
tests/scripts/test_import_demand_and_refresh.py \
tests/scripts/test_run_argus_demand_intake.py \
tests/admin/test_demand_imports.py \
tests/admin/test_app.py::test_json_api_returns_argus_plan_specific_demand_import_template
37 passed, 1 warning

compile:
python -m py_compile src/cios/intelligence/adapters.py src/cios/intelligence/importers.py
passed

follow-up metadata visibility red checks:
tests/db/test_product_market_repo.py::test_get_current_demand_signals_reads_demand_signals
failed because current-demand SELECT omitted metadata

tests/dashboard/test_state_builder.py::test_product_market_demand_signal_exposes_argus_plan_context
failed because DemandSignalSummary had no argus_plan_context

tests/admin/test_app.py::test_json_api_returns_argus_evidence_ledger
failed because demand signal metadata was not serialized in admin JSON

tests/dashboard/test_cockpit_renderer.py -k "Looker or product_market"
failed because the cockpit did not render plan assessment, related competitors,
or collection rationale

affected dashboard/admin/demand suite:
tests/intelligence/test_adapters.py \
tests/intelligence/test_importers.py \
tests/db/test_product_market_repo.py \
tests/dashboard/test_state_builder.py \
tests/dashboard/test_cockpit_renderer.py \
tests/admin/test_app.py::test_json_api_returns_argus_evidence_ledger \
tests/admin/test_demand_imports.py \
tests/admin/test_app.py::test_json_api_returns_argus_plan_specific_demand_import_template \
tests/scripts/test_import_demand_and_refresh.py \
tests/scripts/test_run_argus_demand_intake.py
139 passed, 1 warning

compile:
python -m py_compile src/cios/intelligence/adapters.py src/cios/intelligence/importers.py \
src/cios/db/repos/product_market.py src/cios/dashboard/types.py \
src/cios/dashboard/state_builder.py src/cios/dashboard/cockpit_renderer.py \
src/cios/admin/types.py src/cios/admin/repository.py
passed

full local suite after schema v24 contract update:
1040 passed, 22 deselected, 1 warning

remote affected suite after deployment:
147 passed, 1 warning

remote full suite after deployment:
1039 passed, 1 skipped, 22 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote admin smoke:
cios-admin.service active after restart
demand plan template endpoint returns CSV with Argus topic, capability key,
assessment, suggested filters, related competitors, collection rationale, and
evidence URL columns
evidence ledger endpoint responds for algolia; current demand_count=0
```

Remaining blocker:

- This repairs the ingestion path for a filled plan template. It does not itself
  provide real GA4/Looker demand data. Production actionability is still blocked
  until the demand source is configured or a plan-template export is uploaded.

## 2026-07-12 UTC - Demand plan capability key drives matching and coverage

Problem:

- The Argus demand-plan template carries a human analytics/export topic and a
  separate Argus capability key.
- The importer and dashboard preserved that metadata, but the intelligence
  layer still matched demand to product proof by normalizing only the visible
  topic label.
- That could make Argus falsely report planned demand as missing or off-plan
  even when the operator filled the correct demand-plan row.

Repair:

- Added `demand_capability_key(...)` to the capability-normalization layer.
- Demand matching now prefers `metadata.argus_capability_key` or public
  `argus_plan_context.capability_key` before falling back to the visible topic.
- Wired this through:
  - product-market runner demand read
  - product-market conversion diagnostics
  - deterministic synthesizer rising-demand grouping
  - feature comparison read demand grouping
  - dashboard demand-to-product alignment
- Added integration coverage for a plan-template CSV with blank page
  title/path fields, an analytics topic that does not match product proof, and
  an explicit capability key that does.

Verification:

```text
red before patch:
tests/intelligence/test_runner.py::test_demand_read_uses_argus_plan_capability_key_for_matching
failed because demand_read.top_topics[0].capability_key was "agent experience pages"
instead of "assistant"

tests/dashboard/test_state_builder.py::test_state_builder_uses_argus_plan_capability_key_for_demand_alignment
failed because dashboard demand alignment marked the row unmatched

focused green:
tests/intelligence/test_runner.py::test_demand_read_uses_argus_plan_capability_key_for_matching
1 passed

affected non-integration suite:
tests/intelligence/test_runner.py \
tests/intelligence/test_product_market_synthesizer.py \
tests/intelligence/test_feature_matrix.py \
tests/intelligence/test_capabilities.py \
tests/dashboard/test_state_builder.py \
tests/dashboard/test_cockpit_renderer.py \
tests/scripts/test_export_argus_demand_readiness.py \
tests/admin/test_demand_imports.py \
tests/intelligence/test_adapters.py \
tests/intelligence/test_importers.py
145 passed

compile:
python -m py_compile src/cios/intelligence/capabilities.py \
src/cios/intelligence/runner.py src/cios/intelligence/product_market.py \
src/cios/intelligence/feature_matrix.py src/cios/dashboard/state_builder.py \
tests/integration/test_demand_to_dashboard_flow.py
passed

local integration contract:
tests/integration/test_demand_to_dashboard_flow.py::test_argus_plan_template_demand_file_uses_capability_key_for_dashboard_alignment
skipped locally because CIOS_DATABASE_URL is not set

full local suite:
1042 passed, 23 deselected, 1 warning

remote affected suite after deployment:
145 passed

remote full suite after deployment:
1041 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote integration contract:
tests/integration/test_demand_to_dashboard_flow.py::test_argus_plan_template_demand_file_uses_capability_key_for_dashboard_alignment
skipped because CIOS_DATABASE_URL is not set in the remote test shell
```

Remaining blocker:

- This fixes capability matching once demand exists. It still does not create
  real GA4/Looker demand rows for production; the live system remains blocked
  until demand is uploaded or GA4 is configured.

## 2026-07-12 UTC - Product-muscle ledger repair and demand fast-lane trace parity

Problem:

- Meilisearch and Typesense had active product surfaces, but Scout/Argus
  extraction had previously produced empty product evidence. The operator queue
  therefore kept showing them as product-muscle work items even after the
  GitHub release fallback generated product rows.
- The manual/queued demand fast lane rebuilt the product-muscle sidecar after a
  demand import, but it did not pass the configured `work_root` into
  `export_argus_product_muscle_work_queue.py`. That meant a non-default Hermes
  run could refresh demand with a product-surface execution trace from the
  wrong work directory.
- The remote full suite also exposed a test isolation bug: the Scout HTTP shim
  no-header test inherited the live `SCOUT_API_KEY` from the VPS environment.

Repair:

- Verified the GitHub release fallback outputs on the VPS:
  - latest Meilisearch repair artifact: 12 product rows
  - latest Typesense repair artifact: 12 product rows
  - combined manual payload: 24 Scout/product records
- Verified Postgres now has product evidence for both companies:
  - `Meilisearch`: 12 `product_change_events`
  - `Typesense`: 12 `product_change_events`
- Ran an admin no-public refresh from the live app. The Hermes-facing
  product-muscle queue dropped from 5 limiting items to 3:
  `Athos Commerce`, `Coveo`, and `Searchspring`.
- Added a regression assertion that the demand fast lane passes `--work-root`
  into the product-muscle sidecar rebuild.
- Updated `scripts/import_demand_and_refresh.py` so manual/queued demand
  imports refresh product-muscle evidence from the same configured work root
  as the demand readiness artifact.
- Isolated `tests/scripts/test_scout_http_shim.py` from live Scout auth
  environment variables before asserting the no-header path.

Verification:

```text
red before demand fast-lane patch:
tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_invokes_refresh_and_rerender_after_prepare
failed because calls[5] did not include --work-root

focused green:
tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_invokes_refresh_and_rerender_after_prepare
1 passed

local affected suite:
tests/scripts/test_import_demand_and_refresh.py \
tests/scripts/test_run_argus_demand_intake.py \
tests/scripts/test_export_argus_demand_readiness.py \
tests/scripts/test_export_argus_product_muscle_work_queue.py \
tests/admin/test_dashboard_refresh.py
29 passed

local Scout env-isolation regression:
SCOUT_API_KEY=local-env-key tests/scripts/test_scout_http_shim.py::test_main_posts_to_hosted_scout_and_prints_json
1 passed

full local suite:
1053 passed, 23 deselected, 1 warning

remote backup after demand fast-lane deploy:
/root/.hermes/backups/cios-demand-fastlane-workroot-20260712T124817Z.tgz

remote affected suite:
29 passed

remote full suite after Scout env-isolation fix:
1052 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied
```

Remaining blocker:

- Product reality is improving and the queue now reflects current ledger truth,
  but actionability is still blocked by the inward-demand plane. The live
  manifest remains `blocked_on_evidence` until GA4 is configured or a real
  GA/Looker export is uploaded and mapped to the Argus demand collection plan.

## 2026-07-12 Operator Handoff Repair Slice

Problem:

- The demand-readiness sidecar already knew the correct operator path for a
  missing demand plane: `Download demand plan template` with `?planned=1`.
- The Hermes-facing operator handoff could still promote the older generic
  evidence-queue command, `Download demand template`, as the primary command.
- The admin dashboard refresh runner also omitted `--demand-readiness` when it
  rebuilt `argus-operator-handoff.json`, so an admin refresh could overwrite a
  corrected handoff with the weaker generic command.

Repair:

- Added a regression test proving demand-plane blockers use the first concrete
  demand-readiness action as the handoff primary command.
- Updated `scripts/build_argus_operator_handoff.py` so demand evidence blockers
  prefer the demand-readiness primary action while preserving the existing
  secondary refresh command.
- Added a regression assertion that admin refresh passes
  `--demand-readiness out/argus-demand-readiness.json` into
  `build_argus_operator_handoff.py`.
- Updated `src/cios/admin/dashboard_refresh.py` so admin refresh, demand
  fast-lane refresh, and Hermes wrapper paths all preserve the same demand
  sidecar context.
- Deployed the script, admin runner, and regression tests to
  `/root/.hermes/apps/cios`.
- Ran the live admin refresh runner and republished the dashboard artifacts to
  `/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public`.

Verification:

```text
red before handoff patch:
tests/scripts/test_build_argus_operator_handoff.py::test_build_operator_handoff_uses_plan_aware_demand_action_as_primary_command
failed because primary_command was Download demand template without ?planned=1

focused handoff green:
1 passed

handoff script suite:
9 passed

red before admin refresh patch:
tests/admin/test_dashboard_refresh.py::test_admin_dashboard_refresh_runner_rerenders_and_publishes
failed because the build_argus_operator_handoff.py command omitted --demand-readiness

admin refresh focused green:
1 passed

local affected suite:
58 passed

full local suite:
1054 passed, 23 deselected, 1 warning

remote backups:
/root/.hermes/backups/cios-operator-handoff-plan-action-20260712T130014Z.tgz
/root/.hermes/backups/cios-admin-refresh-demand-readiness-handoff-20260712T130345Z.tgz

remote affected suite:
58 passed

remote full suite:
1053 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

admin refresh publish:
status=published
public_dir=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public

live dashboard click validation:
PASS dashboard_click_validation

live semantic-dashboard.json:
operator_handoff.status=blocked_on_evidence
operator_handoff.primary_command.label=Download demand plan template
operator_handoff.primary_command.href=/api/tenants/algolia/argus/demand-imports/template?planned=1
schema_version=24

live argus-data-plane-manifest.json:
status=blocked_on_evidence
next_hermes_action=configure_ga4_or_upload_demand_export
first blocker operator command=Download demand plan template
```

Remaining blocker:

- Argus now tells the operator the right next action for the missing inward
  demand plane, but the plane is still missing. CI-OS is still not fully
  actionable until GA4 is configured or a real GA/Looker export is uploaded,
  imported, scored against the demand collection plan, and replayed through
  Argus synthesis.

## 2026-07-12 Inward Demand Consume/Archive Slice

Problem:

- The operator/manual demand fast lane could prepare, persist, refresh, and
  rerender a GA / Looker export, but it left the raw uploaded file in the
  active tenant inbox after success.
- That made the admin surface continue to look like demand was still queued
  even after it had been consumed, and it created a repeat-processing risk for
  future operator/Hermes runs.

Repair:

- Added `DemandImportStore.archive_prepared(...)` as the CI-OS package-level
  primitive for moving consumed raw demand exports out of the active inbox.
- Successful prepared rows move to
  `data/looker/{tenant}/_archive/{timestamp}/`.
- Empty or invalid prepared files move to
  `data/looker/{tenant}/_rejected/{timestamp}/` only when the import is being
  consumed after success.
- Prepare-only remains non-destructive for inspection.
- Failed refresh/rerender/publish paths keep files queued so the operator can
  repair or retry.
- `scripts/import_demand_and_refresh.py` now archives only after demand
  persistence succeeded and the requested downstream refresh/render/publish
  work succeeded.

Verification:

```text
red before archive patch:
tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_archives_consumed_queued_file_after_success
failed because data/looker/algolia/ga-pages.csv still existed after successful refresh

focused archive regressions:
2 passed

local demand/import affected suite:
36 passed, 2 deselected

full local suite:
1056 passed, 23 deselected, 1 warning

remote backup:
/root/.hermes/backups/cios-demand-consume-archive-20260712T131303Z.tgz

remote demand/import affected suite:
36 passed, 2 deselected

remote full suite:
1055 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

live demand inbox state:
inbox_files=0
ready_count=0
error_count=0
normalized_row_count=0
archived_files=0
drop_folder=/root/.hermes/apps/cios/data/looker/algolia
```

Remaining blocker:

- The inward-demand ingestion path is safer and no longer leaves consumed
  uploads in the active inbox, but the live Algolia tenant still has no real
  queued GA / Looker demand export and GA4 remains unconfigured. The next
  production-validating step is to provide or connect real analytics data,
  run `run_argus_demand_intake.py`, and verify that demand signals move from
  upload/import into `demand_signals`, the product-market replay, the data-plane
  manifest, and the public cockpit.

## 2026-07-12 Manual Demand Intake History Slice

Problem:

- The Hermes/admin demand-intake control wrote durable attempt summaries under
  `work_root/{tenant}/demand-intake-runs/{run}/demand-intake-summary.json`.
- The manual/operator demand import fast lane wrote only the public
  `out/argus-demand-intake.json` sidecar.
- That meant an operator could upload demand and refresh Argus, but the admin
  "Argus demand intake attempts" history would not necessarily show that manual
  import path as a recorded attempt.

Repair:

- Added a demand-intake history writer to `scripts/import_demand_and_refresh.py`.
- Successful manual/queued demand import refreshes now write a durable summary
  to `work_root/{tenant}/demand-intake-runs/{timestamp}/demand-intake-summary.json`.
- The public `out/argus-demand-intake.json` sidecar now carries a
  `summary_path` pointing to that durable history summary.
- `DemandIntakeHistoryStore` can now read manual import/refresh attempts and
  show them beside Hermes-triggered demand-intake attempts.

Verification:

```text
red before history patch:
tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_records_manual_import_in_demand_intake_history
failed with KeyError: demand_intake_history

focused history regression:
1 passed

import fast-lane suite:
12 passed

local affected suite:
30 passed, 2 deselected, 1 warning

full local suite:
1057 passed, 23 deselected, 1 warning

remote backup:
/root/.hermes/backups/cios-demand-intake-history-20260712T131855Z.tgz

remote affected suite:
30 passed, 2 deselected, 1 warning

remote full suite:
1056 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

live demand-intake history:
attempt_count=1
latest.status=blocked_missing_demand_source
latest.next_hermes_action=configure_ga4_or_upload_demand_export
latest.summary_path=/tmp/cios-product-market/algolia/demand-intake-runs/20260712T084701Z/demand-intake-summary.json
```

Remaining blocker:

- Demand intake attempts are now auditable across both Hermes-triggered and
  manual import paths, but Algolia still has no real inward-demand rows. The
  system still needs a real GA4 connector or GA / Looker export to validate
  the full path from demand evidence to recommendations and UI.

## 2026-07-12 Hermes/Admin Demand Intake History Recording and Latest-Run Repair

Problem:

- The Hermes daily wrapper and admin refresh could produce
  `out/argus-demand-intake.json`, but blocked scheduled/admin attempts were not
  guaranteed to leave a durable run-history copy.
- Live validation exposed a second defect: the public data-plane manifest
  pointed at the fresh demand-intake attempt, while `DemandIntakeHistoryStore`
  reported an older compact run id as `latest`.
- Root cause: the history reader sorted mixed timestamp formats as raw strings.
  Compact run ids like `20260712T084701Z` sort after ISO values like
  `2026-07-12T13:50:23Z` lexicographically even when they are older.

Repair:

- Added `--record-history` to `scripts/run_argus_demand_intake.py`.
- Admin refresh and the Hermes daily wrapper now call the demand-intake
  coordinator with `--record-history`.
- The history payload now includes `generated_at`, `summary_path`, and
  `run_output_dir` and is written to both the public sidecar and the durable
  history location.
- The package preflight contract now rejects wrappers missing
  `--record-history`.
- `DemandIntakeHistoryStore` now sorts demand-intake attempts by parsed UTC time
  across both ISO `generated_at` values and compact run ids, including duplicate
  compact ids with suffixes.

Verification:

```text
red regression before sort repair:
tests/admin/test_demand_intake.py::test_demand_intake_history_sorts_mixed_generated_at_and_run_id_formats
failed because the older compact run id was reported as latest

focused local regression after repair:
1 passed

local affected suite:
155 passed, 1 warning

full local suite:
1061 passed, 23 deselected, 1 warning

remote backup:
/root/.hermes/backups/cios-demand-intake-history-sort-20260712T1359Z.tgz

remote focused regression:
1 passed

remote affected suite:
155 passed, 1 warning

remote full suite:
1060 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

production admin refresh:
status=published
publish=published
sidecars:
  demand_intake=2
  data_plane_manifest=0
  demand_readiness=0
  attach_demand_readiness=0
  operator_handoff=0
  attach_operator_handoff=0
  product_muscle_work_queue=0
  evidence_work_queue=0

live public manifest:
manifest_status=blocked_on_evidence
manifest_generated_at=2026-07-12T13:55:25.594980Z
next_hermes_action=configure_ga4_or_upload_demand_export
audience_demand_status=blocked_missing_demand_source
audience_demand_blocks_action=True
demand_intake_status=blocked_missing_demand_source
demand_intake_exit_code=2
demand_intake_mode=blocked
demand_intake_next_action=configure_ga4_or_upload_demand_export
demand_intake_summary_path=/tmp/cios-product-market/algolia/demand-intake-runs/20260712T135523Z/demand-intake-summary.json
dashboard_generated_at=2026-07-12T13:55:21.815389Z
dashboard_schema=24

live durable demand-intake history:
attempt_count=3
latest_status=blocked_missing_demand_source
latest_exit_code=2
latest_mode=blocked
latest_generated_at=2026-07-12T13:55:23.376745Z
latest_summary_path=/tmp/cios-product-market/algolia/demand-intake-runs/20260712T135523Z/demand-intake-summary.json

live dashboard click validation:
PASS dashboard_click_validation
```

Remaining blocker:

- This slice makes the blocked inward-demand workflow observable and durable.
  It does not create real inward-demand intelligence by itself. The audience
  demand plane remains correctly blocked until GA4/Looker data is connected or
  uploaded and the import path produces real demand rows for Argus to synthesize
  against product muscle and competitor conversation.

## 2026-07-12 Demand Source Contract Slice

Problem:

- The inward-demand plane could say "configure GA4 or upload a GA / Looker
  export," but Hermes did not have a durable, tenant-scoped source contract
  that named the expected demand lanes, their owners, cadence, landing zones,
  and readiness state.
- That made the blocker too vague. Argus could say demand was missing, but it
  could not explain which demand sources existed, which were ready, and which
  configuration path was blocking the current run.

Repair:

- Added `src/cios/admin/demand_sources.py` as the CI-OS package-local demand
  source contract builder. Hermes core was not touched.
- `scripts/export_argus_demand_readiness.py` now writes
  `work_root/{tenant}/demand-source-contract.json` on each readiness run.
- The contract records:
  - `manual_looker_export` with owner `operator`, cadence
    `operator_uploaded_or_daily_when_queued`, landing zone, manifest path,
    accepted suffixes, inbox counts, and status.
  - `ga4_connector` with owner `Hermes`, cadence `daily_when_configured`,
    setup requirements, windows, metric, dimensions, output name, and status.
- `scripts/check_argus_demand_source_gate.py` now includes the source-contract
  status, source ids, and ready-source count in gate output.
- `scripts/export_argus_data_plane_manifest.py` now carries
  `demand_source_contract` inside `planes.audience_demand.details` and mirrors
  the source-contract status onto demand blockers.
- The admin run console now shows a "Demand source contract" table in the
  demand imports section so the operator can see the two inward-demand lanes
  and why neither is currently ready.

Verification:

```text
red focused tests before implementation:
6 failed because demand_source_contract was missing from readiness, gate,
manifest, and admin HTML.

focused local after implementation:
6 passed, 1 warning

local affected suite:
172 passed, 1 warning

full local suite:
1061 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-source-contract-20260712T1415Z.tgz

remote focused suite:
6 passed, 1 warning

remote affected suite:
172 passed, 1 warning

remote full suite:
1060 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

production admin refresh:
status=published
publish=published
sidecars:
  demand_intake=2
  data_plane_manifest=0
  demand_readiness=0
  attach_demand_readiness=0
  operator_handoff=0
  attach_operator_handoff=0
  product_muscle_work_queue=0
  evidence_work_queue=0

live public manifest:
manifest_status=blocked_on_evidence
manifest_generated_at=2026-07-12T14:08:11.355242Z
next_hermes_action=configure_ga4_or_upload_demand_export
audience_demand_status=blocked_missing_demand_source
audience_demand_blocks_action=True
demand_source_contract_status=blocked_no_ready_source
demand_source_contract_ready_source_count=0
demand_source_contract_source_ids=manual_looker_export,ga4_connector
demand_source_contract_path=/tmp/cios-product-market/algolia/demand-source-contract.json
demand_intake_status=blocked_missing_demand_source
demand_intake_exit_code=2
dashboard_generated_at=2026-07-12T14:08:07.301617Z
dashboard_schema=24

durable demand-source contract:
contract_exists=True
contract_status=blocked_no_ready_source
ready_source_count=0
source_ids=manual_looker_export,ga4_connector
manual_status=waiting_for_upload
ga4_status=disabled
secret_values_included=False

live dashboard click validation:
PASS dashboard_click_validation

localhost admin after cios-admin.service restart:
active
Demand source contract
Status: blocked_no_ready_source · Ready sources: 0/2
Manual GA / Looker export · waiting_for_upload
GA4 API export · disabled
```

Remaining blocker:

- The system now has a durable demand-source contract and can explain the
  inward-demand blocker precisely, but it still has no real Algolia GA4/Looker
  demand evidence. The next real intelligence step is to either upload a real
  GA / Looker export into the manual landing zone or configure the GA4 connector
  so this source contract moves from `blocked_no_ready_source` to `ready` and
  then `processed_current_demand`.

## 2026-07-12 Manual Demand Import Archive-Before-Sidecars Slice

Problem:

- The manual GA / Looker import fast lane persisted demand, refreshed Argus,
  rerendered dashboard artifacts, and then generated post-run readiness,
  operator handoff, and data-plane manifest sidecars before archiving the
  consumed upload out of the active drop folder.
- That ordering meant the generated demand-source contract could observe the
  consumed file as still queued, making the contract stale or misleading.
- It also meant a post-rerender sidecar failure could leave already-persisted
  demand in the active inbox, creating duplicate reprocessing risk.

Repair:

- Moved consumed-upload archiving to happen immediately after successful core
  persist/refresh/rerender and before post-rerender sidecars are generated.
- Kept the existing safety behavior that files are not archived if core refresh
  fails.
- Publish and non-publish paths now only archive if an earlier successful
  rerender path has not already archived.
- Added regressions proving:
  - post-rerender sidecars run only after the consumed upload has left the
    active inbox;
  - the real demand-readiness exporter writes a source contract showing
    `processed_current_demand`, `manual_looker_export=waiting_for_upload`,
    and `ready_source_count=0` after a consumed manual import.

Verification:

```text
red regression before repair:
tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_generates_post_rerender_artifacts_after_archive
failed because sidecars observed the active drop file still present

local import fast-lane suite:
14 passed

local affected suite:
171 passed, 1 warning

full local suite:
1063 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-import-archive-before-sidecars-20260712T1425Z.tgz

remote import fast-lane suite:
14 passed

remote affected suite:
171 passed, 1 warning

remote full suite:
1062 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

production admin refresh:
status=published
publish=published
sidecars:
  demand_intake=2
  data_plane_manifest=0
  demand_readiness=0
  attach_demand_readiness=0
  operator_handoff=0
  attach_operator_handoff=0
  product_muscle_work_queue=0
  evidence_work_queue=0

remote sandbox manual-import drill:
status=refreshed
archive_count=1
contract_status=processed_current_demand
ready_source_count=0
manual_status=waiting_for_upload
manual_inbox_count=0
drop_file_exists=false

live public manifest:
manifest_status=blocked_on_evidence
manifest_generated_at=2026-07-12T14:17:24.965900Z
next_hermes_action=configure_ga4_or_upload_demand_export
audience_demand_status=blocked_missing_demand_source
audience_demand_blocks_action=True
demand_source_contract_status=blocked_no_ready_source
demand_source_contract_ready_source_count=0
dashboard_generated_at=2026-07-12T14:17:21.190540Z
dashboard_schema=24

live dashboard click validation:
PASS dashboard_click_validation
```

Remaining blocker:

- The manual import lane is now safer and the source contract is generated from
  the post-consumption state. The live Algolia tenant still needs a real GA /
  Looker upload or GA4 connector configuration before this path can import real
  demand evidence into the production dashboard.

## 2026-07-12 Zero-Demand Import Gate Slice

Problem:

- The inward-demand importer treated GA / Looker rows with a valid topic,
  period, and `0` metric value as normalized demand signals.
- That is not intelligence. A zero-value row may be useful as a skipped
  diagnostic, but it should not be persisted into the demand ledger or used by
  Argus as evidence that a market topic has active audience demand.
- This was the same class of flaw as the product-surface zero-row retry issue:
  technically shaped output could be promoted even when it carried no useful
  signal.

Repair:

- Added importer-level guards for both already-normalized demand rows and raw
  GA / Looker page rows.
- Rows with a non-positive metric now produce a skipped-row diagnostic:
  `reason=non_positive_metric`, `missing_fields=["value"]`.
- `DemandImportStore.prepare()` now inherits the stricter contract through
  `diagnose_looker_rows()`: zero-demand files become `status=empty`, not
  `status=ready`, and do not create payload files for persistence.
- This stays inside the CI-OS extension package. Hermes core was not touched.

Verification:

```text
red regression before repair:
tests/intelligence/test_importers.py::test_already_normalized_looker_rows_skip_when_value_is_zero
failed because the row was normalized with value "0"

tests/intelligence/test_importers.py::test_raw_looker_page_rows_skip_when_metric_is_zero
failed because the raw GA / Looker row was normalized with value 0.0

local importer suite:
16 passed

local affected demand suite:
26 passed

full local suite:
1105 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-zero-demand-import-gate-20260712T190259Z.tgz

remote importer suite:
16 passed

remote affected demand suite:
26 passed

remote full suite:
1104 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote sandbox zero-demand import drill:
file_status=empty
ready_count=0
normalized_row_count=0
skipped_row_count=1
skip_reason=non_positive_metric
```

Remaining blocker:

- The importer is now stricter about fake demand, but the live Algolia tenant
  still needs real GA / Looker data or GA4 connector credentials before Argus
  can merge inward demand with outward competitor moves at production quality.

## 2026-07-12 Demand Volume Quality Gate Slice

Problem:

- The product-market brain treated demand as "rising" when `change_pct >= 5%`
  without requiring enough audience volume.
- That meant a tiny baseline, for example `3 engaged sessions` growing `+90%`,
  could become demand-backed intelligence and trigger an actionable product or
  PMM recommendation.
- This is not a trustworthy semantic layer. Percentage movement without volume
  is a watch signal, not strategic demand.

Repair:

- Added shared demand-quality gate:
  - `DEMAND_CHANGE_FLOOR = 0.05`
  - `DEMAND_VALUE_FLOOR = 50.0`
  - `is_rising_demand_signal()` requires both floors.
- Wired the shared rule into:
  - product-market synthesizer action promotion;
  - product-feature comparison matrix demand-backed rows;
  - conversion diagnostics;
  - demand read;
  - demand-to-recommendation trace;
  - historical window comparison.
- Added regressions proving tiny high-growth demand remains watch-mode and
  does not produce an actionable recommendation or demand-backed product gap.
- This stays inside the CI-OS extension package. Hermes core was not touched.

Verification:

```text
red regressions before repair:
tests/intelligence/test_product_market_synthesizer.py::test_tiny_rising_demand_does_not_promote_action
failed because the synthesizer returned verdict=actionable

tests/intelligence/test_feature_matrix.py::test_product_feature_comparison_does_not_treat_tiny_high_growth_as_demand_backed
failed because demand_backed_count was 1

tests/intelligence/test_runner.py::test_run_product_market_payload_does_not_promote_tiny_high_growth_demand
failed because the runner returned verdict=actionable

local focused brain-gate suite:
37 passed

local intelligence suite:
90 passed

full local suite:
1108 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-volume-quality-gate-20260712T191032Z.tgz

remote focused brain-gate suite:
37 passed

remote intelligence suite:
90 passed

remote full suite:
1107 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote sandbox tiny-demand synthesis drill:
verdict=watch
pattern_count=1
recommendation_count=0
rising_demand_signal_count=0
demand_trace_status=no_rising_demand
```

Remaining blocker:

- This improves the brain's honesty, but the live tenant still lacks real
  current GA / Looker demand evidence. Once real demand is connected, the next
  quality gate should make thresholds tenant-configurable instead of fixed
  constants.

## 2026-07-12 Tenant Demand Threshold Config Slice

Problem:

- The previous demand-quality gate was correct but hardcoded:
  `change_floor=0.05`, `value_floor=50.0`.
- That protected Argus from statistical dust, but it also made the threshold
  impossible for Hermes/CI-OS to tune per tenant, segment, or analytics
  maturity level.
- A trustworthy CI operating system needs the threshold contract to be explicit
  in the run payload and summary, not hidden in package constants.

Repair:

- Added `DemandQualityConfig` to the CI-OS intelligence package.
- Added `demand_quality` to `ProductMarketRunPayload`.
- Added `demand_quality` to `ProductMarketRunSummary` so each run records the
  exact thresholds Argus used.
- Threaded the config through:
  - product-market action synthesis;
  - ledger refresh;
  - feature comparison matrix;
  - conversion diagnostics;
  - demand read;
  - demand-to-recommendation trace;
  - historical window comparison.
- Added CLI flags:
  - `scripts/build_product_market_payload.py --demand-change-floor --demand-value-floor`
  - `scripts/run_product_market_intelligence.py --demand-change-floor --demand-value-floor`
  - `scripts/refresh_product_market_from_ledger.py --demand-change-floor --demand-value-floor`
- This stays inside the CI-OS extension package. Hermes core was not touched.

Verification:

```text
red regressions before repair:
tests/intelligence/test_runner.py::test_run_product_market_payload_uses_payload_demand_quality_thresholds
failed because payload thresholds were ignored and verdict stayed watch

tests/scripts/test_build_product_market_payload.py::test_build_product_market_payload_script_writes_demand_quality_config
failed because the builder script rejected --demand-change-floor/--demand-value-floor

local focused tests:
27 passed

local intelligence + runner script tests:
103 passed

local payload-builder smoke:
{"change_floor": 0.03, "value_floor": 25.0}

full local suite:
1110 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-threshold-config-20260712T192054Z.tgz

remote focused tests:
27 passed

remote payload-builder smoke:
{"change_floor": 0.03, "value_floor": 25.0}

remote intelligence + runner script tests:
103 passed

remote full suite:
1109 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote synthesis threshold drill:
default:
  demand_quality={"change_floor": 0.05, "value_floor": 50.0}
  verdict=watch
  recommendation_count=0
  rising_demand_signal_count=0
lowered:
  demand_quality={"change_floor": 0.05, "value_floor": 2.0}
  verdict=actionable
  recommendation_count=1
  rising_demand_signal_count=1
```

Remaining blocker:

- The threshold contract is now configurable and recorded per run. The live
  tenant still needs real current GA / Looker data or GA4 connector
  credentials before Argus can produce production-quality inward-demand
  intelligence.

## 2026-07-12 Demand Threshold Orchestration Slice

Problem:

- Demand thresholds were configurable in the isolated product-market payload,
  runner, and ledger-refresh scripts, but Hermes-facing orchestration paths did
  not pass the config through.
- That meant daily cron, manual demand import, demand-intake coordination, and
  admin repair/refresh flows could silently fall back to package defaults even
  when an operator configured tenant-specific thresholds.
- This is exactly the kind of hidden drift that makes Argus appear flaky: two
  valid-looking refresh paths can produce different actionability decisions
  over the same evidence.

Repair:

- Added env-driven threshold propagation for Hermes daily product-market
  orchestration:
  - `CIOS_PRODUCT_MARKET_DEMAND_CHANGE_FLOOR`
  - `CIOS_PRODUCT_MARKET_DEMAND_VALUE_FLOOR`
  - fallback aliases `CIOS_DEMAND_CHANGE_FLOOR` and `CIOS_DEMAND_VALUE_FLOOR`.
- Daily cron now passes the threshold flags to both
  `build_product_market_payload.py` and `refresh_product_market_from_ledger.py`.
- Manual demand import now accepts `--demand-change-floor` and
  `--demand-value-floor` and forwards them into ledger refresh.
- `run_argus_demand_intake.py` now accepts the same flags and forwards them to
  the demand import fast lane.
- Admin demand refresh, GA4 refresh, demand intake, and product-surface repair
  refresh now share one env parser and pass `demand_quality` to their runners
  only when configured.
- Default admin runners apply the same config into
  `run_product_market_ledger_refresh()` and `run_product_market_payload()`.
- Hermes core was not touched; this remains inside the CI-OS extension
  package.

Verification:

```text
red regressions before repair:
tests/scripts/test_daily_run.py::test_product_market_chain_runs_plan_execute_payload_and_runner
failed because daily payload and ledger-refresh commands omitted demand flags

tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_invokes_refresh_and_rerender_after_prepare
failed because the manual CLI rejected --demand-change-floor/--demand-value-floor

tests/scripts/test_import_demand_and_refresh.py::test_import_demand_and_refresh_persists_prepared_demand_before_refresh
failed because import_demand_exports() did not accept threshold args

tests/admin/test_app.py::test_json_api_prepares_demand_and_refreshes_argus_in_one_operator_action
failed because admin demand refresh did not pass demand_quality

tests/admin/test_app.py::test_admin_default_ledger_refresh_runner_reads_demand_quality_env
failed because the default admin runner did not pass demand_quality

tests/admin/test_app.py::test_json_api_runs_product_surface_repair_with_bounded_inputs
failed because product-surface repair refresh did not pass demand_quality

local targeted green:
9 passed

local affected suites:
101 passed in tests/scripts/test_daily_run.py
99 passed in tests/scripts/test_import_demand_and_refresh.py,
tests/scripts/test_run_argus_demand_intake.py, and tests/admin/test_app.py

local compile:
scripts/daily_production_run.py
scripts/import_demand_and_refresh.py
scripts/run_argus_demand_intake.py
src/cios/admin/app.py
src/cios/admin/demand_intake.py

local full suite:
1112 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-threshold-orchestration-20260712T193854Z.tgz

remote compile:
remote_compile=pass

remote targeted green:
9 passed, 1 warning

remote affected admin/manual-intake suite:
99 passed, 1 warning

remote daily suite:
101 passed

remote full suite:
1111 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote runtime env smoke:
{"change_floor": 0.03, "value_floor": 25.0}
```

Remaining blocker:

- Threshold propagation is now consistent across the tested Hermes/admin/manual
  paths. This still does not make the live Argus read production-quality until
  real current inward-demand data is connected and the full daily job produces
  an evidence-complete publishable run.

## 2026-07-12 Run-Native Monitoring Agenda Slice

Problem:

- The product-market runner had a durable decision read and scorecard-backed
  recommendations, but the run did not yet emit a first-class monitoring
  agenda for Hermes and Argus.
- That left a gap between "what did Argus learn today?" and "what should
  Hermes collect, recheck, or learn next?" The UI could describe blockers, but
  the brain record itself did not make the next sweep operational.

Repair:

- Added `NextMonitoringAction` to the CI-OS intelligence runner.
- Added `next_monitoring_actions` to `ProductMarketIntelligenceBrief`, persisted
  inside `product_market_run_intelligence.intelligence_brief` with the rest of
  the durable Argus brain record.
- The runner now derives next monitoring actions from the same evidence planes
  used for synthesis:
  - missing demand after a qualified pattern creates a critical Hermes action
    to collect GA / Looker evidence for the specific capability;
  - demand topics missing product proof create product-reality collection
    actions;
  - demand topics missing conversation evidence create market-conversation
    scan actions;
  - actionable recommendations still create source-coverage and Argus learning
    follow-ups, so one run is not treated as permanent truth;
  - quiet runs produce a source-coverage verification action instead of
    pretending the market was silent.
- Exposed `next_monitoring_actions` in the Hermes-facing Argus data-plane
  manifest. The manifest reads the agenda from either the run object or nested
  `intelligence_brief`, keeping it compatible with existing dashboard payloads.
- Hermes core was not touched; the change stays inside the CI-OS package and
  package sidecars.

Verification:

```text
red regression before repair:
tests/intelligence/test_runner.py::test_run_product_market_payload_brief_instructs_hermes_to_collect_missing_demand
failed because ProductMarketIntelligenceBrief had no next_monitoring_actions

red manifest contract before repair:
tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_explains_brain_muscle_and_blocks_action_without_demand
failed because the manifest did not expose next_monitoring_actions

focused runner agenda tests:
2 passed, 20 deselected

runner suite:
22 passed

intelligence + manifest suites:
105 passed

product-market persistence, dashboard-state, and package-contract tests:
114 passed

full local suite:
1114 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

compile:
src/cios/intelligence/runner.py
scripts/export_argus_data_plane_manifest.py
tests/intelligence/test_runner.py
tests/scripts/test_export_argus_data_plane_manifest.py
```

Remaining blocker:

- The package can now tell Hermes what to monitor next after each run. The live
  tenant still needs current inward-demand data and an evidence-complete full
  daily job before Argus can produce production-quality recommendations.

## 2026-07-12 Monitoring Agenda Dashboard Surfacing Slice

Problem:

- `next_monitoring_actions` existed in the durable Argus run brief and
  Hermes-facing data-plane manifest, but the dashboard state contract still
  treated it as nested brief detail.
- That meant public/admin surfaces could still show a read without explicitly
  showing what Hermes should monitor next. The system had the brain output, but
  the cockpit did not expose the operating agenda.

Repair:

- Added `next_monitoring_actions` as a first-class field on
  `ProductMarketRunStatus`.
- Added a model promotion validator so the dashboard state lifts
  `intelligence_brief.next_monitoring_actions` into
  `product_market_run.next_monitoring_actions`.
- Updated the cockpit run trace to render a compact `Hermes next monitor` row
  showing plane, priority, instruction, and reason.
- Kept the UI change inside the existing Hermes / Argus run trace instead of
  adding another dashboard card.
- Hermes core was not touched.

Verification:

```text
red publisher contract before repair:
tests/dashboard/test_publisher.py::test_to_json_dict_serializes_product_market_run_trace
failed because product_market_run.next_monitoring_actions was missing

red renderer contract before repair:
tests/dashboard/test_cockpit_renderer.py::test_cockpit_run_trace_renders_argus_decision_read
failed because the run trace did not render "Hermes next monitor"

focused green:
2 passed

dashboard state/publisher/renderer:
93 passed

combined intelligence, manifest, and dashboard smoke:
127 passed

full local suite:
1114 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

compile:
src/cios/dashboard/types.py
src/cios/dashboard/cockpit_renderer.py
tests/dashboard/test_state_builder.py
tests/dashboard/test_publisher.py
tests/dashboard/test_cockpit_renderer.py
```

Remaining blocker:

- The cockpit now shows what Hermes should monitor next when the run payload
  contains `next_monitoring_actions`. Live production still needs a fresh
  evidence-complete run with current inward-demand data before the public read
  can be called production-quality.

## 2026-07-12 Public Run Status Monitoring Agenda Slice

Problem:

- The refreshed Hermes-facing data-plane manifest contained
  `next_monitoring_actions`, and the refreshed dashboard JSON carried the same
  agenda, but the public-safe latest-run status stripped it out.
- That meant production could honestly say the run was blocked on evidence, but
  it still did not tell an operator what Hermes/Argus should monitor next.

Repair:

- Added a public-safe sanitizer for `manifest.next_monitoring_actions` in
  `scripts/export_public_run_status.py`.
- The public status now exposes owner, plane, priority, instruction, reason,
  source families, and `evidence_url_count`.
- Raw evidence URLs, local artifact paths, and unrecognized internal fields are
  intentionally excluded from the public payload.
- Malformed action rows missing owner, plane, priority, instruction, or reason
  are dropped.
- Hermes core was not touched.

Verification:

```text
red regression before repair:
tests/scripts/test_export_public_run_status.py::test_public_run_status_exposes_sanitized_next_monitoring_actions
failed with KeyError: 'next_monitoring_actions'

focused public-status + manifest + dashboard smoke:
21 passed

local full suite:
1115 passed, 23 deselected

local compile:
python3 -m py_compile scripts/export_public_run_status.py tests/scripts/test_export_public_run_status.py

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote compile:
scripts/export_public_run_status.py
tests/scripts/test_export_public_run_status.py

remote public-status + manifest suites:
18 passed

remote full suite:
1114 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-public-status-next-actions-before-20260712T202337Z.tgz

live public status:
https://ci.chowmes.com/data/argus-latest-run-status.json
generated_at=2026-07-12T20:25:30.622786Z
status=blocked_on_evidence
publish_status=blocked
next_actions=1
top_action=Collect GA / Looker demand evidence for Support before promoting this market movement into a recommendation.
path_leak=False
```

Remaining blocker:

- The current live run is still blocked on audience-demand evidence. The next
  system slice needs to make the GA / Looker demand import path usable and
  verifiable so Argus can join inward demand with product reality and market
  conversation rather than staying in watch mode.

## 2026-07-12 Demand Readiness Operator Action Repair

Problem:

- Production GA4 readiness is currently disabled: no GA4 property id, no
  credentials, no source URL, and no queued manual demand export.
- The demand readiness artifact correctly reported
  `blocked_missing_demand_source`, but its operator actions still included
  `Run GA4 export now`.
- That made the handoff semantically wrong: Hermes/Argus was telling the
  operator to run an export that the same artifact knew could not run.

Repair:

- Updated `scripts/export_argus_demand_readiness.py` so blocked demand-source
  states expose `Configure GA4 connector` instead of `Run GA4 export now`.
- Ready GA4 states still expose `Run GA4 export and refresh Argus` and
  `Run GA4 export now`.
- The public-safe latest-run status now carries the corrected operator command
  through the demand readiness artifact, operator handoff, data-plane manifest,
  and public status exporter.
- Hermes core was not touched.

Verification:

```text
red regression before repair:
tests/scripts/test_export_argus_demand_readiness.py::test_export_argus_demand_readiness_creates_manual_drop_folder
failed because operator actions were:
Download demand plan template, Download demand template, Open demand admin, Run GA4 export now

local demand readiness + admin GA4 controls:
9 passed

local affected suite:
113 passed

local full suite:
1115 passed, 23 deselected

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote affected suite:
113 passed, 1 warning

remote full suite:
1114 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-readiness-actions-before-20260712T202854Z.tgz

live public status:
https://ci.chowmes.com/data/argus-latest-run-status.json
generated_at=2026-07-12T20:30:13.258184Z
status=blocked_on_evidence
publish_status=blocked
next_actions=1
operator_commands=Download demand plan template, Download demand template, Open demand admin, Configure GA4 connector
has_run_ga4_now=False
path_leak=False
```

Remaining blocker:

- CI-OS still needs a real inward-demand source configured or uploaded. Until
  that happens, Argus correctly remains in `watch` / blocked mode instead of
  issuing product, marketing, or sales recommendations as if audience demand
  had been proven.

## 2026-07-12 Registry Coverage Manifest Truth Repair

Problem:

- The public latest-run status top-level `source_coverage` correctly reported
  `48` active sources, `48` checked sources, and `5` failed sources.
- The nested Hermes-facing `registry_coverage` plane in the same payload still
  reported `0/0/0` because the data-plane manifest only handled the older
  summary-shaped `source_health` payload and not the current list-shaped source
  health rows.
- That created a direct semantic contradiction in the run truth: the same
  artifact said sources were fully checked and not checked at all.

Repair:

- Updated `scripts/export_argus_data_plane_manifest.py` so `_source_health`
  accepts both summary-shaped and list-shaped dashboard `source_health`.
- For list-shaped rows, it counts active sources, checked active sources, and
  checked active sources whose latest event is not `ok` / `success`.
- The registry coverage plane now correctly marks the run `degraded` when
  active checked sources include failures.
- Hermes core was not touched.

Verification:

```text
red regression before repair:
tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_counts_list_shaped_source_health_rows
failed because registry_coverage.status was present instead of degraded

local manifest/public-status affected suite:
27 passed

local full suite:
1116 passed, 23 deselected

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote affected suite:
27 passed

remote full suite:
1115 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-manifest-source-health-list-before-20260712T203456Z.tgz

live public status:
https://ci.chowmes.com/data/argus-latest-run-status.json
generated_at=2026-07-12T20:35:48.383395Z
status=blocked_on_evidence
source_coverage=48 active, 48 checked, 5 failed
registry_coverage=degraded, 48 active, 48 checked, 5 failed, 27 monitored competitors
path_leak=False
```

Remaining blocker:

- The registry/source coverage plane is now truthful. The primary system
  blocker remains inward demand: either configure GA4 with a real property and
  credentials, or upload a GA / Looker export through the admin demand-import
  path so Argus can leave watch mode with evidence.

## 2026-07-12 Demand Upload Immediate Validation Slice

Problem:

- The manual GA / Looker demand upload route queued files, but its response did
  not tell the operator whether the uploaded file had usable demand rows.
- That made the inward-demand path too opaque: an operator could upload a file,
  see `queued_for_next_sweep`, and only later discover that Argus could not use
  it.

Repair:

- Extended `DemandImportUploadResult` with immediate preview diagnostics:
  `preview_status`, `raw_row_count`, `normalized_row_count`,
  `skipped_row_count`, `topics`, and `error`.
- `DemandImportStore.upload()` now writes the file, runs the same preview logic
  used by the demand-import status endpoint, and returns the validation summary
  in the upload response.
- Existing queue semantics remain unchanged: valid uploads are still queued for
  the next demand refresh, but the operator now gets immediate evidence that the
  file is ready, empty, or invalid.
- Hermes core was not touched.

Verification:

```text
red regression before repair:
tests/admin/test_app.py::test_json_api_uploads_argus_demand_export_to_tenant_drop_folder
failed with KeyError: 'preview_status'

local demand/admin affected suite:
102 passed, 2 deselected

local full suite:
1116 passed, 23 deselected

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote affected suite:
102 passed, 2 deselected, 1 warning

remote full suite:
1115 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-upload-preview-before-20260712T204030Z.tgz

remote admin route smoke:
POST /api/tenants/algolia/argus/demand-imports
status_code=200
preview_status=ready
raw_row_count=1
normalized_row_count=1
skipped_row_count=0
topics=AI Shopping Agent
temporary upload removed after smoke
```

Remaining blocker:

- The manual demand path is now more inspectable, but no real Algolia demand
  export is currently queued. Argus still needs either a real upload or GA4
  configuration before it can promote product-market movement into evidence-
  backed recommendations.

## 2026-07-12 Product-Muscle Work-Order Status Slice

Problem:

- The live run had a real product-muscle limiter: Klevu had active product
  surfaces but no extracted feature evidence.
- The data-plane manifest exposed only counts and work item ids in the
  `product_reality` plane, which made the limitation technically visible but
  not operationally useful.
- The public latest-run status could show the plane as limited, but it did not
  carry the product-muscle work order needed for Hermes, Argus Command, or an
  admin UI to act on the limiter while the demand plane waits for GA / Looker.

Repair:

- `scripts/export_argus_data_plane_manifest.py` now embeds a sanitized
  `product_muscle_work_queue` summary in the `product_reality` plane details.
- The summary carries status, work item counts, affected company, severity,
  title, next step, operator surface, and safe operator-command metadata.
- `scripts/export_public_run_status.py` now promotes the same work order into
  the public-safe `product_reality` plane while stripping admin hrefs, local
  paths, artifact refs, and debug fields.
- Hermes core was not touched.

Verification:

```text
red regressions before repair:
tests/scripts/test_export_argus_data_plane_manifest.py::test_data_plane_manifest_exposes_product_muscle_work_order_for_limiting_items
failed with KeyError: 'product_muscle_work_queue'

tests/scripts/test_export_public_run_status.py::test_public_run_status_exposes_sanitized_product_muscle_work_order
failed with KeyError: 'product_muscle_work_queue'

local focused regressions:
2 passed

local affected exporter suites:
26 passed

local full suite:
1118 passed, 23 deselected

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote focused regressions:
2 passed

remote affected exporter suites:
26 passed

remote full suite:
1117 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-product-muscle-work-order-status-before-20260712T205412Z.tgz

live public-safe status:
generated_at=2026-07-12T20:56:52.097666Z
status=blocked_on_evidence
next_hermes_action=configure_ga4_or_upload_demand_export
product_status=limited_by_product_surface_evidence
queue_status=limited
queue_items=1
first_title=Klevu has product surfaces but no feature evidence
operator_commands=Open product surfaces, Refresh Argus from evidence ledger
path_leak=False
```

Remaining blocker:

- Product-muscle operator work is now visible and actionable, but the overall
  run still cannot promote recommendations until real Algolia demand evidence
  arrives through GA4 configuration or a GA / Looker export upload.

## 2026-07-12 Empty Product-Surface Repair Action Slice

Problem:

- Product-surface execution already distinguished empty Scout outputs from
  command failures, and `run_product_surface_repair.py` could retry
  `empty_extraction` targets.
- The product-muscle work queue still routed empty successful extractions to
  "Open product surfaces" because it only offered "Run repair retry" when
  `failed_count > 0`.
- That meant the operator work order could describe the right failure but show
  the wrong action for zero-row Scout outputs.

Repair:

- `src/cios/admin/product_muscle_work_queue.py` now treats
  `empty_extraction` as repairable even when the failed command count is zero.
- The generated work item now posts to
  `/admin/{tenant}/argus/product-surface-repair?company_name=...&category=empty_extraction`
  for empty product-surface outputs.
- Hermes core was not touched.

Verification:

```text
red regression before repair:
tests/scripts/test_export_argus_product_muscle_work_queue.py::test_build_product_muscle_work_queue_payload_includes_product_surface_execution_trace
failed because primary_action_label was "Open product surfaces" instead of "Run repair retry"

local focused regression:
1 passed

local affected product-muscle/exporter suites:
34 passed

local full suite:
1118 passed, 23 deselected

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote focused regression:
1 passed

remote affected product-muscle/exporter suites:
34 passed

remote full suite:
1117 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-empty-extraction-repair-action-before-20260712T210000Z.tgz
```

## 2026-07-12 First-Run Product-Surface Extraction Action Slice

Problem:

- Klevu had active product surfaces but no feature evidence and no failed or
  empty Scout trace to repair.
- The product-muscle work queue therefore showed passive navigation instead of
  an operator action that actually starts the first extraction run.
- The Hermes package preflight also did not protect the new extraction control,
  admin route, planner filters, or first-run work-queue action.

Repair:

- `scripts/plan_product_surface_exports.py` now supports scoped planning with
  `--company-name`, `--company-id`, `--surface-id`, and `--limit`.
- `src/cios/admin/product_surface_extraction.py` adds the local-only admin
  control that builds a filtered Scout plan, executes it, and returns the
  product-surface execution summary.
- `src/cios/admin/app.py` exposes the first-run extraction API and admin form
  POST routes.
- `src/cios/admin/product_muscle_work_queue.py` now emits `Run surface
  extraction` as the primary POST action when a company has active product
  surfaces but no feature evidence yet.
- `scripts/verify_hermes_package_contract.py` now rejects a package missing
  the extraction control, admin route, planner filters, Scout bridge default,
  or first-run product-muscle queue action.
- Hermes core was not touched.

Verification:

```text
red package-contract regressions before verifier update:
5 failed because preflight passed packages missing the extraction control,
planner filters, Scout bridge default, work-queue action, and admin route.

local focused package-contract regressions:
6 passed

local affected product-surface/admin/package suite:
58 passed

local full suite:
1127 passed, 23 deselected

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote affected product-surface/admin/package suite:
58 passed, 1 warning

remote full suite:
1126 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-product-surface-first-run-extraction-before-20260712T211749Z.tgz

local-only admin route smoke after cios-admin restart:
POST /api/tenants/algolia/argus/product-surface-extraction with invalid body
returned HTTP 422, proving the route is loaded and validating the request model.

live public-safe status:
status=blocked_on_evidence
next_hermes_action=configure_ga4_or_upload_demand_export
product_status=limited_by_product_surface_evidence
work_item_count=1
klevu_label=Run surface extraction
klevu_method=post
klevu_route_kind=admin
path_leak=False

live first-run extraction attempt:
POST /api/tenants/algolia/argus/product-surface-extraction
company_name=Klevu
route_http_code=200
status=empty
command_status=ok
succeeded=0
failed=0
empty=1
product_row_count=0
product_plane_status=empty

live public-safe status after extraction trace refresh:
status=blocked_on_evidence
product_status=limited_by_product_surface_evidence
klevu_label=Run repair retry
klevu_method=post
klevu_route_kind=admin
path_leak=False
```

Remaining blocker:

- The product-muscle first-run action is now live and protected by package
  preflight, but overall Argus remains blocked on inward demand until GA4 is
  configured or a valid GA / Looker export is uploaded.

Candidate promotion transaction and Klevu product-muscle recovery slice,
2026-07-12:

- `scripts/execute_product_muscle_gap_discovery.py` now commits successful
  candidate writes before closing its DB connection. This fixes the live bug
  where the discovery summary reported stored candidates, but Postgres rolled
  them back on connection close.
- `scripts/promote_product_surface_candidates.py` now commits successful
  promotions. Candidate promotion can no longer return a completed summary
  while leaving rows in `candidate` status.
- `PgProductSurfaceRepository.promote_validated_candidates` now casts optional
  filters in SQL (`company_name::text`, `company_id::bigint`,
  `surface_family::text`) so the real Postgres route does not fail with
  ambiguous parameter types.
- `src/cios/admin/product_muscle_work_queue.py` now prioritizes validated
  candidate promotion before repair for any extraction failure category, not
  only `empty_extraction`.
- The same work queue now prioritizes first-run extraction when active product
  surfaces outnumber the surfaces included in the last extraction plan. This
  prevents newly promoted surfaces from being ignored while the operator keeps
  retrying an older failed docs URL.
- Hermes core was not touched.

Verification:

```text
RED regressions before fixes:
candidate discovery script completed but conn.committed=False
candidate promotion script completed but conn.committed=False
work queue preferred Run repair retry for Klevu scout_failure despite candidates
promotion SQL test failed because optional filters lacked explicit casts
work queue preferred stale repair after newly promoted active surfaces

local focused script tests:
9 passed

local affected product-surface/admin/package suite after transaction fixes:
160 passed, 1 warning

local affected product-surface/admin/package suite after queue and SQL fixes:
162 passed, 1 warning

local full suite:
1142 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote focused script tests:
9 passed

remote affected suite after transaction fixes:
160 passed, 1 warning

remote full suite after transaction fixes:
1139 passed, 1 skipped, 23 deselected, 1 warning

remote affected suite after queue and SQL fixes:
162 passed, 1 warning

remote full suite after final queue rule:
1141 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backups:
/root/.hermes/backups/cios-product-surface-candidate-transaction-before-20260712T215409Z.tgz
/root/.hermes/backups/cios-product-muscle-candidate-action-before-20260712T220000Z.tgz
/root/.hermes/backups/cios-product-surface-promotion-sql-before-20260712T220515Z.tgz
/root/.hermes/backups/cios-product-muscle-extract-promoted-before-20260712T220859Z.tgz

live Klevu candidate discovery:
empty_surface_target_count=1
heuristic_probe_count=8
validated_count=2
stored_candidate_count=2
stored candidates:
- pricing: https://klevu.com/pricing HTTP 200
- integration: https://klevu.com/integrations HTTP 200

live Postgres after candidate discovery:
Klevu product surfaces=3
- docs active https://docs.klevu.com/
- pricing candidate https://klevu.com/pricing
- integration candidate https://klevu.com/integrations

live work queue after discovery:
klevu_candidate_count=2
klevu_action_label=Promote candidate surface
klevu_action_method=post
klevu_action_href=/admin/algolia/argus/product-surface-candidates/promote?company_name=Klevu&limit=1
path_leak=False

live admin promotion route:
POST /api/tenants/algolia/argus/product-surface-candidates/promote
HTTP 200
first promotion: pricing active
second promotion: integration active
Klevu status count after promotions: active=3

live work queue after promotions:
klevu_candidate_count=0
klevu_active_count=3
klevu_planned_count=1
klevu_action_label=Run surface extraction
klevu_action_method=post
klevu_action_href=/admin/algolia/argus/product-surface-extraction?company_name=Klevu

live Klevu pricing extraction:
POST /api/tenants/algolia/argus/product-surface-extraction
surface_id=1453
HTTP 200
status=ready
command_status=ok
planned=1
succeeded=1
failed=0
empty=0
product_row_count=12
scout_paths=1
argus_refresh=True
argus_read=True

live Postgres after extraction:
klevu_product_event_count=150
klevu_feature_position_count=23
klevu_work_items=0

live public-safe status after refresh:
status=blocked_on_evidence
publish_status=blocked
product_status=present
audience_demand_status=blocked_missing_demand_source
path_leak=False
```

Remaining blocker:

- Product reality is now present for Klevu and the product-muscle blocker has
  cleared for that company. Overall Argus still cannot publish as actionable
  because the inward audience-demand plane remains
  `blocked_missing_demand_source`; GA4 must be configured or a valid GA /
  Looker export must be uploaded.

## Demand Intake Dashboard-Plan Freshness Fix, 2026-07-12

Problem:

- Product-muscle refresh could generate a current dashboard and demand
  readiness plan, but the Hermes-facing `run_argus_demand_intake.py` sidecar
  rebuilt readiness with `dashboard=None`.
- That allowed the sidecar to report `blocked_missing_demand_source` with a
  stale or empty demand collection plan even after the product-muscle layer had
  identified current topics.

Changes:

- `scripts/run_argus_demand_intake.py`
  - added `--dashboard`
  - loads the dashboard JSON
  - passes that dashboard into `build_demand_readiness_payload`
- `src/cios/admin/dashboard_refresh.py`
  - passes `--dashboard $OUT/argus-dashboard.json` into demand intake
- `deploy/cios-daily.sh`
  - passes `--dashboard $OUT/argus-dashboard.json` into the Hermes daily
    demand-intake sidecar
- Regression coverage:
  - demand-intake unit test proves dashboard-backed collection plan is preserved
  - admin refresh test proves the dashboard artifact is passed into demand
    intake
  - Hermes wrapper test proves the daily execution path passes the dashboard
    into demand intake

Verification:

```text
local RED tests before fix:
test_run_argus_demand_intake_uses_dashboard_for_fresh_collection_plan:
TypeError: run_demand_intake() got an unexpected keyword argument 'dashboard'

test_admin_dashboard_refresh_runner_rerenders_and_publishes:
AssertionError: '--dashboard' not in demand-intake command

Hermes wrapper RED before fix:
FileNotFoundError: demand-intake-dashboard-arg.txt

local focused suite after fix:
36 passed

local full suite:
1143 passed, 23 deselected, 1 warning

remote focused suite after deploy:
36 passed

remote full suite:
1142 passed, 1 skipped, 23 deselected, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-demand-intake-dashboard-before-20260712T222315Z.tgz
/root/.hermes/backups/cios-demand-intake-dashboard-wrapper-before-20260712T222716Z.tgz

live admin refresh:
status=published
rerender=0
demand_readiness=0
demand_plan_template=0
demand_intake=2
attach_demand_readiness=0
evidence_work_queue=0
product_muscle_work_queue=0
operator_handoff=0
attach_operator_handoff=0
data_plane_manifest=0

live out/argus-demand-readiness.json:
status=blocked_missing_demand_source
generated_at=2026-07-12T22:29:01.797416Z
plan_status=needs_demand_source
topic_count=12
first topics:
- Channel Assistant (AI Agent)
- Complete Discovery Plan
- Conversational Assistant (AI Agent)
- AI Feed Audits (Channel Assistant)
- Flexible Pricing

live out/argus-demand-intake.json:
status=blocked_missing_demand_source
generated_at=2026-07-12T22:29:03.626719Z
plan_status=needs_demand_source
topic_count=12
history=/tmp/cios-product-market/algolia/demand-intake-runs/20260712T222903Z/demand-intake-summary.json

live public /data/argus-data-plane-manifest.json:
status=blocked_on_evidence
generated_at=2026-07-12T22:29:06.178706Z
audience_status=blocked_missing_demand_source
demand_intake.status=blocked_missing_demand_source
demand_intake.exit_code=2
demand_intake.next_hermes_action=configure_ga4_or_upload_demand_export

live public /data/argus-latest-run-status.json:
status=blocked_on_evidence
publish_status=blocked
generated_at=2026-07-12T22:29:46.483940Z
audience_status=blocked_missing_demand_source
summary=No tenant-side demand source is ready. Configure GA4 or upload a GA / Looker export.
```

Remaining blocker:

- The inward demand plane is now truthfully blocked with the current 12-topic
  collection plan preserved. The next real product step is configuring GA4 /
  Looker ingestion or uploading a valid demand export so Argus can merge
  product-muscle truth with audience demand instead of stopping at a blocked
  evidence gate.

## GA4 Export Uses Argus Demand Plan, 2026-07-12

Problem:

- The Hermes demand-intake coordinator already passed the current Argus demand
  collection plan into GA4 export.
- The admin "Run GA4 export" and "Run GA4 export and refresh Argus" actions
  called `ga4_control.run(tenant_slug)` without the plan, so an operator-driven
  GA4 export could be broader and less aligned than the Hermes path.

Changes:

- `src/cios/admin/app.py`
  - added `demand_collection_plan_from_manifest`
  - reads `audience_demand.details.demand_collection_plan` from the current
    data-plane manifest
  - passes that plan into:
    - API `POST /api/tenants/{tenant}/argus/ga4-export`
    - API `POST /api/tenants/{tenant}/argus/ga4-export/refresh`
    - admin form `POST /admin/{tenant}/argus/ga4-export`
    - admin form `POST /admin/{tenant}/argus/ga4-export/refresh`
- `tests/admin/test_app.py`
  - added regression coverage proving the GA4 refresh route writes
    `argus-demand-plan.json`, passes `--demand-plan` into the export script, and
    carries demand-plan coverage fields back in the response.

Verification:

```text
RED before fix:
test_json_api_ga4_export_refresh_passes_argus_demand_plan_to_export_script
AssertionError: '--demand-plan' not in GA4 export command

local focused demand/admin/integration suite:
92 passed, 2 deselected, 1 warning

local data-plane/public-status suite:
28 passed

local full suite:
1144 passed, 23 deselected, 1 warning

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote backup:
/root/.hermes/backups/cios-ga4-demand-plan-guidance-before-20260712T223704Z.tgz

remote focused suite:
3 passed, 1 warning

remote Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

remote full suite:
1143 passed, 1 skipped, 23 deselected, 1 warning
```

Remaining blocker:

- GA4/Looker credentials or a valid export are still required before the
  audience-demand plane can become `processed`. This slice makes the connector
  plan-aware once credentials/export data exist.

## E2E Launch Readiness Gate, 2026-07-13

Problem:

- The user-requested E2E validation plan was missing from the CI-OS repo at
  `docs/plan/e2e-validation.md`.
- The system had many green component tests, but no single executable gate
  that combined Hermes package readiness, live dashboard click validation,
  public status, source coverage, demand evidence, product reality, and
  public-safety checks into one launch verdict.
- That made it too easy to confuse "some slices passed" with "CI-OS is
  launch-ready."

Changes:

- Added `docs/plan/e2e-validation.md` with the launch readiness contract:
  Hermes execution, frontend E2E, backend/data, competitor registry, demand
  GA4/Looker, intelligence/learning, and production acceptance gates.
- Added `scripts/check_e2e_launch_readiness.py`, which reads the public
  `argus-latest-run-status.json`, dashboard click validation log, and Hermes
  package contract log, then emits one JSON verdict.
- The gate fails if public status is blocked, source coverage is incomplete,
  source failures exceed the configured launch budget, inward demand is not
  processed, product reality is missing, dashboard click validation did not
  pass, the Hermes package contract did not pass, or public-safety redaction is
  not proven.
- Updated `scripts/verify_hermes_package_contract.py` so installed CI-OS
  packages must include both the readiness script and the E2E validation plan.
- Updated root `AGENTS.md` to stop claiming the project has no application code
  or toolchain.
- Hermes core was not touched.

Verification:

```text
RED launch-readiness tests before implementation:
5 failed because scripts/check_e2e_launch_readiness.py and
docs/plan/e2e-validation.md were missing.

focused launch-readiness tests:
5 passed

RED package-contract test before verifier update:
test_preflight_fails_when_launch_readiness_gate_missing failed because the
preflight still passed without scripts/check_e2e_launch_readiness.py.

RED package-contract test before plan-path verifier update:
test_preflight_fails_when_e2e_validation_plan_missing failed because the
preflight still passed without docs/plan/e2e-validation.md.

contract regressions after verifier update:
2 passed

affected local suite:
68 passed

local Hermes package contract:
PASS: CI-OS Hermes package contract satisfied

local full suite:
1170 passed, 23 deselected

remote deployment:
/root/.hermes/backups/cios-e2e-launch-readiness-20260713T011110Z.tgz

remote package contract:
PASS: CI-OS Hermes package contract satisfied

remote focused gate/package tests:
56 passed
```

Live gate against `https://ci.chowmes.com/`:

```text
package contract: PASS
dashboard click validation: PASS dashboard_click_validation
launch readiness: fail
checks:
  public_status_publishable=False
  source_coverage_complete=True
  source_failure_budget_ok=False
  audience_demand_processed=False
  product_reality_present=True
  dashboard_click_validation_passed=True
  hermes_package_contract_passed=True
  public_safety_ok=True
blockers:
  public_status_publishable | publish_status=blocked status=blocked_on_evidence
  source_failure_budget_ok | failed_source_count=5 max_failed_sources=0
  audience_demand_processed | audience_demand.status=blocked_missing_demand_source demand_signal_count=0
```

Deployed gate against live public status:

```text
gate_exit=2
status=fail
next_action=configure_ga4_or_upload_demand_export
source_coverage=48 active, 48 checked, 5 failed
checks:
  public_status_publishable=False
  source_coverage_complete=True
  source_failure_budget_ok=False
  audience_demand_processed=False
  product_reality_present=True
  dashboard_click_validation_passed=True
  hermes_package_contract_passed=True
  public_safety_ok=True
```

Remaining blocker:

- The launch gate is now explicit and executable, and it correctly refuses to
  call the system launch-ready. To pass, CI-OS still needs a real GA4/Looker
  demand source or valid demand export, a refreshed Argus run with processed
  demand, and either zero failed sources or a documented degradation budget.
