# Decision-First Dashboard v1 Design Thinking

Date: 2026-06-27

## 1. Mental Model

The user is not carrying a generic dashboard mental model. Arijit is looking for a competitive decision room: a place that turns raw market movement into actions, evidence, and quality control.

Expected:

- A clear top-level read on whether anything matters this week.
- A short list of decisions or actions, not a long list of scraped signals.
- Evidence links and confidence for every claim.
- Owner routing for Product, PMM, Sales Enablement, Partnerships, Exec, and CI Ops.

Confusing:

- Starting with raw signals.
- Treating first-run baseline changes as proven competitor deltas.
- Showing source health as the main story.
- Hiding recommended actions below tables.

## 2. Information Architecture

| Content element | Tier | Treatment |
|---|---|---|
| Weekly decision brief | Hero | One high-clarity panel with trust state, reporting window, and recommended executive posture |
| Top action recommendations | Primary | Action cards with owner, action, rationale, and controls |
| What changed this week | Primary | Delta cards grouped by market theme |
| Trust and evidence state | Primary | Source health, baseline risk, collector mix, quality gates |
| Stakeholder implications | Secondary | PMM/Product/Sales/Partnerships/Exec columns |
| Source health | Secondary | Compact operational panel |
| Signal ledger | Supporting | Search/audit table below decision sections |
| Archive | Supporting | Compact report links |

No tier inflation: signals and archive are supporting. They explain the decision, but they are not the decision.

## 3. Interaction Flow

Three common actions:

1. Accept, assign, defer, or reject a recommended action.
2. Open evidence for a claim.
3. Filter by owner or competitor to inspect why a recommendation exists.

Happy path:

1. User lands on Decision Brief.
2. User reads current trust state and top material changes.
3. User opens evidence for one recommendation.
4. User accepts or assigns the action.
5. User checks source health only if quality is degraded.

States:

- Empty: show "No material deltas cleared the evidence gate" with source coverage state.
- Loading: reserve stable card dimensions and use skeleton rows.
- Error: show collection/report failure with last successful run and recovery action.

## 4. Cognitive Load Budget

First viewport should contain five chunks:

1. Header and navigation.
2. Decision brief.
3. Action queue.
4. Change themes.
5. Trust state.

Raw signal tables and archive are placed lower and compacted.

## 5. Emotional Journey

- Initial: calm orientation. "I know whether this week matters."
- Review: confidence. "Every recommendation has evidence and quality state."
- Action: control. "I can accept, assign, reject, or ask for more proof."
- Audit: trust. "The raw data exists, but it is not dumped on me."

## 6. Design Pre-Mortem

Risk: The UI becomes another generic SaaS table.
Mitigation: The first section is a decision brief and action queue, not a data table.

Risk: Baseline signals are mistaken for deltas.
Mitigation: Use explicit baseline-risk labeling and block battlecard actions until confirmed delta.

Risk: Too much Algolia blue makes it one-note.
Mitigation: Use Algolia blue as command/action color with neutral surfaces and distinct owner colors.

Risk: Stakeholder users do not know what to do.
Mitigation: Each primary item has owner, action, evidence, and decision controls.

Risk: Static v1 suggests functionality that does not exist.
Mitigation: Label persisted state honestly in copy and keep controls as visual placeholders until the action API exists.
