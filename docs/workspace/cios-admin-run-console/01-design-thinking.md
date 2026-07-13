# Admin Run Console Design Thinking

## Mental model

The user is not browsing a dashboard here. They are operating a machine. The expected mental model is a run console: latest run, product-market chain status, what learning changed, and whether Scout produced artifacts.

## Information architecture

Hero: latest product-market chain status.

Primary: report id/date, prioritized product surfaces, runner verdict.

Secondary: learning plan path, Scout artifact count, first few artifact paths.

Supporting: empty-state copy and metadata timestamps.

Anything beyond that belongs in detailed JSON/API responses, not the first admin view.

## Interaction flow

1. Operator opens `/admin?tenant=algolia`.
2. Operator reads whether the latest run was `ran`, `failed`, or skipped.
3. Operator follows up through JSON endpoint if they need raw machine-readable detail.

Empty state: say no run metadata has been recorded yet. Error state: show degraded/failed status from metadata, not a fake green state.

## Cognitive load

Keep it to one compact section with one summary row and one prioritized-target list. Do not add another dashboard inside the admin page.

## Emotional journey

The section should create operational confidence: "I can see what the system did." It should not try to persuade or decorate.

## Pre-mortem

Risk: the console becomes another noisy panel.
Mitigation: cap visible target/artifact rows and push raw detail to JSON.

Risk: stale or missing run metadata looks like success.
Mitigation: explicit empty/degraded states.

Risk: UI implies Hermes core owns CI-OS internals.
Mitigation: copy says Hermes ran the CI-OS package; data remains CI-OS report metadata.

