# CI-OS

Date created: 2026-06-30
Status: Planning baseline with dashboard design still in progress
Product voice: Argus

## Purpose

CI-OS is the clean-slate Competitive Intelligence operating system project. Argus is the product voice, orchestration brain, quality owner, and conversational interface.

## Start Here

- [CI-OS Fable build goal spec (AUTHORIZED 2026-07-07)](docs/planning/CI-OS-Fable-build-goal-spec.md) — hand this to Fable; indexes everything, records verified ground truth + locked decisions + gated build order
- [Argus project manifesto](docs/planning/Argus-project-manifesto.md)
- [CI-OS project overview](docs/planning/CI-OS-project-overview.md)
- [Hermes Argus configuration spec](docs/planning/Hermes-Argus-configuration-spec.md)
- [Argus skill build matrix](docs/planning/Argus-skill-build-matrix.md)
- [CI-OS data model spec](docs/planning/CI-OS-data-model-spec.md)
- [Argus agent operating model](docs/planning/Argus-agent-operating-model.md)
- [CI-OS implementation roadmap](docs/planning/CI-OS-implementation-roadmap.md)
- [CI-OS evaluation plan](docs/planning/CI-OS-evaluation-plan.md)
- [CI-OS environment and secrets spec](docs/planning/CI-OS-env-and-secrets-spec.md)
- [CI-OS dashboard and app UX spec](docs/planning/CI-OS-dashboard-app-UX-spec.md)
- [CI-OS dashboard design checkpoint](docs/planning/CI-OS-dashboard-design-checkpoint-2026-07-01.md)
- [CI-OS channels, identity, ACL, and model provider architecture](docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md)
- [CI-OS persisted state](docs/planning/CI-OS-persisted-state-2026-07-01.md)
- [CI-OS handoff](docs/planning/CI-OS-handoff-2026-07-01.md)
- [Dashboard app design thinking](docs/workspace/ci-os-dashboard-app/01-design-thinking.md)
- [Dashboard app redesign direction](docs/workspace/ci-os-dashboard-app/02-redesign-direction.md)
- [Navigation, barometer, and hero decisions](docs/workspace/ci-os-dashboard-app/03-navigation-barometer-hero-decisions.md)
- [Dashboard app static mockup](docs/mockups/ci-os-dashboard-app-mockup.html)
- [CI-OS skills folder](skills/README.md)

## Current Direction

Build Argus as a Hermes-backed Competitive Intelligence OS, not a single daily report bot. The system should discover sources, collect evidence, synthesize semantic intelligence, monitor GTM and executive speech, update a dashboard, learn from every run, and deliver decision-grade insight through Argus.

## Current Design State

The dashboard/app planning is not final. The current mockup is a living design artifact and should continue to be reviewed section by section before any full build goal starts.

As of 2026-07-01, the accepted dashboard direction is a premium Argus cockpit using a Luxury Editorial / Maison visual language, a role-aware Marketing / Sales / Product command rail, an interactive Competitor Attention Barometer, inline report/article expansion, and an evidence-totality section called `The eye behind the lenses`.

Do not push this project to GitHub yet. Do not treat the dashboard mockup as final UI.

## Planning Baseline

The current build context is now split into:

- Product definition and scope.
- Hermes and model configuration.
- Skill creation order and eval requirements.
- Data contracts for source coverage, evidence, semantics, actions, delivery, and content planning.
- Agent operating model for Argus and specialist roles.
- Implementation roadmap.
- Evaluation and E2E certification plan.
- Environment and secrets handling.
- Dashboard/app UX, Google login, role model, data elements, and screen mockup.
- Multi-channel access, enterprise SSO, ACL, modular adapters, and model-provider abstraction.

Real credentials must not be stored in this project folder. The secrets spec records variable names and handling rules only.
