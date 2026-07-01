# CI-OS Persisted State

Date: 2026-07-01
Status: Planning packet persisted
Project home: `/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
Vault mirror: `/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS`

## Current State

CI-OS is in planning-complete / build-ready state.

The project has a clean local home and a matching vault mirror. The current packet defines the product, architecture, skills, data model, Hermes/Argus configuration, evaluation plan, environment and secrets rules, channel/identity/ACL model, and a premium dashboard cockpit mockup.

## Product Direction

CI-OS is a Hermes-powered Competitive Intelligence operating system.

Argus is the product voice and CI CEO:

- skeptical
- witty
- commercially sharp
- evidence-led
- not generic assistant copy

CI-OS must not be a single daily-report bot. It must become a competitive intelligence operating system with source hunting, evidence collection, semantic synthesis, dashboard updates, action routing, content intelligence, delivery, and learning.

## Major Decisions Captured

- CI-OS is the project/system name.
- Argus is the product voice and operating agent.
- Chowmes remains the host/server umbrella.
- Hermes is the runtime platform.
- Telegram is the first live channel, not the only channel.
- WhatsApp and Apple Messages for Business are planned as channel adapters.
- Apple Messages for Business is the enterprise path for iMessage-style access.
- Users must resolve to canonical identities before Argus answers.
- ACL and audit are platform-level concerns, not prompt-level concerns.
- Google OAuth/OIDC is the first SSO path; enterprise path includes OIDC, SAML, and SCIM.
- The data model is tenant-aware from the beginning.
- Model routing is provider-agnostic. Gemini can be first, but OpenAI, Anthropic, Azure OpenAI, and others must fit through adapters.
- Skills must be built with the official skill-creator workflow and evaluated.
- Real secrets must not be stored in Markdown or vault docs.
- The dashboard should be a premium Competitive Intelligence Cockpit, not an industrial reporting dashboard.

## Planning Packet

Read in this order:

1. `index.md`
2. `docs/planning/Argus-project-manifesto.md`
3. `docs/planning/CI-OS-project-overview.md`
4. `docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md`
5. `docs/planning/Hermes-Argus-configuration-spec.md`
6. `docs/planning/CI-OS-data-model-spec.md`
7. `docs/planning/Argus-agent-operating-model.md`
8. `docs/planning/Argus-skill-build-matrix.md`
9. `docs/planning/CI-OS-implementation-roadmap.md`
10. `docs/planning/CI-OS-evaluation-plan.md`
11. `docs/planning/CI-OS-env-and-secrets-spec.md`
12. `docs/planning/CI-OS-dashboard-app-UX-spec.md`
13. `docs/workspace/ci-os-dashboard-app/01-design-thinking.md`
14. `docs/workspace/ci-os-dashboard-app/02-redesign-direction.md`
15. `docs/mockups/ci-os-dashboard-app-mockup.html`
16. `skills/README.md`

## Dashboard Mockup State

The first dashboard mockup was rejected as too industrial and report-like.

The current mockup is a revised premium cockpit:

- top command rail
- Argus strategic read as hero
- Market Field as signature intelligence visualization
- selected-signal detail
- What matters now
- next-week content intelligence
- action rail
- evidence and coverage
- access and model control
- product route model

Login was removed from the authenticated cockpit. `/login` is now documented as a separate pre-auth route.

Mockup path:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/docs/mockups/ci-os-dashboard-app-mockup.html`

## Build-Ready Gates

The next build should stop at these gates:

1. Gate 0: planning packet read, architecture understood, implementation plan written.
2. Gate 1: platform foundation for tenant, identity, ACL, channels, and model providers validated.
3. Gate 2: data model and source ledger foundation validated.
4. Gate 3: source hunter and intel collector built and evaluated.
5. Gate 4: semantic synthesis, quality review, and false-negative audit working.
6. Gate 5: dashboard app and semantic data export working.
7. Gate 6: Argus delivery, voice, and delivery observability verified.
8. Gate 7: full daily and weekly E2E runs validated.

## Current Non-Build Caveats

- This is a planning packet, not yet implemented software.
- The dashboard mockup is a static HTML planning artifact.
- Official Algolia design-system assets were not found at the previously documented local path during the mockup pass.
- No real credentials have been written into Markdown.
- Private data connectors are intentionally out of scope.

## Verification At Persist Time

Run after this file is written:

- mirror local CI-OS to vault
- compare hashes local vs vault
- parse HTML mockup
- scan for obvious secret patterns

