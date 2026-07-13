# AGENTS.md — CI-OS (Argus)

> Canonical agent instructions for this project. Tool-agnostic (Codex, Claude, and other agents read this). `CLAUDE.md` is a symlink to this file, so there is one source of truth. Follows the AGENTS.md open standard (agents.md).

## Project overview
CI-OS is a clean-slate **Competitive Intelligence operating system**. **Argus** is the product voice, orchestration brain, quality owner, and conversational interface. Argus is **Hermes-backed** and built to discover sources, collect evidence, synthesize semantic intelligence, monitor GTM and executive speech, update a dashboard, learn from every run, and deliver decision-grade insight. It is NOT a single daily-report bot.

**Stage: active implementation, build in progress.** The repo now contains a large CI-OS package, Hermes wrapper, admin service, dashboard renderer, intelligence spine, scripts, and tests. Read the planning docs and current workspace status before proposing or writing code.

## Start here (read in this order)
1. `index.md` — project home + full doc index.
2. `docs/planning/Argus-project-manifesto.md` and `CI-OS-project-overview.md` — what and why.
3. `docs/planning/CI-OS-persisted-state-2026-07-01.md` + `CI-OS-handoff-2026-07-01.md` — where things stand + resume.
4. The rest of `docs/planning/` for the specific area you are touching (data model, Hermes/Argus config, roadmap, eval, env/secrets, dashboard UX, channels/identity/ACL).
5. `skills/README.md` — skill build matrix.

## Toolchain
Use the commands already present in this repo and keep them current:

- `python3 -m pytest -q`
- `python3 scripts/verify_hermes_package_contract.py --app-dir /Users/arijitchowdhury/Dropbox/AI-Development/CI-OS`
- `python3 scripts/validate_dashboard_clicks.py --url https://ci.chowmes.com/ --tenant algolia`
- `python3 scripts/check_e2e_launch_readiness.py --public-status <argus-latest-run-status.json> --click-validation-log <click.log> --package-contract-log <package.log>`

## Conventions
- This is a Codex-primary project; Arijit also uses Claude on parts of the portfolio.
- Product voice is Argus everywhere user-facing.
- Design/plan first: this project is deliberately spec-heavy. Do not skip to code before the relevant planning doc is read and the approach is agreed.

## Security / off-limits (hard)
- **Never store real credentials in this project folder.** The env/secrets spec records variable NAMES and handling rules only (`docs/planning/CI-OS-env-and-secrets-spec.md`).
- Never commit secrets, `.env` files, or API keys.
- Ask before any destructive or irreversible action.

## Working with Arijit
Equal partner, never a yes-man: challenge assumptions, bring the angle he missed, debate to the right answer. No fabrication (unknown stays unknown); evidence on every claim; verify before claiming done. **No em dashes** in any reader-facing text. Full contract: vault `Projects/ArijitOS/Operating-Principles.md`.

## Portfolio context
CI-OS is one of Arijit's active projects (worked in Codex). Cross-project tracker: vault `Projects/ArijitOS/My-Projects.md`. Like PRISM and MyOS, Argus runs on Hermes as its engine.
