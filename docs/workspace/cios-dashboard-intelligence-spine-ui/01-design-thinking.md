# Intelligence Spine UI Design Thinking

## Mental model

The user is not looking for another dashboard card. The mental model is an
operating read: Argus should show how it reached the recommendation, where the
evidence is strong, where it is weak, and what to do next.

Confusing pattern to avoid: separate product, market, demand, and action
widgets that force the user to assemble the logic manually.

## Information architecture

Hero:

- Today's read remains the hero. Do not create a second competing hero.

Primary:

- The intelligence spine: product reality, market conversation, audience demand,
  synthesis/actionability, and the next Argus operator action.
- Blocked action state: what missing plane prevents promotion.

Secondary:

- Leading entities.
- Leading capabilities.
- Evidence URL count and first evidence references.

Supporting:

- Plane-level counts and confidence notes.
- Raw source coverage remains in the appendix.

## Interaction flow

Common actions:

1. Read what Argus believes and why.
2. Inspect which evidence plane is missing or degraded.
3. Follow the next operator action, such as uploading demand evidence or
   opening the relevant evidence URLs.

Happy path:

1. User opens the dashboard.
2. User sees Today's read.
3. User sees the intelligence spine directly under the read / semantic layer
   flow.
4. User understands whether the recommendation is actionable, watch-only, or
   blocked.

Empty state:

- If no spine exists, show one short line that Argus has not produced the
  evidence spine for this run.

Error/degraded state:

- Missing planes must be labeled as missing, not hidden.

## Cognitive load budget

Target visible chunks for the section:

- Spine title and one-sentence purpose.
- Three evidence-plane cells.
- One actionability cell.
- One next-action line.

Everything else stays collapsed or subordinate. This avoids turning the spine
into another evidence appendix.

## Emotional journey

- First feeling: orientation. The user should know what the system is doing.
- Second feeling: confidence. The user should see evidence, not magic.
- Third feeling: agency. The user should know the next action Argus needs.

## Pre-mortem

- Risk: more clutter. Mitigation: plane summaries are compact; raw details stay
  in appendices.
- Risk: fake certainty. Mitigation: missing/degraded planes are visible.
- Risk: Argus feels like a label, not an agent. Mitigation: the section includes
  the next operator action and the blocked-action explanation.
- Risk: accessibility regressions. Mitigation: semantic section, headings,
  text labels, no color-only status.
