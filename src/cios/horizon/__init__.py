"""Multi-horizon industry research (the dot-connector).

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md, Addendum 2
point 1): Argus researches the last 10 / 30 / 60 days across the INDUSTRY --
not just the named competitors -- and brings in what is interesting and
helpful. This is what feeds weekly/monthly pattern synthesis
(cios.brain.cadence) with wider context than the tenant's own daily signal
ledger alone.

Two halves, same split as cios.brain (deterministic scan / LLM synthesis):
  - ledger_scan.py: pure bucketing of the tenant's own accumulated ledger
    (semantic_deltas / facts / signals) into D10/D30/D60 observation sets.
  - industry.py: BrainModel-driven synthesis of a HorizonRead per horizon,
    optionally widened with injected external IndustryFeed observations.
  - connector.py: the actual dot-connector -- ties this week's signals to
    the standing horizon reads.
"""
