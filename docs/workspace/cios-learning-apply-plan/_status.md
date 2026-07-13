# CI-OS Learning Apply Plan

Status: implemented locally, verified by focused and full tests

## Purpose

Argus already records recommendation challenges and approved improvements as
next-sweep instructions. That changes the next run, but it does not yet tell an
operator what should become durable CI-OS package work.

This slice adds that missing bridge without touching Hermes core. The bridge
now has two steps: build an apply plan, then execute it safely as review
proposals or explicitly approved package-local policy records.

## Contract

- Apply-plan input: `next-sweep-learning-plan.json`.
- Apply-plan output: `learning-apply-plan.json`.
- Executor input: `learning-apply-plan.json`.
- Executor outputs:
  - proposal artifacts under `docs/workspace/cios-learning-apply-plan/proposals/`
  - approved, idempotent package policies under `config/*policy.yaml` only when
    `--approved-by` is supplied
- Scope: CI-OS package only.
- Safety: every action requires human approval and carries
  `touches_hermes_core: false`.
- Traceability: every action carries `evidence_event_ids` and
  `source_improvement_ids`.
- Default mutation: none. Proposal-only execution emits review artifacts.
- Approved mutation: package-local config policy writes only. No Hermes core,
  no source registry mutation, no prompt/code mutation.
- Future sweeps: `build_next_sweep_learning_plan.py` loads approved package
  policies and dedupes them against DB-approved queue items.
- Future sweep evidence: `next-sweep-learning-plan.json` includes
  `metadata` with DB instruction count, approved policy count, loaded policy
  instruction count, duplicate policy count, skipped policy count, and policy
  source trace rows. `daily_production_run.py` exposes this as
  `next_sweep_plan_summary`.
- Operator visibility: `GET /api/tenants/{tenant}/argus/learning-apply` and
  the local admin "Argus learning apply" section show pending proposals and
  approved package policies with trace ids. The same API/page also shows the
  current learning policy audit verdict, counts, issue rows, and rollback
  hints.
- Operator execution: `POST /api/tenants/{tenant}/argus/learning-apply/execute`
  and the matching local admin form execute only the latest run's recorded
  `learning_apply_plan_path`. Without `approved_by`, execution is proposal-only.
  With `approved_by`, execution writes approved package-local CI-OS policy
  records.
- Production audit: `scripts/audit_learning_policies.py` recomputes each
  approved policy action id, detects post-approval drift or invalid policy
  records, emits rollback guidance, and exits non-zero on unsafe policy state.
  `deploy/cios-daily.sh` runs this audit after package preflight and before
  schema, daily-run, rerender, or publish work.

## Files

- `src/cios/learn/feedback.py`
- `src/cios/learn/apply.py`
- `scripts/build_learning_apply_plan.py`
- `scripts/execute_learning_apply_plan.py`
- `scripts/audit_learning_policies.py`
- `scripts/build_next_sweep_learning_plan.py`
- `scripts/daily_production_run.py`
- `scripts/verify_hermes_package_contract.py`
- `deploy/cios-daily.sh`
- `src/cios/dashboard/types.py`
- `src/cios/dashboard/state_builder.py`
- `src/cios/dashboard/cockpit_renderer.py`
- `src/cios/admin/types.py`
- `src/cios/admin/learning_apply.py`
- `src/cios/admin/repository.py`
- `src/cios/admin/app.py`
- `tests/learn/test_feedback.py`
- `tests/learn/test_learning_apply_executor.py`
- `tests/learn/test_learning_policy_audit.py`
- `tests/scripts/test_build_learning_apply_plan.py`
- `tests/scripts/test_execute_learning_apply_plan.py`
- `tests/scripts/test_audit_learning_policies.py`
- `tests/scripts/test_build_next_sweep_learning_plan.py`
- `tests/scripts/test_daily_run.py`
- `tests/scripts/test_verify_hermes_package_contract.py`
- `tests/deploy/test_cios_daily_wrapper.py`
- `tests/dashboard/test_state_builder.py`
- `tests/dashboard/test_cockpit_renderer.py`
- `tests/admin/test_repository.py`
- `tests/admin/test_learning_apply.py`
- `tests/admin/test_app.py`

## Verification

- `python3 -m pytest tests/learn/test_feedback.py tests/scripts/test_build_learning_apply_plan.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short`
- `python3 -m pytest tests/admin/test_learning_apply.py tests/admin/test_app.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short`
- `python3 -m pytest tests/scripts/test_daily_run.py -q --tb=short`
- `python3 -m pytest tests/learn tests/scripts/test_execute_learning_apply_plan.py tests/scripts/test_build_learning_apply_plan.py tests/scripts/test_build_next_sweep_learning_plan.py tests/scripts/test_verify_hermes_package_contract.py tests/scripts/test_daily_run.py -q --tb=short`
- `python3 -m pytest tests/dashboard/test_cockpit_renderer.py tests/admin/test_app.py tests/dashboard/test_state_builder.py tests/admin/test_repository.py tests/learn tests/scripts/test_build_learning_apply_plan.py tests/scripts/test_build_next_sweep_learning_plan.py tests/scripts/test_daily_run.py tests/scripts/test_verify_hermes_package_contract.py -q --tb=short`
- `python3 -m pytest -q --tb=short`
- `python3 -m pytest tests/admin/test_learning_apply.py tests/admin/test_app.py tests/learn/test_learning_apply_executor.py tests/scripts/test_execute_learning_apply_plan.py tests/scripts/test_build_learning_apply_plan.py tests/scripts/test_build_next_sweep_learning_plan.py -q --tb=short`
- `python3 -m pytest tests/learn/test_feedback.py tests/learn/test_learning_apply_executor.py tests/scripts/test_build_next_sweep_learning_plan.py tests/scripts/test_build_learning_apply_plan.py tests/scripts/test_execute_learning_apply_plan.py tests/scripts/test_daily_run.py tests/scripts/test_verify_hermes_package_contract.py tests/admin/test_app.py tests/admin/test_learning_apply.py tests/dashboard/test_state_builder.py tests/dashboard/test_cockpit_renderer.py -q --tb=short`
- `python3 -m pytest tests/learn/test_learning_policy_audit.py tests/learn/test_learning_apply_executor.py tests/scripts/test_audit_learning_policies.py tests/scripts/test_execute_learning_apply_plan.py tests/scripts/test_build_next_sweep_learning_plan.py tests/scripts/test_verify_hermes_package_contract.py tests/deploy/test_cios_daily_wrapper.py -q --tb=short`
- `python3 -m pytest tests/admin/test_learning_apply.py tests/admin/test_app.py tests/learn/test_learning_policy_audit.py tests/scripts/test_audit_learning_policies.py tests/scripts/test_verify_hermes_package_contract.py tests/deploy/test_cios_daily_wrapper.py -q --tb=short`

Latest focused result: `75 passed in 5.24s`.
Latest focused result: `38 passed in 3.71s`.
Latest focused result: `230 passed in 1.91s`.
Latest focused result: `61 passed in 1.52s`.
Latest focused result: `169 passed in 2.13s`.
Latest admin/preflight result: `55 passed in 5.41s`.
Latest full result: `837 passed, 21 deselected in 6.60s`.
