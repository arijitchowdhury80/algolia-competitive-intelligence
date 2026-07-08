# CI-OS Dashboard And App UX Spec

Date: 2026-07-01
Status: Planning baseline; dashboard design still in progress
Product: CI-OS
Primary voice: Argus

## Purpose

The CI-OS app is the executive and operator-facing surface where Argus publishes current intelligence, evidence, source health, workflow actions, and weekly content recommendations.

It is not a vanity dashboard. It is the product face of the Competitive Intelligence OS.

## Current Design Checkpoint

As of 2026-07-01, the cockpit mockup is not final and should not be treated as build-ready.

Read before continuing design:

`docs/planning/CI-OS-dashboard-design-checkpoint-2026-07-01.md`

The current accepted direction is a premium Argus cockpit with:

- Luxury Editorial / Maison visual language
- role-aware Marketing / Sales / Product command rail
- Competitor Attention Barometer
- in-row proof previews
- inline report/article/source-bibliography expansion
- evidence totality as `The eye behind the lenses`

Remaining screens and states still need design work before implementation.

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

### Marketing User

Needs:

- Competitor messaging movement.
- Campaign and content ideas.
- Claims and positioning changes.
- Evidence links.
- Suggested action queue.

### Sales User

Needs:

- Pricing and packaging movement.
- New competitor pitches.
- Analyst rankings and awards.
- New customer wins and case studies.
- Deal-facing proof points and objections.

### Product User

Needs:

- Product launches and technical changes.
- Docs and changelog movement.
- Partner and ISV integrations.
- Technical claims and recommendations.
- Roadmap and positioning implications.

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
- Roles: owner, executive_viewer, marketing_viewer, sales_viewer, product_viewer, operator_admin.
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

Primary navigation must follow the global Role-Aware Command Rail directive.

The top command rail should be role-aware:

- role pills are navigation, anchor points, and state setters
- selecting a role changes what the current screen emphasizes
- the selected role remains visible
- UI cards, actions, and detail panels inherit that role lens
- role availability respects ACL

CI-OS role lenses:

- Marketing: messaging shifts, what competitors are saying, audience attention, pattern shifts, momentum shifts, content angles, campaign posture, and positioning opportunities.
- Sales: pricing changes, new offers, competitor pitches, analyst rankings, case studies, new wins, proof points, deal-facing objections, and commercial implications.
- Product: competitor products, technical recommendations, integrations, partner solutions, ISV movement, docs and changelog changes, roadmap implications, and technical positioning.

Admin is an operational control area for SSO, users, channels, integrations, model routing, and run health. It is not one of the three primary daily intelligence lenses.

Primary app routes still exist, but they sit underneath the role lens.

Production routes:

- `/login`: pre-auth Google SSO and access request screen. No authenticated cockpit chrome.
- `/command`: role-aware cockpit with Argus read, Competitor Attention Barometer, trust state, and current priorities.
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
- Top rail anchors in the static mockup represent role lenses; production should preserve route and role in the URL or state.

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
- Competitor Attention Barometer: screenshot-ready ranked bar chart showing which competitor needs the most attention this week.
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

Attention Barometer rules:

- Score means attention needed this week, from 0 to 100.
- Color states are discrete and labeled: green normal, blue monitor, amber watch, red act now.
- The highest-attention competitor must be obvious without decoding a legend.
- Clicking a competitor opens the reason: what changed, why it matters, evidence, recommended response, and confidence.
- The section must be screenshot-ready for Telegram, WhatsApp, or executive brief sharing.
- Do not duplicate the top competitor in a separate pill when the first row already communicates it.
- Do not use separate stat boxes or legends that repeat the bar labels and row scores.
- Each row must include an action cue so "watch" and "monitor" explain what the user should watch or monitor.
- Every visible element must create a human reaction or action: notice, compare, click, verify, decide, or ignore.

Hero rules:

- Name the competitor that matters most.
- State why it matters in business language.
- Show or point to attention score and confidence without duplicating the adjacent barometer.
- Show dominant threat category, decision posture, next artifact, or current constraint.
- Show one action implication for Marketing, Sales, and Product.
- Avoid dramatic but vague claims.
- Avoid giant display copy that does not explain what happened.
- Avoid repeating the selected barometer detail. The hero declares the read; the barometer detail explains the score.
- Do not stretch the hero to fill vertical space if the adjacent intelligence visual is taller.
- If the barometer sits beside the hero, the barometer owns the numeric score while the hero owns the operating posture.

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
- lens filter
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
- Owners are workflow accountability labels, not top-rail navigation labels.
- Marketing, Sales, and Product remain the primary user-facing lenses.
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

## Luxury Editorial Direction

The cockpit should use the Luxury Editorial / Maison design system as the premium visual direction.

Principles:

- Intelligence is presented as a living market magazine, not an engineering status board.
- Argus behaves like an intelligence editor: he finds the plot, names the characters, evaluates evidence, and recommends the next move.
- The first viewport should combine editorial read, image-led story, and interactive attention index.
- Typography, spacing, and imagery should carry the premium feel: Playfair Display, Inter, warm paper, charcoal ink, hairline rules, restrained gold, 0px radius.
- Generated visuals are story surfaces, not evidence. Evidence opens through source/proof interactions.
- No dense stat grids, duplicate metrics, generic AI dashboard copy, or decorative charts without action.

## Brand And First-Viewport Restraint

The app should present as `Argus` in user-facing chrome. `CI-OS` remains the planning/system name, not the primary product wordmark.

Top chrome should contain only:

- Argus wordmark and watch/aperture mark
- role-aware lenses
- quiet issue context such as cadence, scope, and date

Avoid top-right command clutter unless the command is immediately meaningful and necessary. The first viewport should spend space on the logical reading path: editorial read, visual story, and action index.

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
