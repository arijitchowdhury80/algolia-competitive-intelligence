# CI-OS Handoff

Date: 2026-07-01
Status: Ready for build goal

## One-Line Handoff

Build CI-OS from the disk planning packet, starting with platform foundation and stopping at each gate for validation.

## Start Here

Read:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/index.md`

Then read every linked planning, workspace, mockup, and skills document before implementing.

Do not build from chat memory.

## Canonical Paths

Local project home:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`

Vault mirror:

`/Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS`

Dashboard mockup:

`/Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/docs/mockups/ci-os-dashboard-app-mockup.html`

## Required Execution Posture

- Use `dev-loop` for the build lifecycle.
- Use test-driven development for implementation.
- Use the official skill-creator workflow for every Argus skill.
- Use parallel agents only after Gate 0 maps the docs, repo, Hermes/Chowmes state, data model, dashboard requirements, and skill dependencies.
- Do not claim completion without verification output.
- Do not store secrets in Markdown.
- Do not hardwire Gemini into business logic.
- Do not treat Telegram as the only interface.
- Do not reduce Argus to a generic assistant.

## Build Order

1. Platform foundation:
   - tenants
   - users
   - identities
   - roles
   - permissions
   - channel adapters
   - audit events
   - model provider adapters
   - model router

2. CI foundation:
   - competitor registry
   - source ledger
   - source observations
   - scan runs
   - coverage scoring

3. Skills:
   - source hunter
   - intel collector
   - executive speech scanner
   - GTM narrative radar
   - content intelligence
   - LinkedIn monitor
   - semantic synthesizer
   - claim ledger
   - competitor thesis engine
   - quality reviewer
   - false-negative auditor
   - action router
   - delivery commander
   - learning loop

4. Dashboard and app:
   - route model
   - Google login / OIDC foundation
   - command cockpit
   - Market Field
   - signals
   - sources
   - content
   - actions
   - reports
   - admin

5. Hermes / Argus:
   - Argus profile
   - model escalation
   - cron
   - delivery
   - fresh-session voice verification
   - E2E checks

## Gate Protocol

At each gate, report:

- what was built
- what files changed
- what tests ran
- exact verification output
- what failed or remains uncertain
- whether it is safe to continue

Do not advance past a gate if the foundation below it is not verified.

## Goal Prompt To Use

```text
/goal Build CI-OS end to end from the planning packet at /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS.

Read /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS/index.md first, then read every linked planning, workspace, mockup, and skills document before implementing.

Treat the vault mirror at /Users/arijitchowdhury/Dropbox/AI-Development/Personal/Obsidian-Vault/Projects/CI-OS as the knowledge mirror, but implement from the local CI-OS project home.

Execution rules:
1. Do not build from chat memory. Build from the docs on disk.
2. Use dev-loop for the build lifecycle.
3. Use the official skill-creator workflow for every Argus skill, including evals.
4. Use test-driven development for implementation work.
5. Use parallel agents only after Gate 0 has mapped the repo, docs, existing Chowmes/Hermes state, data model, dashboard requirements, and skill dependencies.
6. Stop at logical gates before continuing:
   - Gate 0: planning packet read, architecture understood, implementation plan written.
   - Gate 1: platform foundation for tenant, identity, ACL, channels, and model providers validated.
   - Gate 2: data model and source ledger foundation validated.
   - Gate 3: source hunter and intel collector built and evaluated.
   - Gate 4: semantic synthesis, quality review, and false-negative audit working.
   - Gate 5: dashboard app and semantic data export working.
   - Gate 6: Argus delivery, voice, and delivery observability verified.
   - Gate 7: full daily and weekly E2E runs validated.
7. At every gate, show what was built, what was tested, exact verification output, what remains, and whether it is safe to proceed.
8. Do not claim completion without live verification.
9. Do not put real secrets in Markdown or commit them.
10. Preserve Argus as the CI CEO voice: evidence-led, witty, skeptical, commercially sharp, never generic AI slop.

Build the CI-OS software, skills, database, dashboard, delivery loop, model escalation, content intelligence, evaluation framework, and Hermes/Argus operating configuration according to the planning packet.
```

## Current Best Next Step

Start the build goal and complete Gate 0 only:

- read the entire planning packet
- map the existing local and Chowmes/Hermes implementation state
- write an implementation plan
- identify required repo/app scaffold
- stop for human review before writing production code

