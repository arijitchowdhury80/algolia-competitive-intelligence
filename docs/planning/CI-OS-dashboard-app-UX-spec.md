# CI-OS Dashboard And App UX Spec

Date: 2026-07-01
Status: Planning baseline
Product: CI-OS
Primary voice: Argus

## Purpose

The CI-OS app is the executive and operator-facing surface where Argus publishes current intelligence, evidence, source health, workflow actions, and weekly content recommendations.

It is not a vanity dashboard. It is the product face of the Competitive Intelligence OS.

## User Types

### Arijit

Needs:

- Daily Argus read.
- Weekly strategic readout.
- Source coverage confidence.
- Actionable recommendations.
- Content plan for Algolia.
- Ability to challenge Argus and inspect evidence.

### Algolia Executive

Needs:

- Executive-grade summary.
- What matters now.
- Confidence level.
- Strategic implications.
- No raw implementation noise.

### PMM / GTM User

Needs:

- Competitor messaging movement.
- Campaign and content ideas.
- Claims and positioning changes.
- Evidence links.
- Suggested action queue.

### CI Operator / Admin

Needs:

- Source health.
- Run status.
- Delivery status.
- Model escalation logs.
- Credential and integration health.
- Improvement queue.

## Authentication

V1 login should use Google OAuth.

Requirements:

- Restrict by allowlisted Google accounts or approved email domains.
- Roles: owner, executive_viewer, gtm_viewer, operator_admin.
- Session expiration and logout.
- No public access to sensitive operational views.
- Public share links are out of scope for v1 unless explicitly approved.
- Enterprise path must support OIDC, SAML, SCIM provisioning, group-to-role mapping, and domain verification.
- Channel identities for Telegram, WhatsApp, and Apple Messages for Business must link to the same canonical user account.

## Conversation Channels

Argus must support a channel-neutral conversation model:

- Web app chat.
- Telegram.
- WhatsApp.
- Apple Messages for Business.

Each channel may have different capabilities, but the same ACL and audit model applies. The UI should include an operator-only channel management screen showing configured, degraded, missing credentials, and disabled states.

## Navigation

Primary nav should represent product routes, not one-page anchors.

Production routes:

- `/login`: pre-auth Google SSO and access request screen. No authenticated cockpit chrome.
- `/command`: executive cockpit with Argus read, Market Field, trust state, and current priorities.
- `/signals`: semantic deltas, executive speech, GTM narrative, product/docs, pricing, case studies, social/content signals, and suppressed diagnostics.
- `/sources`: source ledger, coverage matrix, source family health, candidates, retirements, and blocked lanes.
- `/content`: competitor content movement, traction signals, weekly Algolia content plan, hooks, outlines, and archive.
- `/actions`: workflow-backed action queue, owners, due windows, evidence, and status.
- `/reports`: daily, weekly, and monthly archive with quality review, delivery status, and exports.
- `/admin`: users, SSO, channel identity linking, model providers, integrations, schedules, and improvement queue.

Static mockup rule:

- The single-file HTML mockup may use anchors so it can be browsed locally.
- The implemented app should use real routes or route-backed tabs.
- Login must not appear inside the authenticated Command Center screen.

Secondary controls:

- cadence selector: daily, weekly, monthly
- date range selector
- competitor filter
- source family filter
- confidence filter

## Screen 1: Login

Purpose:

- Secure, simple entry.

Elements:

- CI-OS wordmark.
- "Continue with Google" button.
- Short trust statement.
- Access-request disabled state if account is not allowlisted.

No marketing hero. This is a working product.

## Screen 2: Command Center

Purpose:

- The main intelligence surface.

First viewport:

- Argus current read.
- Trust bar: data freshness, source coverage, delivery status, model tier.
- Material deltas.
- Action queue preview.
- Weekly content plan preview when cadence is weekly.

Argus current read structure:

- Useful truth first.
- What changed.
- Why it matters.
- What not to over-believe.
- Recommended move.
- Confidence.

Data elements:

- report id
- cadence
- generated_at
- model tier
- coverage score
- source family count
- material delta count
- false-negative audit status
- delivery status

## Screen 3: Signals

Purpose:

- Inspect semantic deltas and raw signal families.

Tabs:

- Material deltas
- Executive speech
- GTM narrative
- Product/docs changes
- Pricing
- Customer/case studies
- Social/content signals
- Suppressed diagnostics

Delta card data:

- competitor
- delta type
- materiality score
- what changed
- why it matters
- evidence count
- confidence
- recommended action

Detail drawer:

- evidence links
- source snapshots
- related claims
- thesis impact
- action item link

## Screen 4: Sources

Purpose:

- Prove coverage and expose blind spots.

Views:

- competitor coverage table
- source family matrix
- source health events
- candidate sources
- retired sources
- blocked or credential-required sources

Data elements:

- competitor
- source family
- active source count
- last checked
- missing streak
- health status
- candidate count
- coverage score

UX rule:

- Missing coverage should be visible without sounding like system panic.

## Screen 5: Content

Purpose:

- Show competitor content movement and recommend Algolia content plans.

Sections:

- competitor content themes
- public traction signals
- winning hooks and angles
- audience resonance
- next-week Algolia content plan
- content recommendations archive

Recommendation data:

- title
- target audience
- hook
- layout
- recommended format
- why now
- evidence ids
- confidence
- status

Rules:

- Do not copy competitor phrasing.
- Do not recommend content without evidence.
- Separate inspiration from imitation.

## Screen 6: Actions

Purpose:

- Workflow-backed accountability.

Elements:

- action queue
- owner filter
- priority filter
- status filter
- due window
- evidence link
- originating report

Allowed owners:

- Product
- Product Marketing
- Sales Enablement
- Partner Enablement
- Competitive Intelligence
- Executive Review

Rules:

- No owner appears unless an `action_items` record exists.
- Quiet runs do not create fake actions.

## Screen 7: Reports

Purpose:

- Archive of daily, weekly, and monthly readouts.

Elements:

- report list
- cadence
- date
- summary
- quality review status
- delivery status
- export links

Report detail:

- Argus readout
- semantic deltas
- evidence
- source coverage
- actions
- content plan
- delivery metadata

## Screen 8: Settings

Purpose:

- Operator admin controls.

Sections:

- competitors
- source policies
- integrations
- model routing
- delivery channels
- user access
- SSO and provisioning
- channel identity linking
- run schedules
- improvement queue

Rules:

- Settings that require credentials show configured/missing status only.
- Never show raw secrets.
- Dangerous actions require confirmation.
- Model providers are managed through aliases and capabilities, not hardcoded provider names in the UI.

## Visual Storytelling

Use generated or rendered visuals when they clarify intelligence:

- market movement map
- competitor positioning shifts
- source coverage matrix
- narrative theme heatmap
- weekly content opportunity map

Generated visuals must be labeled as generated and must never be treated as evidence.

## Dashboard Data Contract

The app should render from structured data:

- `dashboard_state`
- `semantic_deltas`
- `raw_findings`
- `source_health_events`
- `action_items`
- `bot_deliveries`
- `content_recommendations`
- `weekly_content_plan`
- `quality_reviews`
- `false_negative_audits`

Do not parse Markdown reports for the primary UI.

## Responsive Behavior

Desktop:

- persistent left nav
- three-column command layout where useful
- detail drawer for evidence

Tablet:

- compact nav
- two-column command layout
- full-width detail panels

Mobile:

- brief-first
- stacked cards
- bottom or drawer navigation
- evidence opens as full-screen sheet

## Empty And Degraded States

No material deltas:

- "No material deltas found in the latest run."
- Show coverage score and false-negative audit status.

Coverage weak:

- "Coverage is not strong enough to call the market quiet."
- Show missing source families and recheck state.

Delivery failed:

- Show report generated but Telegram delivery failed.
- Link to delivery record and retry status for operators.

## Static Mockup

Planning mockup:

- `/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/docs/mockups/ci-os-dashboard-app-mockup.html`

Vault mirror:

- `/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS/docs/mockups/ci-os-dashboard-app-mockup.html`
