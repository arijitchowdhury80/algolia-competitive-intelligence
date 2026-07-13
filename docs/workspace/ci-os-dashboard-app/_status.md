# CI-OS Dashboard App Mockup Status

Date: 2026-07-01
Status: Premium cockpit mockup revised; design still in progress

## Completed

- Mental model and information architecture.
- Screen map and user flows.
- Google login and role model.
- Data elements for each screen.
- Dashboard and app UX spec.
- Static HTML mockup.
- Rejected first industrial mockup and replaced with premium Competitive Intelligence Cockpit direction.
- Added Competitor Attention Barometer as the signature intelligence visualization.
- Removed login from the authenticated cockpit screen.
- Clarified that top navigation represents production app routes; static mockup anchors are only for local browsing.
- Recorded global UX SOP directive: top command rails are role-aware by default.
- Changed CI-OS top rail to role lenses and retired the former Market Field / Competitive Signal Map direction.
- Rejected the dot-matrix Competitive Signal Map because it required too much decoding.
- Replaced it with a screenshot-ready Competitor Attention Barometer using one labeled bar per competitor.
- Recorded global UX SOP directive: status visuals must use human-readable labeled states, not ambiguous shade systems.
- Updated CI-OS primary role lenses to Marketing, Sales, and Product.
- Reworked the hero direction so it names the competitor, score, confidence, threat category, and implications for each lens.
- Removed duplicate barometer furniture and made competitor rows action-invoking.
- Adopted the Luxury Editorial / Maison direction for the cockpit: CI-OS should feel like an intelligence magazine, not an engineering dashboard.
- Added the generated Search Intelligence Weekly image as the hero story surface.
- Changed the user-facing brand from `Argus CI-OS` to `Argus`.
- Replaced the old square mark with a generated all-seeing watcher/aperture/compass-style Argus mark.
- Removed top-right command clutter and reduced it to quiet issue context.
- Tightened hero prose and first-viewport scale under a less-is-more rule.
- Removed the brand subtitle under `Argus`.
- Removed the redundant barometer explanation line.
- Compressed barometer action cues into one-line clickable row microcopy.
- Added hover/focus affordance so competitor rows read as evidence-opening controls.
- Superseded the initial compact proof-card idea with in-row accordion proof surfaces.
- Made the top role rail stateful: hover previews the underline, click commits the role, scroll syncs the active role, and matching role sections are highlighted.
- Enforced Marketing / Sales / Product order in the lower lens sections so the page IA follows the command rail.
- Removed first-viewport explanatory furniture: hero body copy, image caption, and barometer score explainer.
- Top-aligned and tightened the hero columns to reduce dead white space.
- Corrected role lens source order to match the command rail: Marketing, Sales, Product.
- Reassigned the Marketing rail anchor to the primary Marketing lens panel and moved the hero barometer to `role-marketing-command`.
- Removed the top-right issue context text from the masthead; report cadence/scope/date should live in report metadata, not global navigation.
- Rebalanced the masthead as brand-left and role-rail-centered after removing the right-side metadata.
- Converted the Competitor Attention Barometer rows into accordions; proof now opens inside the selected row.
- Removed the separate proof-card strip because it duplicated the barometer summaries.
- Reduced hero image height so the editorial image no longer creates dead space around the barometer accordion.
- Added restrained action-driven depth and glass treatment to barometer accordions: strongest for `act now`, lighter for `watch`, cool/quiet for `monitor`, nearly flat for `normal`.
- Validated desktop and mobile behavior with Playwright using the bundled Codex runtime: no horizontal overflow, AWS opens by default, clicking another row closes the prior row, URL hash updates to the opened proof row, and the opened proof pane computes real glass blur and shadow.
- Reframed evidence and coverage as the quantified eye behind the Marketing, Sales, and Product lenses.
- Added compact evidence summaries inside each lens so the qualitative read and quantitative source base are visually connected.
- Removed the Access and model control block from the daily cockpit surface; it remains an Admin/IA concern, not a daily intelligence section.
- Added subtle role-linked gradient washes to the rail and lens panels so Marketing, Sales, Product, and aggregate evidence read as one story.
- Replaced the detached report drill-down with inline brief expansion. Each barometer row now exposes `Open brief`, which unfolds the article/report and source bibliography directly under that signal.
- Removed the `Role-aware navigation model` route explainer from the cockpit mockup. Route architecture remains a planning/spec concern; the user-facing cockpit now demonstrates role-aware navigation through behavior instead of explanatory cards.
- Recorded the 2026-07-01 design checkpoint at `docs/planning/CI-OS-dashboard-design-checkpoint-2026-07-01.md`.
- 2026-07-10: Added the Market timeline and Semantic layer contract after live critique that a "today only" priority read was not a competitive intelligence operating system.
- 2026-07-10: Market timeline now requires history calendar, report-history selector, Today/Yesterday/Last 7 days/Last 30 days windows, holistic daily coverage, and "Why this priority" rationale.
- 2026-07-10: Semantic layer now requires a full watched-universe partner selector, cross-partner pattern map, heat map, market direction, Argus recommendation, confidence rubric, quality gate, and public-source boundary.

## Notes

- The documented UI/UX SOP path and Algolia design-system path were not present at the expected local locations during this pass.
- The mockup now uses a Luxury Editorial / Maison visual direction: warm paper, charcoal ink, Playfair Display, Inter, hairline rules, restrained gold, 0px radius, and image-led story surfaces.
- Before implementation, confirm how CI-OS brand identity should coexist with any future Algolia-specific export surfaces.
- Current mockup is a stronger product-direction artifact. It has browser validation evidence, but Arijit remains the final taste gate before it becomes the UI baseline.
- Do not push to GitHub or launch the full build goal yet. Continue dashboard/app design tomorrow.
