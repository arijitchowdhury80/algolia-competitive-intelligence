# Dashboard Rebuild Contract

Date: 2026-07-10
Status: Active replacement contract

## Decision

Throw away the current cockpit information architecture. Keep the working CI-OS data contract and producer. Rebuild the public dashboard UI from first principles.

## What The Screen Must Communicate

The dashboard has one job: help an Algolia operator understand today’s competitive intelligence and decide what to do.

It must answer, in order:

1. What happened today?
2. Why does it matter?
3. What should Algolia do next?
4. Which competitor should I inspect?
5. What does this mean for Marketing, Sales, and Product?
6. What evidence and coverage supports the read?

If a section does not answer one of those questions, it is appendix material.

## New Information Architecture

Hero:

- `Today’s competitive brief`
- Current top move or quiet-state interpretation.
- One recommended action.
- Confidence boundary: competitor count, source count, failed source count.

Primary:

- `Priority moves`: a ranked competitor selector.
- `Selected competitor`: what changed, why it matters, recommended action, evidence, and brief link.
- `Role implications`: Marketing, Sales, Product cards that update with the selected competitor.

Secondary:

- `Market coverage`: monitored competitors table/list.
- `Evidence and source health`: failed sources and current coverage.

Supporting:

- generated timestamp
- source counts
- links to full briefs
- raw source URLs

## Interaction Contract

- Default selected competitor is the highest-ranked current move.
- Clicking a priority move selects that competitor.
- The selected competitor panel updates immediately.
- Marketing/Sales/Product implications update immediately.
- The active selection is visually obvious and named in plain language.
- Top navigation is stateful, not decorative: each item updates the URL hash, `aria-current`, and scroll position for a distinct section.
- Evidence navigation must open a real evidence section, not land at the same bottom scroll position as Role implications.
- `All competitors` is not a fake filter. If shown, it means the page is no longer focused on one competitor and role cards summarize the whole read.

## Language Rules

- Do not use system metaphors as product copy: no "lens", "barometer", "eye behind the lenses" as primary labels.
- Prefer operator language: "Today’s brief", "Priority moves", "What to do", "Evidence", "Coverage".
- Do not label historical/standing movement as today’s material signal.
- Quiet state must say "No new move crossed the action threshold," not imply nothing was monitored.

## Visual Rules

- Product chrome must preserve the Argus wordmark and aperture/watch mark. `Argus CI-OS` is a system/planning phrase, not the visible product brand.
- Preserve the accepted Luxury Editorial / Maison direction: warm paper, charcoal ink, Playfair Display, Inter, hairline rules, restrained gold, and image-led intelligence texture.
- First viewport must have one dominant read and one obvious next action.
- No wall of repeated competitor cards.
- No raw ledger above the decision layer.
- Role cards are cards because they are three distinct decision audiences.
- Evidence is visible but subordinate.
