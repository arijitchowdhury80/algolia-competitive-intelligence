# Dashboard Operator Handoff Design Thinking

## Mental model

The user is reading an intelligence cockpit, not a data dump. The first question is not "what data exists?" but "can I trust and act on Argus right now?" The operator handoff should feel like the run's decision stamp: actionable, blocked, or limited.

## Information architecture

Hero: Argus readiness. One status: actionable, not actionable, needs review, unknown.

Primary:

- Next operator action.
- Top blocker or the absence of one.
- Primary command link when one exists.

Secondary:

- Handoff status.
- Blocking evidence task count.
- Brief bullet lines from Argus.

Supporting:

- Artifact path/found state.
- Work queue ids.
- Dashboard/work queue artifact refs.

## Interaction flow

Common actions:

1. Read readiness.
2. Follow the primary action or understand why action is blocked.
3. Use evidence coverage/proof chain to inspect the source of the blocker.

Happy path:

1. Dashboard opens with Argus readiness visible near the proof chain.
2. If blocked, user sees the blocker and action before reading dense evidence.
3. User follows the action or knows the public dashboard is read-only and admin must repair the evidence plane.

Empty/error states:

- Missing handoff: show "not recorded" and tell the user Hermes has not published an operator handoff yet.
- Artifact error: show not trustable and route to rebuild the handoff.
- Ready: show no blocker and ask the user to review/challenge recommendations.

## Cognitive load budget

The block gets at most four chunks:

- Readiness status.
- Next action.
- Top blocker.
- Optional brief bullets.

It should not add another long table to the dashboard.

## Emotional journey

The user should move from confusion to orientation. If Argus is blocked, the dashboard should say that plainly instead of pretending the intelligence is complete. If Argus is actionable, the dashboard should create confidence because the evidence gate is clear.

## Design pre-mortem

Risks:

- Looks like another diagnostic panel: mitigate by making readiness the lead and keeping artifact metadata small.
- Adds clutter to an already dense dashboard: mitigate by using one compact proof-chain section.
- Public page exposes admin-only write action: mitigate by showing command labels/links as read-only context and keeping actual writes in admin/local surfaces.
- Brand drift: use the existing Argus cockpit visual system and Algolia blue/status language, not a new palette.
