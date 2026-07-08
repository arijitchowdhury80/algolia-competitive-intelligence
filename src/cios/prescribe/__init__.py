"""The prescription engine: contextualize -> apply -> prescribe.

Doctrine (docs/planning/CI-OS-product-doctrine-2026-07-08.md, Addendum 2
point 3), Arijit verbatim: "Gather intel, contextualize it to MY business,
and hand me VERY specific strategies -- marketing strategies, ploys --
grounded in what was gathered. Not observations. Prescriptions."

Takes this cycle's signals (cios.brain), horizon connections
(cios.horizon), own-brand position (cios.ownbrand), and standing theses
(cios.brain), and turns them into a ranked, capped list of concrete plays
with a team, an urgency window, and evidence-backed grounding. No DB, no
network -- see engine.py for the deterministic vetting that runs regardless
of what the model claims about a candidate.
"""
