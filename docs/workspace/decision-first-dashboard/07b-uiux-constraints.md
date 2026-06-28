# Decision-First Dashboard UI/UX Constraints

Date: 2026-06-27

## Applied Source Material

- CI feature matrix: paid tools already cover monitoring, dashboards, alerts, battlecards, Q&A, and adoption analytics.
- Market patterns: Chowmes must compete on decision quality, not report volume.
- Algolia relevance map: valuable output is role-specific implication and action.
- Differentiation thesis: the wedge is Algolia-specific decision routing with evidence and quality supervision.
- Local UI/UX SOP: Algolia theme uses Algolia blue and strict emphasis tiers.

The older `Algolia-Design-System` path in ChowMes instructions was not present locally. This v1 uses the available local UI/UX SOP and Algolia brand tokens already used in the dashboard seed.

## Emphasis Rules

- One hero section per view: Decision Brief.
- Two to three primary groups max: Actions, Changes, Trust.
- Raw signals are supporting evidence.
- Archive is supporting navigation.

## Component Constraints

- Action cards must show owner, action, rationale, confidence, and evidence.
- Evidence must include source link, detected date, collector, and quality state.
- Tables must remain compact and secondary.
- Cards use 8px radius or less.
- Buttons use clear text commands: accept, assign, defer, reject, evidence.

## Responsive Requirements

- 375px: single-column layout, sticky nav becomes horizontally scrollable, cards stack.
- 768px: two-column sections where possible.
- 1024px: decision/actions/trust grid visible without horizontal scroll.
- 1280px+: dense command-center layout with constrained max width.

## Accessibility Requirements

- Text contrast meets WCAG 2.2 AA.
- Focus states visible.
- Touch targets at least 44px.
- Buttons have labels.
- Color is not the only status cue.
- Details disclosures expose evidence without JavaScript dependency.

## Constraints That Affect The Build

- Do not create a landing page.
- Do not build a pretty signal browser.
- Do not present unsupported claims as fact.
- Do not imply stakeholder-ready access before quality and auth are implemented.
