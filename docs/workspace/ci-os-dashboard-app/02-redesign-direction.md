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

The cockpit gets a Market Field:

- Competitors on one axis.
- Signal families on the other.
- Intensity, confidence, and blind spots visible together.
- The field is not decorative; it is the visual grammar of the product.

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
- Market Field sits in the first screen.
- Supporting panels are dense but editorial.
- Operator details exist, but below the executive cockpit.
- Login is a separate pre-auth route, never embedded inside the authenticated cockpit.
- Nav items are app routes in production; anchors exist only in the static mockup for browsing.

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
- `/command`: Argus read, Market Field, priority actions, confidence state.
- `/signals`: material deltas, signal families, detail drawer, evidence.
- `/sources`: source ledger, coverage, blind lanes, candidates, retirements.
- `/content`: competitor content movement and Algolia content recommendations.
- `/actions`: workflow-backed action queue.
- `/reports`: daily, weekly, monthly archive.
- `/admin`: SSO, users, channels, model providers, integrations, schedules.

The mockup should show the route model as a product map, not by placing every screen inside the command cockpit.
