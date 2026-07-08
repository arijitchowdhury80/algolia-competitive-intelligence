# CI-OS — SESSION.md

Updated: 2026-07-07 (Claude Opus 4.8, caveman mode)

## Status
Argus V0 on Hermes was shipping empty "quiet day" briefs daily; root-caused + hotfixed (0→8 signals, live proof pending). Fable build goal-spec written and authorized. One hard blocker open (Claude provider on VPS).

## Resume action (do first, in order)
1. **Eyeball the 09:00 ET daily brief in Telegram** (chat 6789423537) the morning after 2026-07-07. Confirm it now shows real signals, not the empty quiet-day text. Report quality to next session.
2. **Fix the hard blocker:** no working Claude provider on the Hermes VPS (OpenRouter + Nous keys dead on credit). Either top up OpenRouter or add a direct `ANTHROPIC_API_KEY` to `/root/.hermes/.env`. Verify a live Claude call. Required before Fable's Gate 4.
3. **Redline the spec:** competitor sets (`CI-OS-Fable-build-goal-spec.md` §4) — approve or edit.
4. **Launch Fable:** `/clear` → `/model claude-fable-5` → effort `max` → paste the `/goal` prompt from `CI-OS-Fable-build-goal-spec.md` §8. Then sit through Gates 0-7, reviewing each report.

## Where we stopped (exact)
Spec + hotfix complete. Was offering to SSH into Hermes to get the exact Claude-provider fix (top-up vs direct key) before Arijit runs `/clear`. Arijit ran `/persist` instead. Provider check NOT yet done.

## Decisions locked (2026-07-07)
- Sequencing: hotfix-now + rebuild-for-Fable (V0 stays live until Fable Gate 6 parity, then cut over).
- Tenancy: multi-tenant from day 1 (Algolia, Spryker, Amplitude = 3 tenants).
- Models: tiered by task — cheap (Gemini/Haiku) for collection/extraction, Claude Opus for synthesis/thesis/quality, behind provider router.
- Channels: Telegram-rich → email → dashboard → WhatsApp/Apple Messages.
- Scope: full platform per spec, gated core-first (brain before breadth).
- Deadline: spec handoff by 2026-07-07 12:00 ET — MET.
- Hotfix: fix-and-deploy-now authorized (done).

## Remaining work
- Live-verify the hotfix (item 1 above).
- Clear the Claude-provider blocker (item 2).
- Telegram rich-message format (`parse_mode=HTML`) — deferred to Fable Gate 6.
- `bot_deliveries` observability + Telegram allowlist — Fable Gates 6 / 1.
- The whole Fable build (Gates 0-7).

## Reference files
- `docs/planning/CI-OS-Fable-build-goal-spec.md` — THE handoff spec (read first).
- `docs/planning/Argus-project-manifesto.md` — full capability spec.
- `../Research/docs/Competitive-Intel-Proof.md` — CI competitor teardown + copy/avoid.
- V0 on Hermes: container `hermes:/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence/skills/competitive-research/` (backup `ci_core.py.bak-20260707`).
- Vault: `Obsidian/Arijit-Second-Brain/Projects/CI-OS/index.md`.
- Memory: `ci-os-argus-state-2026-07-07`.

## What has NOT been done
- The hotfix is NOT live-verified (only dry-run proven). Do not claim it fixed until the 9AM brief is seen.
- The Claude provider on the VPS has NOT been checked or fixed.
- The Fable build has NOT started.
- No secrets were written to disk. No prod changes beyond the `ci_core.py` hotfix.

## Files written this session
- `docs/planning/CI-OS-Fable-build-goal-spec.md` (new), `index.md` (edited) — in CI-OS repo.
- `ci_core.py` hotfix on the Hermes VPS (backup saved).
- Vault: `Projects/CI-OS/index.md` + `log.md` (new), `wiki/log.md` + `wiki/hot.md` (appended).
- Memory: `ci-os-argus-state-2026-07-07.md` + `MEMORY.md` index line.
