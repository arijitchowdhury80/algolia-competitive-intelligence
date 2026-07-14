# Runtime Supervision Spec

## Builder

`module-builder`, because the change is a bounded backend/runtime module and
shell contract with no frontend surface.

## Contracts

`execute_product_surface_plan.py` must accept a per-item timeout, a bounded
batch timeout, and a bounded worker count. It must always attempt to write one
summary containing terminal status for every planned item.

The daily runner must use a product-surface batch timeout that is longer than
the executor's own deadline plus shutdown grace. Generic short-command timeout
configuration must not silently override that contract.

Subprocess timeout must terminate the full process group, wait for cleanup,
and preserve captured output for the error record.

Runtime success means the scheduled operating loop completed and emitted its
truthful readiness artifacts. It does not mean every future evidence plane is
ready. Product publication remains blocked whenever its evidence gates fail.

## Observability

Retain `CIOS_PRODUCT_MARKET_STAGE` start/done/failed events. Add batch budget,
terminal counts, and timeout/not-started status to the execution summary.

## Rollback

Redeploy commit `12b97ae6c6fb121a308e9755e7076b6291a04302`, restore the prior
service files, run package preflight, and trigger one Hermes cron smoke. No
schema migration is part of this slice.

## Feature flag

The existing `CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE` flag remains the rollout
control. No new public endpoint or schema is introduced.
