#!/bin/sh
# CI-OS app-user daily pipeline. This file is executable only by the cios account.
set -eu

APP=/opt/data/apps/cios
if [ -n "${CIOS_APP_DIR:-}" ]; then
  APP="$CIOS_APP_DIR"
elif [ ! -d "$APP" ]; then
  APP=/root/.hermes/apps/cios
fi

PUB=/opt/data/apps/algolia-competitive-intelligence/apps/dashboard/public
if [ -n "${CIOS_PUBLIC_DIR:-}" ]; then
  PUB="$CIOS_PUBLIC_DIR"
elif [ ! -d "$PUB" ]; then
  PUB=/root/.hermes/apps/algolia-competitive-intelligence/apps/dashboard/public
fi

set -a
if [ -n "${CIOS_ENV_FILE:-}" ]; then
  if [ ! -f "$CIOS_ENV_FILE" ]; then
    echo "missing CIOS env file: $CIOS_ENV_FILE" >&2
    exit 2
  fi
  . "$CIOS_ENV_FILE"
elif [ -f /opt/data/cios-env ]; then
  . /opt/data/cios-env
elif [ -f /root/.hermes/cios-env ]; then
  . /root/.hermes/cios-env
else
  echo "missing CIOS env file" >&2
  exit 2
fi
set +a

OUT="${CIOS_OUTPUT_DIR:-$APP/out}"
if [ -z "$OUT" ] || [ "$OUT" = "/" ]; then
  echo "unsafe CIOS output directory: $OUT" >&2
  exit 2
fi
case "$OUT" in
  "$APP/out"|"$APP/out/"*) ;;
  *)
    echo "unsafe CIOS output directory outside app output root: $OUT" >&2
    exit 2
    ;;
esac
if [ -L "$OUT" ]; then
  echo "unsafe CIOS output directory is a symlink: $OUT" >&2
  exit 2
fi
if [ -e "$OUT" ] && [ ! -d "$OUT" ]; then
  echo "unsafe CIOS output path is not a directory: $OUT" >&2
  exit 2
fi

export CIOS_DASHBOARD_OUT="$OUT/argus-dashboard.html"
export CIOS_COCKPIT_OUT="$CIOS_DASHBOARD_OUT"
export PYTHONUNBUFFERED=1
export PYTHONPATH="$APP/src${PYTHONPATH:+:$PYTHONPATH}"
export CIOS_MODEL_TIMEOUT_SECONDS="${CIOS_MODEL_TIMEOUT_SECONDS:-150}"
export CIOS_QUALITY_TIMEOUT_SECONDS="${CIOS_QUALITY_TIMEOUT_SECONDS:-75}"
export CIOS_CLAUDE_MAX_ATTEMPTS="${CIOS_CLAUDE_MAX_ATTEMPTS:-1}"
export CIOS_MAX_SYNTH_COMPETITORS="${CIOS_MAX_SYNTH_COMPETITORS:-4}"
export CIOS_SYNTH_DELTAS_PER_COMPETITOR="${CIOS_SYNTH_DELTAS_PER_COMPETITOR:-8}"
export CIOS_SYNTH_FACTS_PER_COMPETITOR="${CIOS_SYNTH_FACTS_PER_COMPETITOR:-12}"
export CIOS_ARTICLE_FETCH_CAP="${CIOS_ARTICLE_FETCH_CAP:-1}"
export CIOS_ENABLE_OWN_BRAND_READ="${CIOS_ENABLE_OWN_BRAND_READ:-0}"
export CIOS_ENABLE_PRESCRIPTIONS="${CIOS_ENABLE_PRESCRIPTIONS:-0}"
export CIOS_ENABLE_LLM_THESIS_UPDATE="${CIOS_ENABLE_LLM_THESIS_UPDATE:-0}"
export CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE="${CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE:-1}"
export CIOS_PRODUCT_MARKET_PROVIDER="${CIOS_PRODUCT_MARKET_PROVIDER:-gemini/gemini-2.5-flash}"
export CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS="${CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS:-3}"
export CIOS_PRODUCT_MARKET_EXPORT_COMMAND_TIMEOUT_SECONDS="${CIOS_PRODUCT_MARKET_EXPORT_COMMAND_TIMEOUT_SECONDS:-300}"
export CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS="${CIOS_PRODUCT_MARKET_EXPORT_BATCH_TIMEOUT_SECONDS:-600}"
export CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS="${CIOS_PRODUCT_MARKET_EXPORT_STAGE_TIMEOUT_SECONDS:-630}"
export CIOS_PRODUCT_MARKET_WORKDIR="${CIOS_PRODUCT_MARKET_WORKDIR:-$APP/tmp/product-market}"
export CIOS_SCOUT_BIN="${CIOS_SCOUT_BIN:-$APP/scripts/scout_http_shim}"
export CIOS_ENABLE_PRODUCT_MUSCLE_GAP_DISCOVERY="${CIOS_ENABLE_PRODUCT_MUSCLE_GAP_DISCOVERY:-1}"
export CIOS_PRODUCT_MUSCLE_GAP_TENANT="${CIOS_PRODUCT_MUSCLE_GAP_TENANT:-${CIOS_DELIVER_TENANT:-algolia}}"
export CIOS_PRODUCT_MUSCLE_GAP_FETCH_TIMEOUT_SECONDS="${CIOS_PRODUCT_MUSCLE_GAP_FETCH_TIMEOUT_SECONDS:-5}"
export CIOS_PRODUCT_MUSCLE_GAP_FETCH_RETRIES="${CIOS_PRODUCT_MUSCLE_GAP_FETCH_RETRIES:-0}"
export CIOS_ENABLE_PRODUCT_SURFACE_CANDIDATE_PROMOTION="${CIOS_ENABLE_PRODUCT_SURFACE_CANDIDATE_PROMOTION:-1}"
export CIOS_PRODUCT_SURFACE_PROMOTION_TENANT="${CIOS_PRODUCT_SURFACE_PROMOTION_TENANT:-$CIOS_PRODUCT_MUSCLE_GAP_TENANT}"
export CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE="${CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE:-product_muscle_gap_plan}"
export CIOS_PRODUCT_SURFACE_PROMOTED_BY="${CIOS_PRODUCT_SURFACE_PROMOTED_BY:-hermes}"
if [ -d "$OUT" ] && [ ! -f "$OUT/.cios-output-dir" ]; then
  echo "refusing to clean unmarked CIOS output directory: $OUT" >&2
  exit 2
fi
mkdir -p "$OUT" "$PUB"
touch "$OUT/.cios-output-dir"
find "$OUT" -mindepth 1 ! -name .cios-output-dir -exec rm -rf -- {} +
mkdir -p "$CIOS_PRODUCT_MARKET_WORKDIR"
chmod 2775 "$CIOS_PRODUCT_MARKET_WORKDIR" 2>/dev/null || true

cd "$APP"
preflight_args="--app-dir $APP"
case "$(printf '%s' "$CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    preflight_args="$preflight_args --require-scout --scout-bin $CIOS_SCOUT_BIN"
    ;;
esac
.venv/bin/python scripts/verify_hermes_package_contract.py $preflight_args
.venv/bin/python scripts/audit_learning_policies.py --package-root "$APP"
.venv/bin/python scripts/apply_product_market_schema.py

run_argus_demand_intake_sidecar() {
  set +e
  .venv/bin/python scripts/run_argus_demand_intake.py \
    --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
    --app-dir "$APP" \
    --work-root "$CIOS_PRODUCT_MARKET_WORKDIR" \
    --out-dir "$OUT" \
    --dashboard "$OUT/argus-dashboard.json" \
    --python-bin ".venv/bin/python" \
    --record-history \
    --output "$OUT/argus-demand-intake.json"
  DEMAND_INTAKE_CODE=$?
  set -e
  if [ ! -s "$OUT/argus-demand-intake.json" ]; then
    echo "missing demand intake artifact from current run: $OUT/argus-demand-intake.json" >&2
    exit 2
  fi
}

write_public_run_status() {
  publish_status="$1"
  if [ ! -f scripts/export_public_run_status.py ]; then
    return 0
  fi
  .venv/bin/python scripts/export_public_run_status.py \
    --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
    --manifest "$OUT/argus-data-plane-manifest.json" \
    --dashboard "$OUT/argus-dashboard.json" \
    --publish-status "$publish_status" \
    --output "$OUT/argus-public-run-status.json"
}

publish_public_run_status() {
  if [ ! -s "$OUT/argus-public-run-status.json" ]; then
    return 0
  fi
  mkdir -p "$PUB/data" "$PUB/v2/data"
  cp "$OUT/argus-public-run-status.json" "$PUB/data/argus-latest-run-status.json"
  cp "$OUT/argus-public-run-status.json" "$PUB/v2/data/argus-latest-run-status.json"
  if [ -s "$OUT/argus-demand-plan-template.csv" ]; then
    cp "$OUT/argus-demand-plan-template.csv" "$PUB/data/argus-demand-plan-template.csv"
    cp "$OUT/argus-demand-plan-template.csv" "$PUB/v2/data/argus-demand-plan-template.csv"
  fi
  if [ -s "$OUT/argus-demand-work-order-guide.json" ]; then
    cp "$OUT/argus-demand-work-order-guide.json" "$PUB/data/argus-demand-work-order-guide.json"
    cp "$OUT/argus-demand-work-order-guide.json" "$PUB/v2/data/argus-demand-work-order-guide.json"
  fi
}

set +e
.venv/bin/python scripts/daily_production_run.py
DAILY_CODE=$?
set -e
if [ "$DAILY_CODE" -ne 0 ]; then
  set +e
  .venv/bin/python scripts/check_argus_demand_source_gate.py \
    --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
    --app-dir "$APP" \
    --work-root "$CIOS_PRODUCT_MARKET_WORKDIR" \
    --dashboard "$OUT/argus-dashboard.json" \
    --output "$OUT/argus-demand-source-gate.json"
  DEMAND_SOURCE_GATE_CODE=$?
  set -e
  if [ -s "$OUT/argus-dashboard.json" ]; then
    case "$(printf '%s' "$CIOS_ENABLE_PRODUCT_MUSCLE_GAP_DISCOVERY" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes|on)
        .venv/bin/python scripts/execute_product_muscle_gap_discovery.py \
          --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
          --gap-plan "$OUT/argus-dashboard.json" \
          --output "$OUT/product-muscle-gap-discovery-summary.json" \
          --fetch-timeout-seconds "$CIOS_PRODUCT_MUSCLE_GAP_FETCH_TIMEOUT_SECONDS" \
          --fetch-retries "$CIOS_PRODUCT_MUSCLE_GAP_FETCH_RETRIES"
        ;;
    esac

    case "$(printf '%s' "$CIOS_ENABLE_PRODUCT_SURFACE_CANDIDATE_PROMOTION" | tr '[:upper:]' '[:lower:]')" in
      1|true|yes|on)
        if [ -n "${CIOS_PRODUCT_SURFACE_PROMOTION_LIMIT:-}" ]; then
          .venv/bin/python scripts/promote_product_surface_candidates.py \
            --tenant "$CIOS_PRODUCT_SURFACE_PROMOTION_TENANT" \
            --discovery-source "$CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE" \
            --promoted-by "$CIOS_PRODUCT_SURFACE_PROMOTED_BY" \
            --limit "$CIOS_PRODUCT_SURFACE_PROMOTION_LIMIT" \
            --output "$OUT/product-surface-candidate-promotion-summary.json"
        else
          .venv/bin/python scripts/promote_product_surface_candidates.py \
            --tenant "$CIOS_PRODUCT_SURFACE_PROMOTION_TENANT" \
            --discovery-source "$CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE" \
            --promoted-by "$CIOS_PRODUCT_SURFACE_PROMOTED_BY" \
            --output "$OUT/product-surface-candidate-promotion-summary.json"
        fi
        ;;
    esac

    .venv/bin/python scripts/export_argus_demand_readiness.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --app-dir "$APP" \
      --work-root "$CIOS_PRODUCT_MARKET_WORKDIR" \
      --dashboard "$OUT/argus-dashboard.json" \
      --output "$OUT/argus-demand-readiness.json"

    .venv/bin/python scripts/export_argus_demand_plan_template.py \
      --readiness "$OUT/argus-demand-readiness.json" \
      --output "$OUT/argus-demand-plan-template.csv" \
      --guide-output "$OUT/argus-demand-work-order-guide.json" \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT"

    run_argus_demand_intake_sidecar

    .venv/bin/python scripts/attach_post_run_summaries.py \
      --dashboard "$OUT/argus-dashboard.json" \
      --gap-summary "$OUT/product-muscle-gap-discovery-summary.json" \
      --candidate-promotion-summary "$OUT/product-surface-candidate-promotion-summary.json" \
      --demand-readiness "$OUT/argus-demand-readiness.json"

    .venv/bin/python scripts/rerender_dashboard.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --out-dir "$OUT"

    .venv/bin/python scripts/export_argus_evidence_work_queue.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --output "$OUT/argus-evidence-work-queue.json"

    .venv/bin/python scripts/export_argus_product_muscle_work_queue.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --demand-readiness "$OUT/argus-demand-readiness.json" \
      --output "$OUT/argus-product-muscle-work-queue.json"

    .venv/bin/python scripts/build_argus_operator_handoff.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --work-queue "$OUT/argus-evidence-work-queue.json" \
      --product-muscle-queue "$OUT/argus-product-muscle-work-queue.json" \
      --demand-readiness "$OUT/argus-demand-readiness.json" \
      --demand-plan-template "$OUT/argus-demand-plan-template.csv" \
      --dashboard "$OUT/argus-dashboard.json" \
      --output "$OUT/argus-operator-handoff.json"

    if [ -s "$CIOS_DASHBOARD_OUT" ]; then
      .venv/bin/python scripts/attach_operator_handoff_to_dashboard.py \
        --dashboard "$OUT/argus-dashboard.json" \
        --handoff "$OUT/argus-operator-handoff.json" \
        --html "$CIOS_DASHBOARD_OUT"
    fi

    .venv/bin/python scripts/export_argus_data_plane_manifest.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --dashboard "$OUT/argus-dashboard.json" \
      --demand-readiness "$OUT/argus-demand-readiness.json" \
      --demand-plan-template "$OUT/argus-demand-plan-template.csv" \
      --demand-intake "$OUT/argus-demand-intake.json" \
      --evidence-work-queue "$OUT/argus-evidence-work-queue.json" \
      --product-muscle-work-queue "$OUT/argus-product-muscle-work-queue.json" \
      --operator-handoff "$OUT/argus-operator-handoff.json" \
      --output "$OUT/argus-data-plane-manifest.json"

    write_public_run_status blocked
    publish_public_run_status
  else
    echo "skipping Argus operator sidecars after failed daily run: missing $OUT/argus-dashboard.json" >&2
  fi
  echo "daily production runner exited with $DAILY_CODE; demand source gate exited with $DEMAND_SOURCE_GATE_CODE" >&2
  if [ "$DAILY_CODE" -eq 3 ] && [ "$DEMAND_SOURCE_GATE_CODE" -eq 2 ]; then
    echo "runtime completed with blocked evidence readiness; Hermes execution is healthy and publication remains blocked" >&2
    exit 0
  fi
  exit "$DAILY_CODE"
fi

case "$(printf '%s' "$CIOS_ENABLE_PRODUCT_MUSCLE_GAP_DISCOVERY" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    .venv/bin/python scripts/execute_product_muscle_gap_discovery.py \
      --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
      --gap-plan "$OUT/argus-dashboard.json" \
      --output "$OUT/product-muscle-gap-discovery-summary.json" \
      --fetch-timeout-seconds "$CIOS_PRODUCT_MUSCLE_GAP_FETCH_TIMEOUT_SECONDS" \
      --fetch-retries "$CIOS_PRODUCT_MUSCLE_GAP_FETCH_RETRIES"
    ;;
esac

case "$(printf '%s' "$CIOS_ENABLE_PRODUCT_SURFACE_CANDIDATE_PROMOTION" | tr '[:upper:]' '[:lower:]')" in
  1|true|yes|on)
    if [ -n "${CIOS_PRODUCT_SURFACE_PROMOTION_LIMIT:-}" ]; then
      .venv/bin/python scripts/promote_product_surface_candidates.py \
        --tenant "$CIOS_PRODUCT_SURFACE_PROMOTION_TENANT" \
        --discovery-source "$CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE" \
        --promoted-by "$CIOS_PRODUCT_SURFACE_PROMOTED_BY" \
        --limit "$CIOS_PRODUCT_SURFACE_PROMOTION_LIMIT" \
        --output "$OUT/product-surface-candidate-promotion-summary.json"
    else
      .venv/bin/python scripts/promote_product_surface_candidates.py \
        --tenant "$CIOS_PRODUCT_SURFACE_PROMOTION_TENANT" \
        --discovery-source "$CIOS_PRODUCT_SURFACE_PROMOTION_SOURCE" \
        --promoted-by "$CIOS_PRODUCT_SURFACE_PROMOTED_BY" \
        --output "$OUT/product-surface-candidate-promotion-summary.json"
    fi
    ;;
esac

if [ ! -s "$CIOS_DASHBOARD_OUT" ]; then
  echo "missing dashboard artifact from current run: $CIOS_DASHBOARD_OUT" >&2
  exit 2
fi
if [ ! -s "$OUT/brief.html" ]; then
  echo "missing brief artifact from current run: $OUT/brief.html" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-dashboard.json" ]; then
  echo "missing dashboard JSON artifact from current run: $OUT/argus-dashboard.json" >&2
  exit 2
fi

.venv/bin/python scripts/export_argus_demand_readiness.py \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
  --app-dir "$APP" \
  --work-root "$CIOS_PRODUCT_MARKET_WORKDIR" \
  --dashboard "$OUT/argus-dashboard.json" \
  --output "$OUT/argus-demand-readiness.json"

.venv/bin/python scripts/export_argus_demand_plan_template.py \
  --readiness "$OUT/argus-demand-readiness.json" \
  --output "$OUT/argus-demand-plan-template.csv" \
  --guide-output "$OUT/argus-demand-work-order-guide.json" \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT"

run_argus_demand_intake_sidecar

.venv/bin/python scripts/attach_post_run_summaries.py \
  --dashboard "$OUT/argus-dashboard.json" \
  --gap-summary "$OUT/product-muscle-gap-discovery-summary.json" \
  --candidate-promotion-summary "$OUT/product-surface-candidate-promotion-summary.json" \
  --demand-readiness "$OUT/argus-demand-readiness.json"

.venv/bin/python scripts/rerender_dashboard.py \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
  --out-dir "$OUT"

if [ ! -s "$CIOS_DASHBOARD_OUT" ]; then
  echo "missing dashboard artifact from current run: $CIOS_DASHBOARD_OUT" >&2
  exit 2
fi
if [ ! -s "$OUT/brief.html" ]; then
  echo "missing brief artifact from current run: $OUT/brief.html" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-dashboard.json" ]; then
  echo "missing dashboard JSON artifact from current run: $OUT/argus-dashboard.json" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-demand-readiness.json" ]; then
  echo "missing demand readiness artifact from current run: $OUT/argus-demand-readiness.json" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-demand-plan-template.csv" ]; then
  echo "missing demand plan template artifact from current run: $OUT/argus-demand-plan-template.csv" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-demand-work-order-guide.json" ]; then
  echo "missing demand work-order guide artifact from current run: $OUT/argus-demand-work-order-guide.json" >&2
  exit 2
fi

.venv/bin/python scripts/export_argus_evidence_work_queue.py \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
  --output "$OUT/argus-evidence-work-queue.json"

if [ ! -s "$OUT/argus-evidence-work-queue.json" ]; then
  echo "missing evidence work queue artifact from current run: $OUT/argus-evidence-work-queue.json" >&2
  exit 2
fi

.venv/bin/python scripts/export_argus_product_muscle_work_queue.py \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
  --demand-readiness "$OUT/argus-demand-readiness.json" \
  --output "$OUT/argus-product-muscle-work-queue.json"

if [ ! -s "$CIOS_DASHBOARD_OUT" ]; then
  echo "missing dashboard artifact from current run: $CIOS_DASHBOARD_OUT" >&2
  exit 2
fi
if [ ! -s "$OUT/brief.html" ]; then
  echo "missing brief artifact from current run: $OUT/brief.html" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-dashboard.json" ]; then
  echo "missing dashboard JSON artifact from current run: $OUT/argus-dashboard.json" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-product-muscle-work-queue.json" ]; then
  echo "missing product muscle work queue artifact from current run: $OUT/argus-product-muscle-work-queue.json" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-demand-readiness.json" ]; then
  echo "missing demand readiness artifact from current run: $OUT/argus-demand-readiness.json" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-demand-plan-template.csv" ]; then
  echo "missing demand plan template artifact from current run: $OUT/argus-demand-plan-template.csv" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-demand-work-order-guide.json" ]; then
  echo "missing demand work-order guide artifact from current run: $OUT/argus-demand-work-order-guide.json" >&2
  exit 2
fi

.venv/bin/python scripts/build_argus_operator_handoff.py \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
  --work-queue "$OUT/argus-evidence-work-queue.json" \
  --product-muscle-queue "$OUT/argus-product-muscle-work-queue.json" \
  --demand-readiness "$OUT/argus-demand-readiness.json" \
  --demand-plan-template "$OUT/argus-demand-plan-template.csv" \
  --dashboard "$OUT/argus-dashboard.json" \
  --output "$OUT/argus-operator-handoff.json"

if [ ! -s "$OUT/argus-operator-handoff.json" ]; then
  echo "missing Argus operator handoff artifact from current run: $OUT/argus-operator-handoff.json" >&2
  exit 2
fi

.venv/bin/python scripts/attach_operator_handoff_to_dashboard.py \
  --dashboard "$OUT/argus-dashboard.json" \
  --handoff "$OUT/argus-operator-handoff.json" \
  --html "$CIOS_DASHBOARD_OUT"

.venv/bin/python scripts/export_argus_data_plane_manifest.py \
  --tenant "$CIOS_PRODUCT_MUSCLE_GAP_TENANT" \
  --dashboard "$OUT/argus-dashboard.json" \
  --demand-readiness "$OUT/argus-demand-readiness.json" \
  --demand-plan-template "$OUT/argus-demand-plan-template.csv" \
  --demand-intake "$OUT/argus-demand-intake.json" \
  --evidence-work-queue "$OUT/argus-evidence-work-queue.json" \
  --product-muscle-work-queue "$OUT/argus-product-muscle-work-queue.json" \
  --operator-handoff "$OUT/argus-operator-handoff.json" \
  --output "$OUT/argus-data-plane-manifest.json"

if [ ! -s "$CIOS_DASHBOARD_OUT" ]; then
  echo "missing dashboard artifact after operator handoff attach: $CIOS_DASHBOARD_OUT" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-dashboard.json" ]; then
  echo "missing dashboard JSON artifact after operator handoff attach: $OUT/argus-dashboard.json" >&2
  exit 2
fi
if [ ! -s "$OUT/argus-data-plane-manifest.json" ]; then
  echo "missing Argus data-plane manifest artifact from current run: $OUT/argus-data-plane-manifest.json" >&2
  exit 2
fi
if [ ! -d "$OUT/briefs" ]; then
  echo "missing competitor briefs directory from current run: $OUT/briefs" >&2
  exit 2
fi

write_public_run_status published

STAGE="$PUB/.argus-publish.$$"
rm -rf "$STAGE"
trap 'rm -rf "$STAGE"' EXIT INT TERM
mkdir -p "$STAGE/data" "$STAGE/v2/data"

cp "$CIOS_DASHBOARD_OUT" "$STAGE/index.html"
cp "$CIOS_DASHBOARD_OUT" "$STAGE/v2/index.html"
cp "$OUT/brief.html" "$STAGE/brief.html"
cp "$OUT/brief.html" "$STAGE/v2/brief.html"
cp "$OUT/argus-dashboard.json" "$STAGE/data/semantic-dashboard.json"
cp "$OUT/argus-dashboard.json" "$STAGE/v2/data/semantic-dashboard.json"
cp "$OUT/argus-data-plane-manifest.json" "$STAGE/data/argus-data-plane-manifest.json"
cp "$OUT/argus-data-plane-manifest.json" "$STAGE/v2/data/argus-data-plane-manifest.json"
if [ -s "$OUT/argus-public-run-status.json" ]; then
  cp "$OUT/argus-public-run-status.json" "$STAGE/data/argus-latest-run-status.json"
  cp "$OUT/argus-public-run-status.json" "$STAGE/v2/data/argus-latest-run-status.json"
fi
if [ -s "$OUT/argus-demand-plan-template.csv" ]; then
  cp "$OUT/argus-demand-plan-template.csv" "$STAGE/data/argus-demand-plan-template.csv"
  cp "$OUT/argus-demand-plan-template.csv" "$STAGE/v2/data/argus-demand-plan-template.csv"
fi
if [ -s "$OUT/argus-demand-work-order-guide.json" ]; then
  cp "$OUT/argus-demand-work-order-guide.json" "$STAGE/data/argus-demand-work-order-guide.json"
  cp "$OUT/argus-demand-work-order-guide.json" "$STAGE/v2/data/argus-demand-work-order-guide.json"
fi
cp -R "$OUT/briefs" "$STAGE/briefs"
cp -R "$OUT/briefs" "$STAGE/v2/briefs"

mkdir -p "$PUB/data" "$PUB/v2/data"
cp "$STAGE/index.html" "$PUB/index.html"
cp "$STAGE/v2/index.html" "$PUB/v2/index.html"
cp "$STAGE/brief.html" "$PUB/brief.html"
cp "$STAGE/v2/brief.html" "$PUB/v2/brief.html"
cp "$STAGE/data/semantic-dashboard.json" "$PUB/data/semantic-dashboard.json"
cp "$STAGE/v2/data/semantic-dashboard.json" "$PUB/v2/data/semantic-dashboard.json"
cp "$STAGE/data/argus-data-plane-manifest.json" "$PUB/data/argus-data-plane-manifest.json"
cp "$STAGE/v2/data/argus-data-plane-manifest.json" "$PUB/v2/data/argus-data-plane-manifest.json"
if [ -s "$STAGE/data/argus-latest-run-status.json" ]; then
  cp "$STAGE/data/argus-latest-run-status.json" "$PUB/data/argus-latest-run-status.json"
  cp "$STAGE/v2/data/argus-latest-run-status.json" "$PUB/v2/data/argus-latest-run-status.json"
fi
if [ -s "$STAGE/data/argus-demand-plan-template.csv" ]; then
  cp "$STAGE/data/argus-demand-plan-template.csv" "$PUB/data/argus-demand-plan-template.csv"
  cp "$STAGE/v2/data/argus-demand-plan-template.csv" "$PUB/v2/data/argus-demand-plan-template.csv"
fi
if [ -s "$STAGE/data/argus-demand-work-order-guide.json" ]; then
  cp "$STAGE/data/argus-demand-work-order-guide.json" "$PUB/data/argus-demand-work-order-guide.json"
  cp "$STAGE/v2/data/argus-demand-work-order-guide.json" "$PUB/v2/data/argus-demand-work-order-guide.json"
fi
rm -rf "$PUB/briefs" "$PUB/v2/briefs"
cp -R "$STAGE/briefs" "$PUB/briefs"
cp -R "$STAGE/v2/briefs" "$PUB/v2/briefs"

echo "dashboard published to ci.chowmes.com from $APP"
