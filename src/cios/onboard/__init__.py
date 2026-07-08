"""Tenant onboarding pipeline (Addendum 3.3, docs/planning/CI-OS-product-doctrine-2026-07-08.md).

No feeder screen, no customer-side wizard (doctrine rule 2): the seller
pre-researches the buyer and pre-builds the competitor set before the
customer ever logs in. This package is the executable version of that
pre-build: company in -> competitors researched -> sources discovered,
validated, and seeded. It re-runs whenever the central company changes; a
company swap produces a new tenant slug and never touches the prior tenant.
"""
