# Navigation, Barometer, And Hero Decisions

Date: 2026-07-01
Status: Accepted UX direction

## Decision 1: CI-OS Has Three Primary Lenses

The top command rail for CI-OS uses three primary role lenses:

- Marketing
- Sales
- Product

Admin exists as an operational control area, not as a primary daily intelligence lens.

The three lenses are not department-politics labels. They are operating filters for what a human needs to decide next:

- Marketing asks what the market is hearing and how Algolia should respond in narrative.
- Sales asks what the field needs before competitive conversations.
- Product asks what technical or roadmap movement deserves inspection.

Role rail behavior:

- hover previews the active underline on the hovered role
- click commits the active role and scrolls to that role anchor
- scroll updates the active role when a role-owned section becomes the reading context
- matching role-owned sections receive an active highlight
- role state is not only visual chrome; it dictates what the page emphasizes below
- if the product later uses multiple pages, every route must still inherit the selected role lens
- the visual order, DOM order, and anchor order must match: Marketing, Sales, Product
- role anchors are reserved for the primary lens panels; role-aware hero modules may share role state but should not steal the canonical role anchor
- the masthead should contain brand and role navigation only unless metadata changes user action
- report cadence, scope, and date belong in report metadata or archive surfaces, not as decorative top-right masthead text
- when right-side masthead metadata is removed, the role rail remains centered; do not add invisible or decorative filler to balance the layout

## Marketing Lens

Marketing covers:

- messaging shifts
- what competitors are saying
- audience attention
- pattern and momentum shifts
- content angles
- campaign posture
- positioning opportunities

Marketing means product marketing, field marketing, content, brand, and other marketing functions. The UI should not over-fragment marketing roles.

## Sales Lens

Sales covers:

- pricing changes
- new offers
- competitor pitches
- analyst rankings
- case studies
- new wins
- proof points
- deal-facing objections
- commercial implications of industry movement

Sales should show what reps, managers, enablement, and commercial leaders need to know before competitive conversations.

## Product Lens

Product covers:

- new competitor products
- technical recommendations
- integrations
- partner solutions
- ISV movement
- docs and changelog changes
- roadmap implications
- technical positioning

Examples include integrations with Salesforce, commercetools, CMS, PIM, and other relevant ecosystem platforms.

## Decision 2: Competitor Attention Barometer Is Accepted

The barometer replaces the rejected dot matrix.

Rules:

- one bar per competitor
- score means attention needed this week, 0 to 100
- green means normal
- blue means monitor
- amber means watch
- red means act now
- every bar has a text label
- clicking a competitor opens the reason, evidence, recommendation, and confidence
- section must be screenshot-ready for Telegram, WhatsApp, and executive briefs
- do not repeat the leading competitor in a separate pill if the first row already says it
- do not show stat cards that duplicate the score, competitor count, or confidence already visible elsewhere
- do not show a separate legend when the bars already carry the state labels
- each row must include an action cue, such as what to verify, watch, inspect, or ignore
- "watch" and "monitor" are not complete UX states unless the UI says what the user is watching or monitoring
- action cues should be inline microcopy beside the competitor name, not a second body-text line
- rows must feel clickable through pointer, hover, focus, and row-level anchoring
- rows are accordion objects: the folded row is the summary, the opened row is the proof surface
- row anchors must resolve to the accordion row itself; dead clickable furniture is not acceptable

## Decision 3: Hero Must Be Concrete

The previous hero felt like science fiction because it made a dramatic claim without giving enough operational meaning.

New hero requirements:

- name the competitor that matters most
- state why it matters
- identify the dominant threat category or decision posture
- show what Marketing, Sales, and Product should do
- avoid vague grand thesis language
- avoid empty "market quiet" rhetoric unless coverage evidence is the actual issue
- stay compact enough that it does not become an empty billboard beside the barometer
- do not carry explanatory body copy once the headline, image, and barometer already express the read

The hero should feel like Argus' useful operating read, not a poster.

The hero and barometer detail must not repeat the same sentence in two places:

- hero declares the operating read
- barometer detail explains why the selected bar has that score
- detail should expose trigger, risk, next move, evidence, and confidence
- if the barometer is visible in the same viewport, the hero stats should emphasize decision posture, next artifact, current constraint, and threat category instead of repeating the score

## Decision 4: UI Must Invoke Human Action

Every visible element in the cockpit must earn its place by triggering understanding, attention, inspection, prioritization, or action.

For the barometer, this means:

- the row is the interactive object
- the score belongs on the row
- the status label belongs inside the bar
- the action cue belongs beside the competitor
- the action cue should be short enough to scan with the competitor name as one sentence
- proof points, sources, and recommended response open inside the selected row
- do not duplicate the barometer summary in a separate proof-tile strip
- depth and glass effects belong on selected/actionable rows, not as page decoration
- action intensity controls optical depth: `act now` gets the strongest lift, `watch` gets restrained lift, `monitor` gets cool/quiet lift, `normal` stays almost flat
- opened proof uses a glass layer to indicate it is the currently inspected evidence surface

Redundant badges, stat boxes, legends, and selected-item panels are removed unless they add a new decision-useful fact.

## Decision 4.5: Evidence Quantifies The Lenses

Evidence and coverage are not an isolated dashboard appendix.

They are the quantified eyesight that produces the Marketing, Sales, and Product lenses. The cockpit should make that relationship visible:

- each lens gets a compact evidence summary showing the source basis and confidence constraint behind that lens
- the aggregate evidence section is the totality of Argus' sightline, not a disconnected metrics panel
- source-health numbers should explain confidence, not compete with the intelligence read
- degraded channels should be named as constrained sightlines, not buried as operational trivia
- private-data absence should be represented honestly as a coverage boundary, not as a failure
- infrastructure and access controls belong in Admin or route documentation, not in the daily intelligence surface

Visual treatment:

- role rail, lens panels, and evidence totality should feel connected
- each lens may use a subtle role-specific gradient wash, but the gradient must be a semantic link, not decorative color
- Marketing, Sales, and Product washes should remain quiet enough that the content stays editorial and premium
- the evidence totality panel can blend the lens colors because it represents the combined Argus eye

## Decision 4.6: Summaries Must Drill Into Reports

No intelligence summary should be a dead end.

When the cockpit shows a barometer row, lens item, or evidence chip, the user must be able to reach the deeper artifact that produced it:

- daily report
- article or narrative brief
- source bibliography
- evidence state
- confidence and constraint
- recommended next action
- related role lens

Interaction rule:

- the folded barometer row is the attention summary
- the opened row is the proof preview
- the proof preview must expose a deliberate `Open brief` action
- `Open brief` expands the full article/report inline under the proof preview
- the full brief should not teleport the user away from the signal unless the user explicitly chooses a separate Reports archive route
- the article must be the same kind of artifact Argus produced and delivered that day: narrative report, what was captured, source trail, customer/market evidence, confidence state, and recommended implication
- in production, every row should carry a stable `reportId` and `signalId`
- report links should preserve the selected role lens where relevant

This keeps the cockpit clean while preserving auditability. The surface can be editorial, but the evidence trail must always be one click away.

## Decision 4.7: Do Not Show Architecture Explaners In The Cockpit

The cockpit is an operating surface, not a product-spec page.

Remove sections that explain the app's route model, implementation model, or future navigation architecture unless they directly change the user's next intelligence action.

Specifically:

- do not show a `Role-aware navigation model` card grid inside the daily cockpit
- keep route architecture in the UX spec and planning docs
- the product should demonstrate role-aware navigation through behavior, not explanatory furniture
- Admin, login, SSO, model-provider, channel-linking, and route-map details belong in Admin or documentation, not in the daily read
- every visible section should answer what happened, why it matters, what to inspect, what to do, or how much confidence to assign

If a section is only useful for the builder, it is not user-facing cockpit content.

## Decision 5: Explanatory Furniture Is Removed From The First View

The first viewport should not explain the design to the user.

Removed from the hero/barometer:

- hero paragraph under the headline
- image caption over the editorial brief image
- score formula explainer under the barometer

Reason:

- the headline carries the operating read
- the image carries the editorial mood and evidence-world texture
- the barometer rows carry action and clickability
- the opened barometer row carries the detail after selection

If explanatory text does not change the next user action, it should be cut or moved behind interaction.

Active role highlights should hug meaningful content. Do not stretch a highlighted section merely to match a neighboring image height if that creates framed empty space.

Hero imagery should carry editorial mood and evidence texture, but it must not govern the height of the first viewport. If the image creates dead space around the barometer or proof accordion, reduce the image height before adding filler copy.

## Decision 6: CI-OS Uses Luxury Editorial Storytelling

The cockpit should not look like an engineering telemetry board.

CI-OS is competitive intelligence, but it is also interpretation, editorial judgment, content strategy, and imagination. Argus should feel like an intelligence editor publishing a living market magazine: plot, characters, evidence, tension, and the next move.

Accepted visual direction:

- use the Luxury Editorial / Maison design system as the cockpit direction
- warm paper, charcoal ink, Playfair Display, Inter, hairline rules, generous space, and 0px radius
- use restrained gold only as editorial accent
- use visual story surfaces, not decorative dashboard art
- treat the generated Search Intelligence Weekly image as the direction-setting artifact for the hero
- preserve actionability: visuals create attention, rows create interaction, evidence opens after selection

The first viewport should combine:

- Argus editorial read
- image-led market story
- interactive competitor attention index

This is the product differentiation: premium editorial intelligence with evidence-backed actions, not a generic SaaS dashboard.

## Decision 6: Brand And First-Viewport Restraint

The product surface should brand itself as `Argus`, not `Argus CI-OS`.

`CI-OS` remains the system/project name in planning and architecture, but the user-facing product voice is Argus.

Brand direction:

- wordmark: Argus
- supporting line: Competitive intelligence editor
- logo: an all-seeing watcher/aperture/compass mark in charcoal and gold, representing Argus' mythic vigilance, editorial scrutiny, and market judgment
- no generic square app glyph
- no repeated system acronyms in the first viewport

Current logo asset:

- `docs/mockups/assets/argus-logo-mark.png`
- generated as a raster concept mark, then chroma-keyed into a transparent PNG for the mockup
- future production implementation should recreate or refine it as a simplified vector mark for crisp small-size rendering

First-viewport restraint:

- remove controls that do not earn immediate action
- cadence, scope, and date can appear as quiet issue context
- avoid fake or unclear command buttons such as "Open brief" when the page itself is the brief
- shorten hero prose until it gives the read and the next action in one breath
- keep visual hierarchy layered: brand and lens, editorial read, image-led story, attention index, then deeper role sections
- less is more, but only after the remaining elements are sharper
- remove brand subtitles when the wordmark and mark already establish identity
- remove explanatory captions when the interaction itself already explains the section
