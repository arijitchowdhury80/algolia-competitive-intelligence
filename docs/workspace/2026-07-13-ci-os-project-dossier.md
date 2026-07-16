# CI-OS Project Dossier

Date: 2026-07-13
Status: Phase 2 staging verified; recovery still in progress
Product owner: Arijit Chowdhury
Operating agent: Argus
Runtime: Hermes / MyOS-Core
First tenant: Algolia

## Executive Position

CI-OS is approximately 35 percent complete against the original product goal. The engineering scaffold is approximately 65 percent complete, but the product does not yet deliver a reliable, evidence-backed competitive decision loop.

2026-07-16 Phase 2 update: publication integrity is now verified in staging. Candidate `11dc7df631ac84a500c833eb21659b0a98ed5cf2` produced Hermes-owned run `cios-20260716T090552Z-3890353`; strict readiness passed with `status=pass`, `exit_code=0`, `public_status_publishable=true`, source coverage `42/42`, `failed_source_count=0`, and `blockers=[]`. This proves the Phase 2 publication gate, not the whole Algolia pilot. Phase 3 product muscle still has 39 nonblocking confidence-limiting work items, and later phases still own the accepted product IA, intelligence proof, release monitoring, and pilot usage.

The system must not be called fully launch-ready for the Algolia pilot yet. Phase 2 now has a trustworthy, run-bound published decision surface, but Product Muscle, Argus intelligence proof, accepted IA, E2E UX/security validation, and the controlled pilot release remain ahead in the documented phase order.

The project has real foundations worth preserving. It also has a large amount of uncommitted, partially validated work that must be recovered into a controlled release sequence before more feature expansion.

## Product Goal

Argus should be a Hermes-native competitive strategist, not a smaller monitoring dashboard. It must merge three evidence planes:

1. Product reality: what competitors and Algolia actually shipped.
2. Market conversation: what companies, executives, analysts, and the market are saying.
3. Audience demand: what Algolia audiences are reading, searching, comparing, and responding to.

The required output is a defensible answer to:

> Across the last seven days, what did competitors ship, what did they say, what did Algolia's audience respond to, and what should Algolia do next?

Every answer must include evidence, confidence, coverage limitations, owner, urgency, and a specific next action.

## Architecture Boundary

The intended architecture remains correct:

- Hermes core owns schedules, execution, profiles, model routing, delivery, generic memory, and runtime infrastructure.
- Argus is the operating CI agent inside Hermes.
- CI-OS is an independently versioned extension package above Hermes core.
- CI-OS owns tenants, competitors, sources, evidence, intelligence, recommendations, learning, briefs, dashboard state, and admin behavior.
- Scout is the product-surface acquisition layer for changelogs, release notes, docs, pricing, integrations, APIs, and product pages.
- GA4 / Looker is the inward audience-demand layer.
- CI-OS must not modify Hermes core to solve domain problems.

The reviewed implementation follows this boundary directionally. Production ownership, package release discipline, and run identity are not yet strong enough.

## Verified Live State

Evidence was refreshed directly from Chowmes on 2026-07-13.

### Hermes run

| Item | Verified state |
|---|---|
| Job | `cios-v2-daily` |
| Schedule | `0 9 * * *`, America/New_York |
| Execution mode | Hermes no-agent script |
| Wrapper | `cios-daily.sh` |
| Latest completed schedule | 2026-07-12 09:00 ET |
| Result | Failed, exit code 1 |
| Failure | Hermes could not remove root-owned output artifacts |
| Autonomous daily loop | Not healthy |

The failure is not a cosmetic dashboard problem. Root/manual repair paths recreated root-owned files, so the Hermes runtime user could not begin the next scheduled cycle. Public artifacts may look newer than the last successful Hermes run because manual/root paths refreshed them.

### Public run status

| Item | Verified state |
|---|---|
| Status | `blocked_on_evidence` |
| Publish status | `blocked` |
| Generated at | `2026-07-13T01:51:21.937836Z` |
| Public dashboard updated | false |
| Next Hermes action | Configure GA4 or upload a demand export |

### Evidence planes

| Plane | Verified state | Meaning |
|---|---:|---|
| Monitored competitors | 27 | Registry exists and is represented publicly. |
| Active sources | 43 | Reported active in current public state. |
| Checked sources | 43 | Reported checked by a manual/root refreshed artifact, not a successful scheduled run. |
| Blocked sources | 5 | Present in the public source ledger. |
| Failed active sources | 0 | Current artifact reports none. |
| Product events | 12 | Ledger contains product evidence. |
| Current product-surface targets | 38 | Targets are registered. |
| Current product-surface planned | 0 | Current status does not prove execution. |
| Current product-surface succeeded | 0 | Current status does not prove execution. |
| Current product rows extracted | 0 | Current status does not prove execution. |
| Companies missing product muscle | 11 | Product comparison remains incomplete. |
| Conversation themes | 500 | Market-conversation evidence exists. |
| Demand signals | 0 | No ready GA4 / Looker source. |
| Patterns | 3 | Deterministic pattern primitives produced output. |
| Recommendations | 0 | No promoted action because evidence is incomplete. |
| Consumed learnings | 0 | Learning effect on the current run is not proven. |

Blocking the recommendation plane while demand is absent is the correct behavior. The problem is that the required inward evidence has still not been connected.

## Repository State

Verified local CI-OS repository state:

| Item | State |
|---|---|
| Branch | `main` |
| Latest commit | `453849c` |
| Git remote | None configured |
| Tracked files changed | 44 |
| Tracked diff | 17,879 insertions, 885 deletions |
| Untracked files | 186 |
| Full local test suite | 1,180 passed, 1 skipped, 23 deselected |
| Whitespace check | Passed |

The test suite proves that the current local test contract passes. It does not prove the live Hermes path, current evidence, UI usability, or production publication contract.

The absence of a Git remote contradicts older vault claims that the standalone GitHub repository is the current source of truth. This must be reconciled before release work.

## Implemented Capability Inventory

### Substantially implemented

- Multi-tenant Postgres schema and repositories.
- Tenant, competitor, source, source-health, and product-surface registries.
- Competitor/source add, edit, pause, retire scaffolding in local admin.
- Evidence ledger and source provenance structures.
- Product events, capability positions, conversation themes, demand signals, patterns, recommendations, and scorecards.
- Source failure classification and blocked-source handling.
- Competitor-specific brief generation and routes.
- Public monitored-competitor roster.
- Product muscle work queues and demand work orders.
- Manual demand upload and GA4 readiness controls.
- Learning event, challenge, proposal, and apply-plan artifacts.
- Hermes package wrapper and cron registration.
- Public dashboard renderer and selected Playwright interaction checks.

### Partially implemented or unproven

- Reliable Hermes-owned daily execution.
- Current-run Scout product-surface extraction.
- Product feature comparison across every active competitor.
- GA4 / Looker ingestion with validated demand coverage.
- Cross-plane synthesis from product, conversation, and demand.
- Recommendation promotion with human-usable action detail.
- Learning that changes a later run.
- Multi-channel delivery through Hermes rather than duplicated paths.
- Complete competitor onboarding from admin through first successful sweep.
- Historical validity and seven-day / thirty-day pattern views.
- Public release safety and atomicity.

### Not delivered to product standard

- Production Argus Read.
- Production Product Muscle Matrix.
- Production Conversation Heatmap.
- Production Demand Lens.
- Production Pattern Board.
- Production Actions workflow.
- Coherent Competitor Registry journey.
- Coherent Evidence Lab.
- Coherent Argus Command and Admin separation.
- Exhaustive UI, accessibility, semantic, and live-data E2E validation.

## Completion Assessment

| Workstream | Completion | Current judgment |
|---|---:|---|
| Hermes extension boundary | 65% | Boundary exists; package release and ownership need control. |
| Hermes scheduled execution | 15% | Job exists; latest real scheduled run failed. |
| Competitor and source registry | 55% | Data/admin/public roster exist; onboarding proof incomplete. |
| Daily outward collection | 45% | Coverage can be reported; autonomous reliability is unproven. |
| Scout product muscle | 30% | Model and queues exist; current extraction proof is absent. |
| GA4 / Looker demand | 10% | Plumbing exists; no production demand signals. |
| Pattern intelligence | 25% | Three patterns exist; cross-plane validation is incomplete. |
| Recommendations | 10% | Structures exist; current output is zero. |
| Frontend IA and usability | 20% | Existing UI is not the accepted Product Muscle IA. |
| History, heatmap, semantic views | 30% | Surfaces exist; business validity is not acceptance-tested. |
| Learning loop | 25% | Artifacts exist; downstream run impact is unproven. |
| E2E and launch validation | 35% | Broad tests exist; gate and UI coverage have major blind spots. |
| Version control and release hygiene | 5% | Large dirty tree, no remote, no auditable release series. |

Weighted product completion: approximately 35 percent.

## Critical Code And Operational Findings

### P0

1. Hermes runtime ownership is broken. Root/manual runs recreate files Hermes cannot replace.
2. The daily wrapper can recursively delete an unsafe configured output path.
3. Public publication is not atomic and can expose a partial artifact set as published.
4. The current repository state cannot be audited or rolled back as a coherent release.

### P1 correctness and security

1. Public safety is self-attested rather than derived from a final artifact scan.
2. Launch validation accepts PASS substrings from arbitrary logs.
3. Launch validation does not bind all artifacts to one fresh run identity.
4. Product readiness can pass from historical event counts when current extraction did no work.
5. The existing Playwright suite checks a selected subset, not every interaction or competitor.
6. Admin writes are allowed without a token when the token is unset.
7. Source creation does not prove competitor ownership by the same tenant.
8. Repeated demand uploads can overwrite evidence with the same basename.
9. A GA4 plan sidecar can be scanned as demand evidence.
10. Package verification tests paths and text, not executable behavior.
11. Admin product-surface subprocesses lack an outer timeout.
12. Direct runner defaults diverge from the current Gemini production policy.

## User And Business Gaps

The present product still does not clearly answer:

- What changed across the whole monitored market, not only one selected competitor?
- What was actually shipped versus merely said?
- What themes are accelerating, cooling, or converging over time?
- Where is Algolia strong, behind, silent, or over-positioned?
- What does Algolia's audience behavior validate or contradict?
- Why is one competitor or action prioritized over another?
- What confidence rubric and evidence produced that judgment?
- What should a PMM, Product, Sales, Content, or executive owner do next?
- What did Argus learn, and how did that learning change the next run?

Without these answers, the application remains monitoring and plumbing rather than a Competitive Intelligence Operating System.

## Remaining Deliverables

1. A healthy Hermes-owned scheduled loop with no root/manual production path.
2. Safe staging, atomic publication, current-run identity, and trustworthy launch evidence.
3. Scout extraction across active product surfaces and a validated feature/capability matrix.
4. A real GA4 or Looker demand source with topic coverage and time-series signals.
5. Cross-plane patterns with explicit support, contradiction, confidence, and unknowns.
6. Specific recommendations with owner, urgency, evidence, and generated work products.
7. A proven learning loop whose instruction changes the following run.
8. The accepted Argus Product Muscle IA implemented as one coherent product.
9. Exhaustive backend, frontend, accessibility, semantic, security, and live cron E2E validation.
10. A clean, versioned, reviewable release and an evidence-backed pilot gate.

## Dependencies And Decisions

### Required from Arijit

- Provide or authorize a GA4 / Looker export or connector for the Algolia tenant.
- Confirm who may access public CI-OS status versus internal evidence and admin data.
- Approve the first human-reviewed recommendation as useful enough to operationalize.
- Decide the repository remote and release ownership model.

### System dependencies

- Hermes runtime and cron.
- CI-OS extension package.
- Scout acquisition and extraction.
- Postgres evidence ledger.
- Gemini model route.
- Algolia GA4 / Looker evidence.
- Public dashboard and local/authenticated admin.

## Definition Of Done

CI-OS is complete for the Algolia pilot only when all of the following are true:

- One scheduled Hermes run completes as Hermes with exit 0 and no orphan work.
- All active sources are checked or explicitly skipped with reason.
- Scout extracts current product evidence across the required competitor set.
- Demand evidence is processed and coverage is visible.
- One fresh run produces a defensible seven-day cross-plane read.
- At least one recommendation is specific, evidence-backed, and accepted by its intended owner.
- Every public click and admin journey reaches the correct entity and action.
- Every displayed data point traces to current-run evidence.
- Keyboard, accessibility, responsive, semantic, and security gates pass.
- Public publication is atomic and public-safe.
- A saved learning demonstrably changes the next successful run.
- The exact deployed package is versioned, reviewable, and reproducible.

## Canonical Supporting Records

- `docs/audits/2026-07-13-ci-os-forensic-status-review.md`
- `docs/decisions/2026-07-13-ci-os-recovery-boundary.md`
- `docs/plan/argus-product-muscle-ia.md`
- CI-OS repository: `docs/plan/e2e-validation.md`
- CI-OS repository: `docs/workspace/cios-intelligence-core/_status.md`

## Documentation And Bible Publication

Completed on 2026-07-13:

- Updated the canonical MyOS Competitive Intelligence index and workspace state.
- Updated the Second Brain CI-OS index, task ledger, status, dossier, and completion plan.
- Updated the cross-project tracker with the current CI-OS recovery state while preserving a concurrent Algolia-Central2 tracker update.
- Added the dossier and completion plan to the CI-OS repository documentation.
- Added and tested the canonical Bible route `/ci-os`.
- Made `status.md` the CI-OS Bible landing document.
- Published the public-safe CI-OS status, phase tracker, and completion plan.
- Escaped raw HTML in vault Markdown and removed dynamic `innerHTML` use from Bible search rendering.
- Added a CI-OS public-file allowlist. Only `status.md`, `tracker.md`, and `completion-plan.md` are discoverable or retrievable; the internal index, log, task ledger, doctrine, and full dossier return 404.
- Kept the latest internal task ledger and full internal dossier out of the public mirror.

Live public page: `https://bible.chowmes.com/ci-os`
