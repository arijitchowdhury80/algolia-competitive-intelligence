# UX Correction: From Command Center Map To Guided Weekly Brief

Date: 2026-06-28

## What Failed In The First Decision-First Prototype

The first prototype used better ingredients than the original signal dashboard, but the information architecture was still confusing.

The failure was not visual polish. The failure was the user's task model.

Specific problems:

- The page still presented too many equally important zones: Decision brief, Actions, Trust, Operations, Archive, Material movement, Implications.
- Labels such as "Trust state", "Material movement", and "Operations" reflected internal system concepts, not the user's next action.
- The dashboard required Arijit to infer the workflow instead of giving him one.
- Action buttons appeared before persisted action workflow exists, which made the prototype feel more capable than it is.
- Source health and collector mix were too prominent for an executive/operator view. They matter only when trust is broken.
- The page answered "what objects exist in the system?" more than "what should I do now?"

## Correct Mental Model

This should feel like a weekly competitive brief with a clear decision path, not like a monitoring console.

The user should read it in this order:

1. Start here: what is the recommendation this week?
2. Choose one action: what should I review, assign, or ignore?
3. Check proof only when needed.
4. Check system health only if the trust state is degraded.

## Correct Information Architecture

| User question | Section | Treatment |
|---|---|---|
| What do I do now? | Start here | Hero |
| What requires my attention? | Action queue | Primary |
| Why does it matter? | Explanation inside each action | Primary |
| What evidence supports it? | Evidence drawer / proof table | Secondary |
| Can I trust this run? | Data quality sidebar | Secondary |
| What changed underneath? | Raw signals | Supporting |
| Where are reports? | Report links | Supporting |

## Design Rule

The page must use user verbs:

- Review this.
- Watch this.
- Do not act yet.
- Check proof.
- Open report.

Avoid internal nouns as top-level navigation:

- Decision brief.
- Trust state.
- Operations.
- Material movement.

## V2 Direction

The corrected v2 should:

- Use a single page flow instead of a dashboard grid.
- Keep the first viewport to one recommendation and one quality state.
- Replace action buttons with honest static statuses until persistence exists.
- Push source health into a compact "Data quality" panel.
- Make raw signals explicitly "proof behind the brief."
