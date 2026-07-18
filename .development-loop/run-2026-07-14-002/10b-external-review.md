# External Review

Draft pull request [#1](https://github.com/arijitchowdhury80/algolia-competitive-intelligence/pull/1)
provides the external review surface for the CI-OS package:

- Base: `ci-os-package-main`
- Head: `codex/ci-os-phase1-runtime`
- GitHub mergeability: `MERGEABLE`
- Draft status: open; it is not approved or ready to merge

The repository's existing remote `main` is an unrelated generated-dashboard
lineage with no merge base to the retained CI-OS package history. The verified
Phase 0 package baseline `12b97ae` was therefore published as the dedicated
`ci-os-package-main` source branch. No unrelated histories were merged and the
generated-dashboard `main` branch was not changed.

## Automated review evidence

The package lineage had no GitHub Actions workflow. TDD contract tests were
added before `.github/workflows/ci-os-package.yml`, which now runs the default
suite, strict static checks, package verification, and a disposable Postgres
integration suite for pull requests into `ci-os-package-main`.

The first run failed only at package verification after all preceding checks
passed: the verifier correctly reported `missing package python:
.venv/bin/python`. A GitHub checkout installed editable dependencies into the
runner Python rather than creating the deployment virtual environment. The CI
contract was narrowed to `--skip-python-imports`; imports remain covered by
`pip check`, Pyright, MyPy, and the full test suite. The regression contract
failed before that change and passed afterward.

Run [29326371217](https://github.com/arijitchowdhury80/algolia-competitive-intelligence/actions/runs/29326371217)
passed on commit `43533b9`:

- `static-and-unit`: PASS in 1m0s
- `postgres-integration`: PASS in 53s

There are no human review comments or approvals yet. Automated checks and
mergeability do not replace the Stage 12 staging approval or the later Finish
gate.
