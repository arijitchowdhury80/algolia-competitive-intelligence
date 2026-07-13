# CI-OS Completion Plan

Date: 2026-07-13
Input: `docs/status/2026-07-13-ci-os-project-dossier.md`
Status: proposed execution plan
Scope: finish the Algolia pilot before generalizing CI-OS

## Planning Principle

The next phase is recovery and proof, not feature accumulation. Work advances only through explicit exit gates. A phase is not complete because code exists; it is complete when the real Hermes path, real evidence, real UI, and current deployed state prove it.

Hermes remains the runtime OS. CI-OS remains a separately versioned extension. No phase may move CI-OS business logic into Hermes core.

## End State

The Algolia pilot must answer, from one fresh run:

> Across the last seven days, what did competitors ship, what did they say, what did Algolia's audience respond to, and what should Algolia do next?

The answer must be actionable, source-backed, confidence-scored, honest about unknowns, and usable by PMM, Product, Sales, Content, and executive users.

## Phase Order

| Phase | Outcome | Depends on |
|---|---|---|
| 0. Contain and baseline | One controlled code and runtime baseline | Nothing |
| 1. Restore Hermes execution | Healthy scheduled operating loop | Phase 0 |
| 2. Make release evidence trustworthy | Atomic, fresh, run-bound publication and gates | Phase 1 |
| 3. Complete Product Muscle | Current Scout-backed product comparison | Phase 2 |
| 4. Connect Audience Demand | Valid GA4 / Looker evidence plane | Phase 2 and Arijit input |
| 5. Prove Argus intelligence | Cross-plane pattern, action, and learning | Phases 3 and 4 |
| 6. Build the accepted product IA | Coherent Argus workflows | Phase 5 |
| 7. Complete E2E validation | Technical, semantic, UX, accessibility, and security proof | Phase 6 |
| 8. Release the Algolia pilot | Versioned, reproducible, monitored pilot | Phase 7 |

## Phase 0: Contain And Establish A Baseline

### Objective

Stop uncontrolled mutation and convert the two-day dirty tree into an auditable recovery baseline.

### Work

1. Freeze new feature work.
2. Inventory all 44 tracked changes and 186 untracked files by domain: source, tests, docs, generated output, deploy, and local artifacts.
3. Remove generated output and machine metadata from source-control candidates without deleting evidence needed for review.
4. Identify which files came from accepted requirements versus abandoned UI iterations.
5. Split the retained work into reviewable commits: schema/repositories, collection, product muscle, demand, intelligence, admin, dashboard, deployment, and tests.
6. Configure the intended Git remote and document branch/release ownership.
7. Tag or otherwise preserve the pre-recovery deployed package state.
8. Record checksums or commit IDs for the exact local and deployed baselines.

### Tests and evidence

- Full local suite passes from a clean checkout.
- `git diff --check` passes.
- Generated artifacts are reproducible and excluded from source commits.
- Deployed package maps to an identifiable commit or release bundle.

### Exit gate

One clean, reviewable branch represents the retained CI-OS implementation. No unknown untracked source files remain.

## Phase 1: Restore Hermes-Owned Execution

### Objective

Make Hermes the only production execution owner and prove a complete scheduled cycle.

### Work

1. Repair app, output, temporary, and public ownership for the Hermes runtime user.
2. Remove or disable root/manual production execution paths that recreate root-owned artifacts.
3. Add preflight checks for runtime user, output ownership, writeability, required environment, database, package version, and free space.
4. Canonicalize `CIOS_OUTPUT_DIR` and require an app-owned staging prefix plus marker before deletion.
5. Replace broad output deletion with validated staging-directory rotation.
6. Add bounded stage and process-tree timeouts.
7. Ensure timeout and failure paths kill descendants and preserve diagnostic evidence.
8. Add per-stage and per-source progress with a final structured run summary.
9. Exercise the real Hermes cron path, not a root shell substitute.

### Tests and evidence

- Unit tests reject empty, root, app-root, public-root, parent-traversal, symlink, and unmarked output paths.
- Integration test reproduces root-owned/unwritable output failure before the fix and passes after it.
- Timeout test proves no orphan process remains.
- Live cron run exits 0 as Hermes.
- All active sources are checked or explicitly skipped with reason.

### Exit gate

Two consecutive scheduled Hermes runs complete without root intervention, permission errors, timeout, orphan work, or stale-public fallback.

## Phase 2: Make Publication And Readiness Trustworthy

### Objective

Ensure every public status and launch result describes one fresh, complete run.

### Work

1. Introduce a run ID shared by cron, stages, source coverage, product extraction, demand, intelligence, dashboard, briefs, and E2E artifacts.
2. Stage every public artifact in a versioned run directory.
3. Validate the complete staged manifest before publication.
4. Publish atomically and write the final public status last.
5. Replace PASS-substring parsing with structured JSON results and exit codes.
6. Enforce freshness windows and reject mismatched run IDs.
7. Derive public safety from a recursive scan of final HTML, JSON, CSV, and brief artifacts.
8. Require current-run product execution evidence, not historical ledger counts.
9. Record the exact package version and model route in private run metadata.
10. Keep blocked runs visible as diagnostics without overwriting the last successful decision surface.

### Tests and evidence

- Publication failure injection at every copy step never exposes partial state as published.
- Stale, mismatched, spoofed, self-attested, and path-leaking fixtures fail the gate.
- Current-run structured artifacts pass.
- Package contract verifies executable behavior, permissions, and dry-run preflight.

### Exit gate

The corrected launch gate fails every planted defect and passes one fresh Hermes run whose public artifacts are complete, safe, and run-bound.

## Phase 3: Complete Scout Product Muscle

### Objective

Build the defensible feature and product comparison layer from shipped reality.

### Work

1. Finalize the product-surface registry for Algolia and the accepted competitor set.
2. Cover changelogs, release notes, docs, product pages, pricing, integrations, APIs, and package pages.
3. Run Scout extraction across all active targets with bounded retries and source-family adapters.
4. Normalize findings into product events, capabilities, products, availability, dates, and evidence URLs.
5. Deduplicate repeated announcements and distinguish new release, update, deprecation, packaging, and positioning.
6. Resolve the 11-company product-muscle gap or mark each unknown explicitly with cause and next check.
7. Build the feature-capability matrix for Algolia versus competitors.
8. Add evidence review for high-impact feature claims.
9. Record extraction confidence, freshness, and last-checked state per capability.

### Tests and evidence

- Fixture tests for every supported source family.
- Integration tests with successful, blocked, empty, duplicate, stale, and changed surfaces.
- Every matrix cell is supported, unknown, or not applicable. Blank disappearance is prohibited.
- Human audit samples claims against the cited source page.

### Exit gate

The active competitor set has current product evidence or explicit unknown states, and the matrix survives human evidence review with no unsupported feature claim.

## Phase 4: Connect Audience Demand

### Objective

Add the inward evidence plane that validates whether market and product themes matter to Algolia audiences.

### Required Arijit input

Provide or authorize one of:

- A GA4 connector with the approved property and dimensions.
- A Looker Studio export covering the required topics and date ranges.
- A recurring manual export contract for the pilot.

### Work

1. Lock the demand schema: page, topic, search term, referrer/campaign, engagement, conversion proxy, date, segment, and provenance.
2. Map Argus product/conversation topics into a demand work order before collection.
3. Validate uploads without consuming or overwriting originals.
4. Store source files immutably and prepared rows separately.
5. Distinguish matched plan topics, off-plan discoveries, missing topics, and insufficient samples.
6. Create time-series demand signals and confidence rules.
7. Prevent analytics from being misrepresented as proof of competitor behavior.
8. Expose coverage, freshness, missing fields, and the next operator action.

### Tests and evidence

- Unit tests for schema, deduplication, date ranges, attribution, and topic matching.
- Upload tests for duplicate names, malformed exports, partial coverage, and refresh failure.
- Integration test proves the raw file survives downstream failure.
- Human validation compares sampled prepared rows to the source export.

### Exit gate

At least one seven-day demand window produces nonzero, traceable signals for the active Argus topic plan, with explicit coverage and confidence.

## Phase 5: Prove Argus Intelligence And Learning

### Objective

Turn the three evidence planes into a decision that is better than source skimming.

### Work

1. Define deterministic candidate patterns across product, conversation, and demand.
2. Score support, contradiction, freshness, materiality, breadth, confidence, and Algolia actionability.
3. Require every pattern to expose supporting and contradicting evidence.
4. Distinguish facts, inference, hypotheses, unknowns, and rejected reads.
5. Generate recommendations only when evidence and confidence thresholds are met.
6. Attach owner, urgency, why now, evidence, expected result, and next review date.
7. Generate concrete work products: PMM brief, product investigation, sales talk track, content outline, or executive note.
8. Let users challenge, accept, reject, or amend the read.
9. Convert approved feedback into a scoped learning instruction.
10. Prove that instruction changes the next successful run and remains auditable.

### Tests and evidence

- Planted support, contradiction, false-quiet, stale-evidence, and missing-plane scenarios.
- Recommendation blocked when required evidence is absent.
- Human review rubric for usefulness, specificity, confidence, novelty, and actionability.
- Before/after run comparison proves learning effect.

### Exit gate

Arijit accepts at least one seven-day cross-plane recommendation as accurate, non-obvious, and directly usable by a named team.

## Phase 6: Build The Accepted Argus Product IA

### Objective

Implement one coherent business product around proven intelligence, not around raw data availability.

### Production navigation

1. Argus Read.
2. Product Muscle Matrix.
3. Conversation Heatmap.
4. Demand Lens.
5. Pattern Board.
6. Actions.
7. Competitor Registry.
8. Evidence Lab.
9. Argus Command and Admin.

### Work

1. Make Argus Read the first screen and lead with one decision, evidence, confidence, and action.
2. Implement time controls for today, seven days, thirty days, and custom ranges.
3. Keep competitor and partner context persistent across every dependent view.
4. Make the matrix inspectable by capability, product area, competitor, and evidence date.
5. Make the heatmap show theme intensity, movement, commonality, and competitor contribution.
6. Make Demand Lens show audience response and its overlap or contradiction with market/product themes.
7. Make Pattern Board explain why each pattern exists and what evidence would disprove it.
8. Make Actions usable by PMM, Product, Sales, Content, and executives.
9. Make Registry support end-to-end competitor and source onboarding through first sweep.
10. Move technical health and rejected evidence into Evidence Lab and Admin.
11. Make Argus contextually available in each workflow for explain, challenge, investigate, generate, save, and rerun actions.
12. Keep Argus conversation bounded; repeated commands update state rather than append an endless transcript.

### Tests and evidence

- Component and route tests from the real backend contract.
- User-journey tests for PMM, Product, Sales, Admin, and Evidence Auditor.
- No page contains unexplained metrics, dead controls, duplicated cards, or UI-only claims.
- Design review against the official Algolia design system.

### Exit gate

Five representative business users can identify the priority, evidence, confidence, and next action without explanation, and every journey reaches the correct competitor and artifact.

## Phase 7: Complete End-To-End Validation

### Objective

Prove the complete system technically, semantically, visually, and operationally.

### Backend coverage

- Unit and integration tests for tenancy, registry, collection, extraction, demand, intelligence, learning, publication, and failure paths.
- Real Postgres integration with multiple tenants, competitors, source types, blocked sources, quiet entities, and new competitor onboarding.
- Security tests for admin authentication, CSRF, tenant ownership, upload safety, path safety, secret leakage, and public data boundaries.

### Frontend coverage

- Automatically discover all links, buttons, tabs, summaries, filters, menus, dialogs, forms, and admin actions.
- Assert accessible name, expected target/action, state transition, entity identity, and semantic result for every control.
- Validate every competitor-specific brief and selected context.
- Validate keyboard order, focus, contrast, touch targets, reduced motion, responsive layouts, overflow, and deep links.
- Run desktop, tablet, and mobile visual checks with no overlap or hidden required context.

### Semantic coverage

- Every visible number traces to one current-run field.
- Every claim traces to evidence.
- Every pattern shows support, contradiction, and confidence.
- Every recommendation passes the human usefulness rubric.
- Quiet, stale, failed, blocked, unknown, and degraded states are distinct.

### Live coverage

- Run through real Hermes cron.
- Verify no orphan work and no root ownership drift.
- Verify package version, run ID, artifacts, dashboard, briefs, status, and E2E output all match.

### Exit gate

The corrected launch command exits 0 against production and a human acceptance pass confirms the decision is useful.

## Phase 8: Release The Algolia Pilot

### Objective

Ship a controlled pilot with monitoring, rollback, and explicit boundaries.

### Work

1. Create a versioned release from the reviewed branch.
2. Deploy the exact release bundle to the Hermes package path.
3. Preserve a tested rollback bundle.
4. Restrict admin access and define public versus internal surfaces.
5. Add run, source, evidence-plane, recommendation, and publication monitoring.
6. Define pilot users, cadence, feedback rubric, and decision owners.
7. Run daily for an agreed observation window.
8. Review false positives, false negatives, recommendation usage, and learning effects.
9. Decide whether evidence supports continued investment, a narrower scope, or termination.

### Exit gate

The pilot produces repeatable, trusted decisions and at least one team uses an Argus recommendation in real work. Only then consider generic tenant packaging.

## Progress Rules

- No phase skips.
- No launch percentages derived from test counts alone.
- No manual/root run may substitute for Hermes evidence.
- No UI build may fabricate missing evidence.
- No recommendation may hide a blocked plane.
- No phase closes without its tests, live evidence, and vault update.
- The tracker and Bible public status update after every phase gate, not after every code edit.

## Immediate Next Execution Slice

The first authorized implementation slice should contain only:

1. Phase 0 repository triage and clean baseline.
2. Phase 1 ownership preflight and safe output rotation.
3. One test-driven Hermes cron recovery.
4. Documentation of exact deployed package and run evidence.

Do not begin Scout, GA/Looker, intelligence, or UI work until this slice passes its exit gate.

