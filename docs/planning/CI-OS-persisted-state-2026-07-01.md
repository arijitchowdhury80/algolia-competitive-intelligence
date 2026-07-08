# CI-OS Persisted State

Date: 2026-07-01
Status: Planning packet persisted; dashboard design still in progress
Project home: `/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
Vault mirror: `/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS`

## Current State

CI-OS is in planning state. The system manifesto and architecture packet exist, but the dashboard/app design is still in active critique and is not final.

The project has a clean local home and a matching vault mirror. The current packet defines the product, architecture, skills, data model, Hermes/Argus configuration, evaluation plan, environment and secrets rules, channel/identity/ACL model, and a premium dashboard cockpit mockup under active design review.

Do not push this state to GitHub yet. Do not start the full build goal until the remaining dashboard/app sections and routes are designed.

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
- CI-OS top command rail uses three primary role lenses: Marketing, Sales, and Product.
- The hero must be concrete: name the competitor, why it matters, attention score, confidence, threat category, and what each lens should do.
- User-facing product brand is `Argus`, not `Argus CI-OS`.
- The accepted visual direction is Luxury Editorial / Maison.
- The Competitor Attention Barometer is the signature intelligence visualization.
- Barometer rows are accordions: folded state is the summary, opened state is the proof preview.
- Proof previews must drill into full reports/articles/source bibliographies. AWS currently demonstrates this pattern.
- Evidence and coverage are framed as `The eye behind the lenses`, the quantitative sightline behind Marketing, Sales, and Product conclusions.
- Access/model controls and route architecture explainers are removed from the daily cockpit surface and belong in Admin/spec docs.

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
13. `docs/planning/CI-OS-dashboard-design-checkpoint-2026-07-01.md`
14. `docs/workspace/ci-os-dashboard-app/01-design-thinking.md`
15. `docs/workspace/ci-os-dashboard-app/02-redesign-direction.md`
16. `docs/workspace/ci-os-dashboard-app/03-navigation-barometer-hero-decisions.md`
17. `docs/mockups/ci-os-dashboard-app-mockup.html`
18. `skills/README.md`

## Dashboard Mockup State

The first dashboard mockup was rejected as too industrial and report-like.

The current mockup is a revised premium cockpit, but it is not final:

- Argus masthead and role-aware Marketing / Sales / Product command rail
- concrete hero operating read
- generated editorial intelligence image
- Competitor Attention Barometer
- in-row proof preview accordions
- inline full brief/article/source-bibliography expansion for barometer rows
- Marketing, Sales, and Product role lenses
- evidence-totality section called `The eye behind the lenses`

Login, access/model controls, and route model explainers were removed from the authenticated cockpit. They remain valid product requirements, but they belong in `/login`, `/admin`, or planning/spec docs, not the daily intelligence surface.

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
- The dashboard/app design is still incomplete and should continue tomorrow before any build starts.
- Many sections remain undesigned or only partially designed: Signals, Reports archive, Actions workflow, Sources ledger, Content Intelligence, Admin, quiet/error states, and channel-share/screenshot flows.
- Official Algolia design-system assets were not found at the previously documented local path during the mockup pass.
- No real credentials have been written into Markdown.
- Private data connectors are intentionally out of scope.

## Verification At Persist Time

Run after this file is written:

- mirror local CI-OS to vault
- compare hashes local vs vault
- parse HTML mockup
- scan for obvious secret patterns
