# Live Test UX Repair

Date: 2026-07-10
Status: Implemented in renderer, pending production publish

## Problem Observed

The production dashboard passed backend and click validation, but failed the human test. The visible surface made the user ask what they were supposed to understand because it led with implementation proof:

- A 27-card monitored competitor registry.
- Repeated "No material signal" boxes.
- Raw source-health rows.
- A cryptic "eye behind the lenses" diagnostics block.
- "Material signal" labels in the registry even when the current run had no promoted attention cards.

This was a product failure, not a user education issue. The backend proof was exposed as the main experience.

## Corrected Mental Model

The cockpit must open as an intelligence brief:

1. What changed today?
2. If nothing new crossed the threshold, what does that actually mean?
3. Which standing patterns still matter?
4. What should Algolia do next?
5. What confidence boundary applies because of source health?

Monitoring proof and source failures remain available, but as appendices.

## Implemented Changes

- Added a `Today’s competitive read` section directly after the hero.
- Added explicit quiet-run language: "No new material moves were promoted today."
- Added a standing watchlist sourced from monitored competitors with existing movement summaries.
- Added a next-action tile so the page tells the user what to do with the read.
- Added a confidence-boundary tile with competitor/source/failure counts.
- Collapsed `Monitored competitors` into an expandable registry appendix.
- Collapsed source diagnostics into an expandable `Source coverage and failures` appendix.
- Changed registry label from `Material signal` to `Standing pattern` so the registry does not imply a current-day material move.

## UX Constraint Applied

The missing local UIUX SOP path prevented direct loading of the external standard file. The applied constraints for this repair are:

- First screen must answer business meaning, not system state.
- Raw logs and coverage ledgers are supporting detail, not primary content.
- Empty/quiet states must distinguish "nothing new promoted" from "nothing monitored."
- Historical or standing patterns must not be labeled as current material signals.
- Every visible diagnostic block must explain what decision it supports.
- Source failures constrain confidence; they do not define the whole product experience.

## Validation Added

- `test_quiet_run_opens_with_executive_read_not_registry_wall`
- `test_registry_uses_standing_pattern_not_current_material_signal_label`

