# CI-OS Product Doctrine — Arijit, verbatim intent (2026-07-08 morning)

> Recorded on Arijit's explicit order: "record all this shit... this is the gold."
> This document outranks any implementation detail. Every brief, dashboard, and
> module gets measured against THIS, not against what V0 did or what any
> competitor tool does.

## The motto

**"What is my competitor doing, and based on that, what intelligent task and
step and work should I do?"**

It is called INTELLIGENCE, not data mining. Data is mined every single day to
BUILD intelligence.

## The persona and the moment (the whole product in one scene)

I am the CMO of a company. I come in, I log in, and my CI-OS shows me, in very
clear visual terms:

- "This is what YOUR company is doing."
- "This is what THAT competitor did."
- "This is what is relevant to you FOR TODAY, for you to take action and
  involve this team and that team."

Where your competitor is. Where you are. Where you think they could go.

## Hard product rules (Arijit's words, normalized)

1. **NOT Algolia-specific.** Algolia is just the experiment currently running.
   CI-OS is a software product: modular, sellable to any company. Nothing in
   the intelligence layer may hardcode Algolia's vertical, competitors, or
   vocabulary.
2. **No feeder screen. No onboarding questionnaire.** "That's the 1950s."
   When CI-OS is sold to a company (target price point: ~$10,000), the seller
   has already researched the buyer's business and pre-built the competitor
   set. The customer logs in and it already knows who they are.
3. **Completely autonomous.** Monitor all competitors, check what they're
   doing online, grab the signals, transform signals into something that
   triggers an action for marketing (content or otherwise). No babysitting.
4. **Own scouting capability.** Learn by scouting the web ourselves: features,
   functionality, posts, everything, on a scripted 24-hour cycle.
5. **The cadence ladder — mine daily, boil upward:**
   - **Daily (24h):** digest everything learned, deliver succinct, lucid
     intelligence to marketing leadership: "In the last 24 hours, THIS
     happened; THIS is where you should pay attention."
   - **Weekly:** summarize, identify PATTERNS, provide a summarized action
     plan.
   - **Monthly:** boil the weekly up another level.
6. **Every signal lands as an action** naming which team gets involved
   (marketing, content, product, exec...). Signal without an action trigger is
   noise.
7. **Business stakes:** "based on these capabilities, our business, our
   product, is going to fail or bomb or be successful." This doctrine is the
   success criterion.

## What this changes in the build (translation to work items)

- The daily brief template is written to the CMO persona: your-company vs
  competitor framing, today's attention items, team-level action triggers.
  Tenant = "your company"; the brief speaks to the reader as the leader of
  that company, never as an Algolia analyst.
- Weekly synthesis = pattern detection over the daily ledger + action plan.
  Monthly = roll-up of weeklies. Both are first-class pipeline outputs, not
  afterthoughts.
- The dashboard's first screen answers: where competitor is / where you are /
  where they could go — the "three positions" view.
- Tenant onboarding is a seller-side pre-build (competitor set researched and
  seeded before the customer ever logs in), not a customer-side wizard.
- Modularity: intelligence layer must be domain-agnostic; Algolia's competitor
  set is seed data, never logic.

## Addendum (same day, later): freshness USP + Hermes packaging intent

**The USP is FRESHNESS.** Intelligence must be actionable AT THAT INSTANT —
"even 30 minutes after it may not be applicable... half a day after it will
not be applicable." The system monitors every channel and source, online and
offline, gets it inside, analyzes, and hands over critical actionable
instructions while they are still actionable. Daily cadence is the floor,
not the ceiling; the architecture must support near-real-time signal-to-action.

**Packaging intent: CI-OS ships WITH Hermes.** Arijit wants Hermes and the
custom Claude-built code (the V2 `cios` codebase) to become ONE product —
"one common code base and one common spine of execution" — with CI-OS as
Hermes's first flagship use case. Open architecture question, explicitly
assigned as a goal/loop to figure out: can Hermes be the center (gateway,
channels, scheduling, agent runtime) with cios as the domain brain, or do
they merge differently? Study assigned 2026-07-08.

## Addendum 2 (same day): why Argus beats a Klue subscription — the dot-connector

Arijit, verbatim intent: "If I'm a user and I got a Klue subscription, I got
all the professional subscriptions — why the hell should I even look at
Argus?" The answer, and therefore the product bar:

1. **Argus connects the dots.** Not another feed. It does research over the
   last 10 / 30 / 60 days (multi-horizon lookbacks) across the INDUSTRY, not
   just the named competitors, and brings in what is interesting and helpful.
2. **Argus researches the tenant's OWN brand too.** (Algolia today — plug
   and play, just the example.) Own-brand perception/position research is a
   first-class module beside competitor intel.
3. **Contextualize → apply → prescribe.** Gather intel, contextualize it to
   MY business, and hand me VERY specific strategies — marketing strategies,
   ploys — grounded in what was gathered. Not observations. Prescriptions.
4. **Offload collaterals from the intelligence.** A module that generates
   marketing collateral from gathered intel: marketing dashboards and
   marketing landing pages are the first two named. Intelligence that ends
   in a produced asset, not a paragraph.
5. Living doc discipline: Arijit adds product truth "as I'm remembering" —
   capture every drop here, keep enhancing. This doc is append-only gold.

## The dashboard experience bar (Addendum 2 continued)

Arijit has not yet seen a screen he considers Argus. The old CI screen is his
only reference. Dashboard must earn the "extraordinarily special" verdict:
the three-position view, multi-horizon industry research, own-brand read,
prescriptions with team routing, and generated collaterals — visible,
premium, interactive. Design phase = frontend-builder flow against THIS list.
