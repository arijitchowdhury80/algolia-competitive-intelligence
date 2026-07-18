# Value Proposition

- Who: Argus, the CI operator, and Algolia teams consuming CI-OS output.
- Why: they must distinguish a complete current decision from a stale, mixed,
  partial, or unsafe release.
- Before: staged files are copied sequentially and readiness trusts assertions.
- How: immutable run generations, content manifests, independent scans,
  structured verdicts, and atomic pointers.
- After: each status is provably bound to one safe generation or one explicit
  blocked diagnostic.
- Alternative: per-file atomic writes still permit mixed generations.

Value proposition: For teams acting on CI-OS evidence, Publication Integrity
is a release-verification boundary that makes every visible result complete,
current, safe, and run-bound. Unlike sequential static-file copying, it proves
and promotes one generation at a time.

Tagline: One run, one truth.
