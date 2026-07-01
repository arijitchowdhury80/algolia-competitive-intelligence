# CI-OS

Date created: 2026-06-30
Status: Fresh project home with planning baseline
Product voice: Argus

## Purpose

CI-OS is the clean-slate Competitive Intelligence operating system project. Argus is the product voice, orchestration brain, quality owner, and conversational interface.

## Start Here

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
- [CI-OS channels, identity, ACL, and model provider architecture](docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md)
- [CI-OS persisted state](docs/planning/CI-OS-persisted-state-2026-07-01.md)
- [CI-OS handoff](docs/planning/CI-OS-handoff-2026-07-01.md)
- [Dashboard app design thinking](docs/workspace/ci-os-dashboard-app/01-design-thinking.md)
- [Dashboard app static mockup](docs/mockups/ci-os-dashboard-app-mockup.html)
- [CI-OS skills folder](skills/README.md)

## Current Direction

Build Argus as a Hermes-backed Competitive Intelligence OS, not a single daily report bot. The system should discover sources, collect evidence, synthesize semantic intelligence, monitor GTM and executive speech, update a dashboard, learn from every run, and deliver decision-grade insight through Argus.

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
