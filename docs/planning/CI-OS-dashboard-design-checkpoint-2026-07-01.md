# CI-OS Dashboard Design Checkpoint

Date: 2026-07-01
Status: Design in progress, not ready for GitHub or build execution

## Current Position

The dashboard/app mockup has moved from an industrial reporting surface toward a premium Argus cockpit.

This is a design checkpoint only. Do not treat the current mockup as final product UI. Do not start the full CI-OS build from this state without a fresh design review.

## Current Mockup

Local:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/docs/mockups/ci-os-dashboard-app-mockup.html`

Vault mirror:

`/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS/docs/mockups/ci-os-dashboard-app-mockup.html`

Current validated screenshot:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/docs/mockups/screenshots/ci-os-route-explainer-removed-desktop.png`

## Accepted Direction

- User-facing product brand is `Argus`, not `Argus CI-OS`.
- Argus should feel like a premium competitive intelligence editor, not a generic AI dashboard.
- Visual direction is Luxury Editorial / Maison: warm paper, charcoal ink, Playfair Display, Inter, hairline rules, restrained gold, and evidence-led imagery.
- The cockpit must invoke human action. Every visible element must answer: what does this make the user notice, inspect, decide, verify, or do?
- Top command rail is role-aware by design. It uses Marketing, Sales, and Product as the three primary role lenses.
- The role rail is not just visual navigation. Hover previews, click commits, scroll syncs, and content emphasis follows the selected role.
- The Competitor Attention Barometer is the signature weekly/daily attention visualization.
- Barometer rows are interactive accordions. Folded row equals summary. Open row equals proof preview.
- The proof preview must unfold into a full report/article/source-bibliography artifact inline under the same signal.
- Each current barometer row demonstrates the pattern with `Open brief` and a stable example report ID.
- Evidence and coverage are now framed as `The eye behind the lenses`, meaning the quantitative sightline that produced Marketing, Sales, and Product conclusions.
- Route architecture, Admin controls, model provider details, and access/channel setup do not belong inside the daily cockpit surface.

## Removed During This Pass

- Industrial dashboard treatment.
- Dot-matrix competitive signal map.
- Duplicate top competitor badge.
- Duplicate stat cards and legends around the barometer.
- Separate proof-card strip that repeated the barometer rows.
- Brand subtitle under Argus.
- Top-right issue metadata in the masthead.
- Hero body copy that repeated the barometer.
- Image caption and score formula explainer.
- Access and model control section from the cockpit page.
- Role-aware navigation model route explainer from the cockpit page.

## Current Cockpit Structure

1. Argus masthead with role-aware Marketing / Sales / Product rail.
2. Hero operating read: AWS pricing pressure needs verification before action.
3. Editorial intelligence image.
4. Competitor Attention Barometer.
5. Inline proof preview and `Open brief` report expansion for each barometer row.
6. Marketing lens.
7. Sales lens.
8. Product lens.
9. The eye behind the lenses.

## Verification Already Run

- HTML parse checks for duplicate IDs.
- Hash target checks for broken in-page links.
- Playwright desktop and mobile screenshots.
- Playwright checks for no horizontal overflow.
- Barometer open/close behavior.
- Inline `Open brief` expansion for barometer reports.
- Back-to-barometer behavior.
- Local-to-vault file hash parity.
- Obvious secret-pattern scan.

## Open Design Questions For Tomorrow

- What exactly should each role lens show when it is selected: same page filtering, route-backed lens pages, or hybrid?
- Should the hero change when Marketing, Sales, or Product is selected?
- Should each barometer row have its own full report section in the mockup, or should only one row demonstrate the pattern?
- What does a real source bibliography look like: source snapshots, citations, direct URLs, confidence grading, archived copies, or all of these?
- How should Telegram/WhatsApp screenshot-ready summaries be generated from the barometer and report sections?
- How does the daily cockpit differ from weekly and monthly views?
- What is the exact UI for the Signals page?
- What is the exact UI for the Reports archive?
- What is the exact UI for the Actions workflow and owner/status lifecycle?
- What is the exact UI for the Sources ledger and source-hunting results?
- What is the exact UI for Content Intelligence and next-week content recommendations?
- What belongs in Admin versus operator-only diagnostics?
- How should Google SSO, ACL, channel identity, and model provider settings appear without polluting the cockpit?
- What should the empty, quiet-day, degraded-source, and failed-run states look like?
- What live data contract should drive the mockup: `semantic-dashboard.json`, database tables, or a typed app API?
- How should Argus' voice appear in the UI without turning into long prose?
- How should visual imagery be generated, refreshed, versioned, and tied to the weekly/daily brief?

## Do Not Do Yet

- Do not push this to GitHub.
- Do not start the full CI-OS implementation goal.
- Do not treat the static mockup as final UI.
- Do not reintroduce implementation explainers into the cockpit screen.
- Do not add fake controls or fake routes unless they demonstrate a real planned interaction.

## Next Session Start

Open the mockup in browser and continue section-by-section critique.

Recommended next focus:

1. Decide whether the three role lenses should remain on the command page or become route-backed pages.
2. Design the full Signals page.
3. Design the Reports archive and report detail page.
4. Design Actions workflow UI.
5. Design Sources ledger UI.
6. Decide how screenshots and messaging artifacts are generated for Telegram, WhatsApp, and executive sharing.
