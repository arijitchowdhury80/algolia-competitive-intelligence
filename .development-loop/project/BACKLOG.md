# CI-OS Backlog

Backlog is governed by the approved completion plan and current Phase 0
containment baseline.

Immediate backlog:

- Split retained work into domain-level review commits.
- Create a reproducible release identity for the deployed package.

Resolved 2026-07-14: CI-OS package source and release ownership

- Authoritative repository:
  `arijitchowdhury80/algolia-competitive-intelligence`.
- The repository's generated dashboard remains on `main`.
- The separately versioned CI-OS package uses `ci-os-package-main` as its
  protected source branch because the two lineages have no common ancestor.
- Package changes flow through pull requests into `ci-os-package-main`.
- Release candidates are identified by immutable commits and candidate tags;
  final release tags are created only after their release gate passes.
