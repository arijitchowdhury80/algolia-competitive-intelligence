# Semantic Layer Design

Date: 2026-07-10
Status: Active implementation note

## Mental Model

The user expects Argus to behave like an intelligence partner, not a source ledger.

The screen must support three questions:

1. Which partner or competitor should I inspect?
2. What pattern is forming across the watched market?
3. Why should I trust, discount, or challenge the recommendation?
4. What happened before today, and does today's priority make sense against history?

What confuses the user:

- A list of signals without cross-competitor interpretation.
- A recommendation without a visible scoring basis.
- A navigation surface that cannot select the full watched universe.
- A heat map that looks decorative instead of encoding theme intensity.
- A "today only" read that cannot be checked against yesterday, last week, or last month.

## Information Architecture

Hero:

- Today's brief remains the entry read.

Primary:

- Semantic market layer.
- Market timeline and history controls.
- Partner selector covering the full monitored universe, not only material cards.
- Pattern map showing common themes across partners.
- Heat map showing theme intensity by partner.
- Direction and recommendation.
- Holistic daily coverage board showing every monitored partner's current state.
- Priority rationale explaining why the top partner outranks the rest.

Secondary:

- Confidence rubric with component scores.
- Data qualifications: source coverage, evidence count, quality gate, failed sources, public-source boundary.

Supporting:

- Exact source-health and registry appendices.
- Brief links.
- Generated timestamp.

## Interaction Flow

Common actions:

1. Select a partner from the drop-down.
2. Read what changed, why it matters, and what to do for that partner.
3. Check the timeline/history selector for prior days and weeks.
4. Inspect the holistic coverage board to see who was checked, quiet, degraded, or material.
5. Inspect the pattern map and confidence rubric before trusting the recommendation.

Happy path:

1. User reads today's brief.
2. User checks Market timeline to see the current day against available historical reports.
3. User checks Holistic daily coverage to see every monitored partner, not only the priority list.
4. User opens Semantic market layer.
5. User selects Constructor, Elastic, Algonomy, or any monitored competitor.
6. Selected competitor panel and role implications update.
7. User checks heat map, direction, recommendation, and confidence rubric.
8. User opens evidence or competitor brief.

States:

- Quiet competitor: selector still works and shows monitored-but-not-material copy.
- Failed sources: confidence rubric reduces source coverage score and names failed source count.
- No patterns: show "insufficient cross-partner pattern" instead of a fake trend.

## Cognitive Load Budget

Visible chunks in semantic layer:

1. Timeline/history controls.
2. Holistic daily coverage.
3. Partner selector.
4. Pattern map plus heat map.
5. Direction/recommendation plus confidence rubric.

This is the upper limit. Evidence details stay below as appendix content.

## Emotional Journey

- First: relief that "today" is not treated as the whole truth.
- Second: confidence that every monitored partner can be seen.
- Third: clarity about what competitors have in common.
- Fourth: healthy skepticism because confidence is scored visibly.
- Fifth: action orientation through a recommendation that names its basis.

## Design Pre-Mortem

Risks:

- Generic analytics look. Mitigation: keep Luxury Editorial / Maison tokens and use a "market thesis board" treatment.
- Fake intelligence. Mitigation: every pattern is deterministic and evidence-bound.
- Fake priority. Mitigation: show "Why this priority" using score, evidence count, signal count, and source health.
- Fake history. Mitigation: history controls only link to real report paths and explicitly show when no history is published.
- Too much detail. Mitigation: show pattern and score summaries first, evidence appendix second.
- Mobile crowding. Mitigation: heat map becomes a horizontal scroll grid; selector remains native and full width.
- Trust gap. Mitigation: confidence rubric shows factors and qualifications.

## Aesthetic

Use the existing Luxury Editorial / Maison direction:

- warm paper
- charcoal ink
- Playfair Display and Inter
- hairline rules
- restrained gold
- no generic SaaS gradient dashboard

Signature element: a "market thesis board" heat map. Rows are semantic themes. Columns are watched partners. Cell intensity is derived from source-backed card, prescription, thesis, and source-family matches.

## UI/UX Constraints

The documented UI/UX SOP path was not present locally during this pass:

`~/Library/CloudStorage/GoogleDrive-arijitchowdhury@algolia.com/My Drive/AI-Docs/Obsidian/ArijitOS-Brain/Standards/UIUXDesignSOP/index.md`

Applied constraints from project docs and active renderer:

- 375px, 768px, 1024px, 1280px responsive checks.
- Every interactive element needs an accessible label.
- Touch targets minimum 44px for selector and nav.
- Active state cannot be color-only.
- Confidence scoring must show what it is based on.
- No fake routes, no fake controls, no naked recommendation.
