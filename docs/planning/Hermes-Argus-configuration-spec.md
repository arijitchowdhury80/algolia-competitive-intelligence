# Hermes Argus Configuration Spec

Date: 2026-07-01
Status: Planning baseline
System: CI-OS

## Objective

Configure Hermes so Argus becomes the operating layer for CI-OS: scheduled executor, quality reviewer, conversational interface, delivery voice, and self-improvement loop.

## Naming Boundaries

- Chowmes: server and DNS umbrella.
- Hermes: runtime software.
- CI-OS: competitive intelligence product and project.
- Argus: product voice, CI CEO, orchestration agent, and channel identity.

Do not rename the Chowmes server. Rename and organize the CI product around Argus.

## Profile Strategy

V1 should use one primary Argus profile for the production CI loop.

Argus profile responsibilities:

- Own CI doctrine and voice.
- Run scheduled synthesis and review.
- Explain system status.
- Deliver readouts through approved channels.
- Review source coverage and false quiet.
- Propose improvements.

Specialist skills provide the muscle. Additional live Hermes profiles should be added only when there is a durable reason: separate memory, permissions, cadence, or delivery channel.

## Model Escalation

Default model policy:

| Tier | Intended use | Internal alias | Current provider target |
|------|--------------|----------------|-------------------------|
| Low | routing, extraction cleanup, small classification, source health notes | `gemini-flash-lite` | Current Gemini Flash-Lite family, for example `gemini-3.1-flash-lite` where available. |
| Standard | daily synthesis, moderate summarization, action routing, report narration | `gemini-flash` | Current Gemini Flash family, for example Gemini 3 Flash where available. |
| High | weekly synthesis, large multi-source reasoning, thesis updates, false-negative review, major strategy | `gemini-pro-high` | Current Gemini Pro family, for example Gemini 3.1 Pro where available. |
| Image | visual storytelling, report graphics, concept visuals | `nanobanana` | Current Nano Banana image family, usually Nano Banana 2 for production speed or Nano Banana Pro for premium visuals. |

Implementation rule:

- The model router should choose the lowest tier that can do the job well.
- Escalation must be recorded in run metadata: requested tier, actual model, reason, token/cost estimate if available, and output artifact.
- Weekly synthesis may default to high tier if the week has meaningful activity or wide source coverage.
- Quiet-day daily synthesis should not use high tier unless a false-negative audit flags risk.
- Provider model ids must be verified at implementation time and mapped behind stable internal aliases. Do not scatter provider ids across cron wrappers and skills.
- The model router must be provider-agnostic. Gemini can be the first configured provider, but CI-OS must be able to switch to OpenAI, Anthropic, Azure OpenAI, or another approved provider through config, credentials, provider adapters, and eval certification.

## Escalation Triggers

Escalate from low to standard when:

- The output becomes user-facing.
- More than one source family must be reconciled.
- The result includes a recommendation.
- There is conflict between sources.

Escalate from standard to high when:

- The system is producing weekly strategy.
- Multiple competitors have related movement.
- A competitor thesis changes.
- False-negative audit suggests likely missed activity.
- Argus must compare messaging, content performance, and market direction.
- The output will shape next-week content or executive action.

Do not escalate because a prompt is long. Escalate because the reasoning risk is high.

## Hermes Features To Enable

- Profiles: Argus production profile.
- Skills: CI-OS skills stored under `CI-OS/skills` until promoted into Argus.
- Cron: scheduled source hunting, collection, synthesis, review, learning, and delivery.
- Memory: approved project memory for durable decisions and lessons.
- Channel gateways: Telegram first, then WhatsApp and Apple Messages for Business through channel adapters.
- Web/search tooling: source discovery and evidence collection.
- X/Grok tooling: only after credentials and compliance are approved.
- Dashboard publish command: deterministic export step after synthesis.
- Gemini API integration should prefer the current recommended API surface for new agentic projects when Hermes supports it.

## Hermes Features To Gate

- Multi-agent delegation: phase 2, after single-profile workflows are stable.
- Kanban/task board: phase 2, when action workflow is real.
- Code execution from Telegram: disabled unless explicitly approved.
- Broad shell access from Argus: use deterministic wrappers and allowlists.
- Private data connectors: not in v1.
- Auto memory writes: require review or bounded rules.

## Cron Architecture

Recommended jobs:

| Job | Cadence | Agent mode | Model tier |
|-----|---------|------------|------------|
| source-hunter | daily, optional midday | no-agent plus Argus review | low or standard |
| intel-collector | daily | no-agent | low |
| executive-speech-scanner | daily | no-agent plus standard synthesis | low or standard |
| gtm-narrative-radar | daily | agent-backed summary | standard |
| content-intelligence | weekly plus daily observations | agent-backed | standard or high |
| semantic-synthesizer | daily | agent-backed | standard |
| weekly-synthesis | weekly | agent-backed | high |
| quality-reviewer | after synthesis | agent-backed | standard or high |
| delivery-commander | after review | no-agent delivery plus Argus narration | standard |
| learning-loop | after daily and weekly | agent-backed | standard |

## Runtime Guardrails

- Every run writes a run record.
- Every run writes source coverage state.
- Every user-facing claim links to evidence ids.
- Every delivery writes delivery state.
- Every failure becomes structured status, not raw log sludge.
- Every model escalation writes why it escalated.
- Every inbound channel message resolves to a canonical user and permission set before Argus or any skill runs.
- Every channel delivery writes channel-specific delivery state.

## Argus Voice Runtime Requirements

Argus must use `SOUL.md` as the source of truth. Do not patch voice through external scripts. After voice or prompt changes, refresh the Argus Telegram session and verify a fresh response.

Argus response spine:

1. Useful truth first.
2. What changed.
3. Why it matters.
4. What not to over-believe.
5. Recommended move.
6. Evidence.
7. Confidence.

## Visual Storytelling

Visuals are allowed when they clarify the story:

- Weekly market map.
- Competitor positioning shift.
- Narrative movement timeline.
- Content theme heatmap.
- Executive commentary quote map.
- Source coverage map.

Rules:

- Generated visuals must be labeled as generated.
- Generated visuals cannot be treated as evidence.
- Visuals should serve interpretation, not decorate reports.
- Use Algolia visual language for dashboard/report visuals.
