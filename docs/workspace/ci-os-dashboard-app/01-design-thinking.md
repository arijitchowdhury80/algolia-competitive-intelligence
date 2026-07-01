# CI-OS Dashboard App Design Thinking

Date: 2026-07-01
Status: Planning baseline

## 1. Mental Model

Users will arrive carrying three mental models:

- Dashboard: what is happening now?
- Intelligence brief: what does this mean?
- Workflow cockpit: what should we do next?
- Messaging assistant: can I ask Argus from the channel I already use?

The app should not behave like a generic analytics dashboard. It should behave like an intelligence operating room: evidence, interpretation, confidence, and action in one place.

What would confuse users:

- Daily quiet state mixed with weekly strategic pattern.
- Metrics without evidence.
- Raw logs shown as status.
- Buttons that imply workflow but do nothing.
- Argus sounding like a passive summarizer instead of an intelligence lead.
- Telegram, WhatsApp, Apple Messages, and web app behaving like separate identities with inconsistent permissions.

## 2. Information Architecture

Hero:

- Current Argus read: the single most important interpretation for the selected cadence.

Primary:

- Material deltas.
- Confidence and coverage.
- Recommended actions.

Secondary:

- Source health.
- Delivery state.
- Channel access state.
- User and role state.
- Competitor movement by family.
- Content opportunities.
- Executive speech signals.

Supporting:

- Timestamps.
- Evidence links.
- Model tier used.
- Run ids.
- Public-source coverage limits.

Tier inflation risks:

- Do not turn every signal into a card.
- Do not make suppressed diagnostics look like findings.
- Do not make source failures look like competitor silence.

## 3. Interaction Flow

Most common actions:

1. Read today's Argus brief.
2. Inspect evidence behind a material delta.
3. Review recommended actions or weekly content plan.
4. Ask Argus a follow-up from web app, Telegram, WhatsApp, or Apple Messages for Business.

Happy path:

1. User logs in with Google.
2. User lands on Command Center.
3. User reads Argus current read.
4. User opens one material delta.
5. User checks evidence and confidence.
6. User reviews action or content recommendation.
7. User exports or shares the brief if needed.

Empty state:

- Say no material deltas were found only if source coverage and false-negative audit support it.
- Show coverage state prominently.

Loading state:

- Show latest completed report while the current run is processing.
- Label freshness clearly.

Error state:

- Use polished degraded-mode language.
- Show affected capability, not raw stack traces.

## 4. Cognitive Load Budget

Command Center first viewport should show no more than five chunks:

1. Navigation and date/cadence selector.
2. Argus current read.
3. Trust bar: freshness, coverage, delivery, model tier.
4. Material deltas.
5. Action queue or content recommendation preview.

Additional detail moves into tabs:

- Signals
- Sources
- Content
- Actions
- Archive
- Settings

## 5. Emotional Journey

Login:

- Feel secure and professional.

Command Center:

- Feel oriented in under ten seconds.

Delta detail:

- Feel evidence-backed confidence.

Actions:

- Feel momentum, not bureaucracy.

Content planning:

- Feel strategically useful and original, not opportunistic mimicry.

Settings:

- Feel controlled and auditable.

## 6. Design Pre-Mortem

Risk: generic AI dashboard.

- Mitigation: Argus-led language, strong evidence structure, disciplined visual hierarchy.

Risk: overload.

- Mitigation: Command Center uses progressive disclosure; detail tabs carry depth.

Risk: false certainty.

- Mitigation: coverage and confidence are always visible.

Risk: fake workflow.

- Mitigation: only show controls that have backing workflow objects.

Risk: ACL leakage across channels.

- Mitigation: channel identity is never trusted directly; every request resolves to canonical user plus permission set before Argus answers.

Risk: broken mobile.

- Mitigation: mobile becomes brief-first with stacked cards and tab drawer.

Risk: inaccessible dark UI.

- Mitigation: high contrast surfaces, visible focus, semantic labels, no color-only status.

## Aesthetic Choice

Chosen direction: enterprise intelligence cockpit.

Traits:

- Dense but calm.
- Restrained contrast.
- Evidence-first cards.
- Strong typography.
- Minimal ornament.
- Algolia-inspired technical clarity.

The official Algolia design-system path should be loaded before production implementation. It was not found at the documented local path during this planning pass.
