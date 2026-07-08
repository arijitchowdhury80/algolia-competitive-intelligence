# CI-OS Dashboard Redesign Direction

Date: 2026-07-01
Status: Mockup revision

## Rejection

The first mockup was rejected because it looked like an industrial reporting system. That criticism is correct.

The failure:

- Too much generic sidebar plus cards.
- Too much status reporting.
- Not enough premium cockpit feeling.
- Not enough Argus as strategic intelligence lead.
- No memorable intelligence artifact.
- It looked like a system about reports, not a system about competitive meaning.

## New Design Thesis

CI-OS should feel like a premium Competitive Intelligence Cockpit.

The first viewport should answer:

- What does Argus think?
- Which competitor motion matters?
- How strong is the evidence?
- Where are we blind?
- What should Algolia do next?

## Signature Element

The cockpit gets a Competitor Attention Barometer:

- One bar per competitor.
- Score is attention needed this week, 0 to 100.
- Color is a discrete state: green normal, blue monitor, amber watch, red act now.
- The highest-priority competitor must be obvious without reading a legend.
- The visual should be screenshot-ready for Telegram, WhatsApp, or executive brief sharing.

## Visual System

Palette:

- Ink: `#0b1020`
- Surface: `#fbfaf7`
- Panel: `#ffffff`
- Algolia blue: `#003dff`
- Signal cyan: `#00a3ff`
- Evidence green: `#11835b`
- Risk amber: `#b36b00`
- Editorial red: `#d13c2f`

Layout:

- Slim top command rail instead of heavy industrial sidebar.
- Hero is Argus' strategic read, not a metric block.
- Competitor Attention Barometer sits in the first screen.
- Supporting panels are dense but editorial.
- Operator details exist, but below the executive cockpit.
- Login is a separate pre-auth route, never embedded inside the authenticated cockpit.
- The top command rail is role-aware. Role pills act as navigation, anchors, and state setters; selected screens inherit the active role lens.
- Product routes exist under the role lens; anchors exist only in the static mockup for browsing.

Writing:

- Short, sharp, evidence-backed.
- No generic AI wording.
- No raw log language.
- Argus voice appears as judgment, not mascot copy.

## Mockup Standard

The mockup should make someone say:

"This is where a serious competitive intelligence system lives."

Not:

"This is a dashboard template with better copy."

## Route Model

Production routes:

- `/login`: Google SSO, access request, and denied-state handling.
- `/command`: Argus read, Competitor Attention Barometer, priority actions, confidence state.
- `/signals`: material deltas, signal families, detail drawer, evidence.
- `/sources`: source ledger, coverage, blind lanes, candidates, retirements.
- `/content`: competitor content movement and Algolia content recommendations.
- `/actions`: workflow-backed action queue.
- `/reports`: daily, weekly, monthly archive.
- `/admin`: SSO, users, channels, model providers, integrations, schedules.

The mockup should show the route model as a product map, not by placing every screen inside the command cockpit.

## Role-Aware Command Rail

The top rail should default to role lenses:

- Marketing
- Sales
- Product

Marketing covers product marketing, field marketing, content, brand, campaigns, messaging, positioning, audience attention, and momentum shifts. Do not fragment it into separate PMM and field-marketing rails.

Sales covers pricing, offers, pitches, analyst movement, case studies, wins, proof points, objections, and other deal-facing competitive movement.

Product covers product launches, technical recommendations, docs, changelogs, partner solutions, ISV integrations, and roadmap implications.

Admin remains available as an operational route for users, SSO, channel identity, schedules, model providers, and integrations. It is not one of the three primary daily intelligence lenses.

When a lens is selected, the current route should filter or reorder content to match that lens. This is now a global UX SOP directive, not a CI-OS-only decision.

## Human-Readable Status Visuals

The old dot matrix was rejected because it required too much decoding. The replacement must follow the global human-readable status visual SOP:

- no subtle shade systems
- no unexplained dots
- no hidden metric colors
- score meaning must be stated
- colors must have text labels
- visual must survive as a screenshot in chat
