#!/bin/sh
# Argus V2 daily pipeline -- Hermes cron.
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

handoff_to_cios_runner_if_requested() {
  case "$(printf '%s' "${CIOS_RUNNER_HANDOFF:-0}" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|on) ;;
    *) return 0 ;;
  esac
  if [ "${CIOS_DISABLE_RUNNER_HANDOFF:-0}" = "1" ]; then
    return 0
  fi

  app_user="${CIOS_APP_USER:-cios}"
  current_user="$(id -un 2>/dev/null || printf unknown)"
  if [ "$current_user" = "$app_user" ]; then
    return 0
  fi

  queue_dir="${CIOS_RUNNER_QUEUE_DIR:-$APP/run-queue}"
  wait_seconds="${CIOS_RUNNER_WAIT_SECONDS:-1200}"
  case "$wait_seconds" in
    ''|*[!0-9]*)
      echo "invalid CIOS_RUNNER_WAIT_SECONDS: $wait_seconds" >&2
      exit 2
      ;;
  esac

  mkdir -p "$queue_dir"
  chmod 2775 "$queue_dir" 2>/dev/null || true
  request_id="$(date -u +"%Y%m%dT%H%M%SZ")-$$"
  request="$queue_dir/$request_id.request"
  result="$queue_dir/$request_id.result"
  log="$queue_dir/$request_id.log"
  {
    printf 'request_id=%s\n' "$request_id"
    printf 'requested_at=%s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    printf 'requested_by=%s\n' "$current_user"
    printf 'app_user=%s\n' "$app_user"
    printf 'app_dir=%s\n' "$APP"
    printf 'public_dir=%s\n' "$PUB"
  } > "$request.tmp"
  mv "$request.tmp" "$request"
  echo "queued CI-OS runner handoff request: $request_id" >&2

  elapsed=0
  while [ ! -f "$result" ]; do
    if [ "$elapsed" -ge "$wait_seconds" ]; then
      echo "CI-OS runner handoff timed out after ${wait_seconds}s: $request_id" >&2
      if [ -f "$log" ]; then
        tail -120 "$log" >&2 || true
      fi
      exit 124
    fi
    sleep 2
    elapsed=$((elapsed + 2))
  done

  if [ -f "$log" ]; then
    cat "$log"
  fi
  code="$(head -n 1 "$result" | tr -cd '0-9' || true)"
  if [ -z "$code" ]; then
    echo "invalid CI-OS runner result for request: $request_id" >&2
    exit 2
  fi
  exit "$code"
}

handoff_to_cios_runner_if_requested

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
export CIOS_CONTROLLED_PILOT_ALLOW_PARTIAL_DEMAND="${CIOS_CONTROLLED_PILOT_ALLOW_PARTIAL_DEMAND:-1}"
export CIOS_PRODUCT_MARKET_PROVIDER="${CIOS_PRODUCT_MARKET_PROVIDER:-gemini/gemini-2.5-flash}"
export CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS="${CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS:-3}"
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
export CIOS_DAILY_RUN_TIMEOUT_SECONDS="${CIOS_DAILY_RUN_TIMEOUT_SECONDS:-1350}"
export CIOS_PLANNED_DEMAND_EXPORT_DATA_DIR="${CIOS_PLANNED_DEMAND_EXPORT_DATA_DIR:-$APP/data}"

case "$CIOS_DAILY_RUN_TIMEOUT_SECONDS" in
  ''|*[!0-9]*)
    echo "invalid CIOS_DAILY_RUN_TIMEOUT_SECONDS: $CIOS_DAILY_RUN_TIMEOUT_SECONDS" >&2
    exit 2
    ;;
esac

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

evaluate_planned_demand_sidecar() {
  DEMAND_PLAN_AMENDMENTS_ARG=""
  if [ ! -d "$CIOS_PLANNED_DEMAND_EXPORT_DATA_DIR" ]; then
    return 0
  fi
  if [ ! -s "$OUT/argus-demand-plan-template.csv" ]; then
    return 0
  fi
  if [ ! -f scripts/evaluate_argus_planned_demand_exports.py ]; then
    return 0
  fi
  set +e
  .venv/bin/python scripts/evaluate_argus_planned_demand_exports.py \
    --plan "$OUT/argus-demand-plan-template.csv" \
    --data-dir "$CIOS_PLANNED_DEMAND_EXPORT_DATA_DIR" \
    --output "$OUT/argus-planned-demand-evaluation.json" \
    --prepared-output "$OUT/argus-planned-demand-prepared.csv" \
    --amendment-output "$OUT/argus-demand-plan-amendment-candidates.csv" \
    --accept-limited-plan-evidence
  PLANNED_DEMAND_EVAL_CODE=$?
  set -e
  if [ -s "$OUT/argus-planned-demand-evaluation.json" ]; then
    DEMAND_PLAN_AMENDMENTS_ARG="--demand-plan-amendments $OUT/argus-planned-demand-evaluation.json"
  fi
  if [ "$PLANNED_DEMAND_EVAL_CODE" -ne 0 ] && [ "$PLANNED_DEMAND_EVAL_CODE" -ne 2 ]; then
    echo "planned demand evaluation exited with $PLANNED_DEMAND_EVAL_CODE; continuing without changing the gate" >&2
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
  if [ -s "$OUT/argus-planned-demand-evaluation.json" ]; then
    cp "$OUT/argus-planned-demand-evaluation.json" "$PUB/data/argus-planned-demand-evaluation.json"
    cp "$OUT/argus-planned-demand-evaluation.json" "$PUB/v2/data/argus-planned-demand-evaluation.json"
  fi
  if [ -s "$OUT/argus-demand-plan-amendment-candidates.csv" ]; then
    cp "$OUT/argus-demand-plan-amendment-candidates.csv" "$PUB/data/argus-demand-plan-amendment-candidates.csv"
    cp "$OUT/argus-demand-plan-amendment-candidates.csv" "$PUB/v2/data/argus-demand-plan-amendment-candidates.csv"
  fi
}

promote_public_store_if_present() {
  public_store="${CIOS_PUBLIC_STORE_DIR:-/opt/cios/public-store}"
  if [ ! -d "$public_store/served" ] || [ ! -d "$public_store/releases" ]; then
    return 0
  fi
  previous_release=""
  if [ -L "$public_store/current" ]; then
    previous_release="$(readlink "$public_store/current" || true)"
  fi
  release_id="cios-$(date -u +"%Y%m%dT%H%M%SZ")-$$"
  release_dir="$public_store/releases/$release_id"
  tmp_dir="$public_store/releases/.${release_id}.tmp"
  served_tmp="$public_store/.served.$release_id.tmp"
  rm -rf "$tmp_dir"
  rm -rf "$served_tmp"
  mkdir -p "$tmp_dir"
  cp -R "$PUB/." "$tmp_dir/"
  cat > "$tmp_dir/publication-manifest.json" <<EOF
{"schema_version":1,"run_id":"$release_id","previous_release":"$previous_release","published_at":"$(date -u +"%Y-%m-%dT%H:%M:%SZ")"}
EOF
  mv "$tmp_dir" "$release_dir"
  if [ -s "$release_dir/data/argus-latest-run-status.json" ]; then
    cp "$release_dir/data/argus-latest-run-status.json" "$public_store/latest-status.json"
  fi
  mkdir -p "$served_tmp"
  cp -R "$release_dir/." "$served_tmp/"
  rm -rf "$public_store/served.previous"
  mv "$public_store/served" "$public_store/served.previous"
  mv "$served_tmp" "$public_store/served"
  rm -f "$public_store/current.next"
  ln -s "releases/$release_id" "$public_store/current.next"
  rm -f "$public_store/current"
  mv "$public_store/current.next" "$public_store/current"
}

kill_process_tree() {
  root_pid="$1"
  if command -v pgrep >/dev/null 2>&1; then
    for child_pid in $(pgrep -P "$root_pid" 2>/dev/null || true); do
      kill_process_tree "$child_pid"
    done
  fi
  kill "$root_pid" 2>/dev/null || true
}

kill_process_tree_force() {
  root_pid="$1"
  if command -v pgrep >/dev/null 2>&1; then
    for child_pid in $(pgrep -P "$root_pid" 2>/dev/null || true); do
      kill_process_tree_force "$child_pid"
    done
  fi
  kill -KILL "$root_pid" 2>/dev/null || true
}

ACTIVE_DAILY_PID=""
ACTIVE_DAILY_PGID=""
ACTIVE_WATCHDOG_PID=""

cleanup_active_daily() {
  if [ -n "$ACTIVE_WATCHDOG_PID" ]; then
    kill_process_tree "$ACTIVE_WATCHDOG_PID"
    wait "$ACTIVE_WATCHDOG_PID" 2>/dev/null || true
    ACTIVE_WATCHDOG_PID=""
  fi
  if [ -n "$ACTIVE_DAILY_PID" ] && kill -0 "$ACTIVE_DAILY_PID" 2>/dev/null; then
    if [ -n "$ACTIVE_DAILY_PGID" ]; then
      kill -TERM "-$ACTIVE_DAILY_PGID" 2>/dev/null || true
    fi
    kill_process_tree "$ACTIVE_DAILY_PID"
    sleep 2
    if kill -0 "$ACTIVE_DAILY_PID" 2>/dev/null; then
      if [ -n "$ACTIVE_DAILY_PGID" ]; then
        kill -KILL "-$ACTIVE_DAILY_PGID" 2>/dev/null || true
      fi
      kill_process_tree_force "$ACTIVE_DAILY_PID"
    fi
  fi
  ACTIVE_DAILY_PID=""
  ACTIVE_DAILY_PGID=""
}

trap 'cleanup_active_daily' EXIT
trap 'cleanup_active_daily; exit 130' INT HUP TERM

run_daily_production_with_timeout() {
  timeout_seconds="$1"
  timeout_flag="$OUT/.daily-production-timeout"
  rm -f "$timeout_flag"
  daily_pgid=""
  if command -v setsid >/dev/null 2>&1; then
    setsid .venv/bin/python scripts/daily_production_run.py &
    daily_pid="$!"
    daily_pgid="$daily_pid"
  else
    .venv/bin/python scripts/daily_production_run.py &
    daily_pid="$!"
  fi
  ACTIVE_DAILY_PID="$daily_pid"
  ACTIVE_DAILY_PGID="$daily_pgid"
  if [ "$timeout_seconds" -gt 0 ]; then
    (
      sleep "$timeout_seconds"
      if kill -0 "$daily_pid" 2>/dev/null; then
        printf "1" > "$timeout_flag"
        if [ -n "$daily_pgid" ]; then
          kill -TERM "-$daily_pgid" 2>/dev/null || true
        fi
        kill_process_tree "$daily_pid"
        sleep 2
        if [ -n "$daily_pgid" ]; then
          kill -KILL "-$daily_pgid" 2>/dev/null || true
        fi
        kill_process_tree_force "$daily_pid"
        if kill -0 "$daily_pid" 2>/dev/null; then
          echo "daily production runner survived timeout kill: pid=$daily_pid" >&2
        fi
      fi
    ) >/dev/null 2>&1 &
    watchdog_pid="$!"
    ACTIVE_WATCHDOG_PID="$watchdog_pid"
  else
    watchdog_pid=""
    ACTIVE_WATCHDOG_PID=""
  fi
  wait "$daily_pid"
  daily_code="$?"
  if [ -n "$watchdog_pid" ]; then
    kill_process_tree "$watchdog_pid"
    wait "$watchdog_pid" 2>/dev/null || true
  fi
  ACTIVE_DAILY_PID=""
  ACTIVE_DAILY_PGID=""
  ACTIVE_WATCHDOG_PID=""
  if [ -f "$timeout_flag" ]; then
    rm -f "$timeout_flag"
    echo "daily production runner timed out after ${timeout_seconds}s" >&2
    return 124
  fi
  return "$daily_code"
}

write_timeout_manifest() {
  generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  {
    printf '{\n'
    printf '  "schema_version": 1,\n'
    printf '  "tenant_slug": "%s",\n' "$CIOS_PRODUCT_MUSCLE_GAP_TENANT"
    printf '  "generated_at": "%s",\n' "$generated_at"
    printf '  "status": "blocked_runtime_timeout",\n'
    printf '  "next_hermes_action": "inspect_daily_run_stage_ledger_and_rerun_after_timeout_fix",\n'
    printf '  "planes": {\n'
    printf '    "runtime": {\n'
    printf '      "status": "timeout",\n'
    printf '      "summary": "Hermes stopped the CI-OS daily runner after it exceeded the configured runtime budget.",\n'
    printf '      "blocks_action": true,\n'
    printf '      "counts": {"timeout_seconds": %s},\n' "$CIOS_DAILY_RUN_TIMEOUT_SECONDS"
    printf '      "next_hermes_action": "inspect_daily_run_stage_ledger_and_rerun_after_timeout_fix"\n'
    printf '    }\n'
    printf '  },\n'
    printf '  "blockers": [\n'
    printf '    {\n'
    printf '      "plane": "runtime",\n'
    printf '      "severity": "blocks_publish",\n'
    printf '      "title": "Daily runner timed out",\n'
    printf '      "next_step": "Inspect the CI-OS stage ledger and logs, fix the hanging stage, then rerun Hermes daily execution."\n'
    printf '    }\n'
    printf '  ]\n'
    printf '}\n'
  } > "$OUT/argus-data-plane-manifest.json"
}

set +e
run_daily_production_with_timeout "$CIOS_DAILY_RUN_TIMEOUT_SECONDS"
DAILY_CODE=$?
set -e
if [ "$DAILY_CODE" -eq 124 ]; then
  write_timeout_manifest
  write_public_run_status blocked
  publish_public_run_status
  exit "$DAILY_CODE"
fi
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

    evaluate_planned_demand_sidecar
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
      $DEMAND_PLAN_AMENDMENTS_ARG \
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

evaluate_planned_demand_sidecar
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
  $DEMAND_PLAN_AMENDMENTS_ARG \
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
if [ -s "$OUT/argus-planned-demand-evaluation.json" ]; then
  cp "$OUT/argus-planned-demand-evaluation.json" "$STAGE/data/argus-planned-demand-evaluation.json"
  cp "$OUT/argus-planned-demand-evaluation.json" "$STAGE/v2/data/argus-planned-demand-evaluation.json"
fi
if [ -s "$OUT/argus-demand-plan-amendment-candidates.csv" ]; then
  cp "$OUT/argus-demand-plan-amendment-candidates.csv" "$STAGE/data/argus-demand-plan-amendment-candidates.csv"
  cp "$OUT/argus-demand-plan-amendment-candidates.csv" "$STAGE/v2/data/argus-demand-plan-amendment-candidates.csv"
fi
cp -R "$OUT/briefs" "$STAGE/briefs"
cp -R "$OUT/briefs" "$STAGE/v2/briefs"

if [ -f scripts/export_argus_recommendation_review_packet.py ] && \
   [ -f scripts/export_pilot_recommendation_work_artifact.py ] && \
   [ -f scripts/build_phase8_disposition_request.py ] && \
   [ -f scripts/publish_pilot_recommendation_work_artifact.py ]; then
  mkdir -p "$OUT/phase8"
  set +e
  .venv/bin/python scripts/export_argus_recommendation_review_packet.py \
    --dashboard "$OUT/argus-dashboard.json" \
    --output "$OUT/phase8/argus-recommendation-review-packet.json" \
    --markdown-output "$OUT/phase8/argus-recommendation-review-packet.md" \
    --reviewed-by "cios-wrapper"
  phase8_review_code=$?
  set -e
  if [ "$phase8_review_code" -eq 0 ]; then
    .venv/bin/python scripts/export_pilot_recommendation_work_artifact.py \
      --review-packet "$OUT/phase8/argus-recommendation-review-packet.json" \
      --output "$OUT/phase8/argus-pmm-narrative-brief.json" \
      --markdown-output "$OUT/phase8/argus-pmm-narrative-brief.md" \
      --generated-by "cios-wrapper"
    .venv/bin/python scripts/build_phase8_disposition_request.py \
      --work-artifact "$OUT/phase8/argus-pmm-narrative-brief.json" \
      --work-artifact-url "https://ci.chowmes.com/data/phase8/argus-pmm-narrative-brief.md" \
      --manifest-url "https://ci.chowmes.com/data/phase8/argus-phase8-work-artifacts.json" \
      --review-packet-path "out/phase8/argus-recommendation-review-packet.json" \
      --output "$OUT/phase8/argus-pmm-disposition-request.json" \
      --markdown-output "$OUT/phase8/argus-pmm-disposition-request.md"
    .venv/bin/python scripts/publish_pilot_recommendation_work_artifact.py \
      --artifact-json "$OUT/phase8/argus-pmm-narrative-brief.json" \
      --artifact-markdown "$OUT/phase8/argus-pmm-narrative-brief.md" \
      --disposition-request-json "$OUT/phase8/argus-pmm-disposition-request.json" \
      --disposition-request-markdown "$OUT/phase8/argus-pmm-disposition-request.md" \
      --public-dir "$STAGE" \
      --base-url "https://ci.chowmes.com" \
      --output "$OUT/phase8/argus-pmm-narrative-brief-publication.json"
  else
    echo "Phase 8 PMM work artifact skipped; no current reviewable recommendation in this run" >&2
  fi
fi

.venv/bin/python scripts/redact_public_artifacts.py \
  --public-dir "$STAGE" \
  --output "$OUT/public-artifact-redaction.json"

.venv/bin/python scripts/scan_public_artifacts.py \
  --public-dir "$STAGE" \
  --output "$OUT/public-artifact-safety-scan.json"

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
if [ -s "$STAGE/data/argus-planned-demand-evaluation.json" ]; then
  cp "$STAGE/data/argus-planned-demand-evaluation.json" "$PUB/data/argus-planned-demand-evaluation.json"
  cp "$STAGE/v2/data/argus-planned-demand-evaluation.json" "$PUB/v2/data/argus-planned-demand-evaluation.json"
fi
if [ -s "$STAGE/data/argus-demand-plan-amendment-candidates.csv" ]; then
  cp "$STAGE/data/argus-demand-plan-amendment-candidates.csv" "$PUB/data/argus-demand-plan-amendment-candidates.csv"
  cp "$STAGE/v2/data/argus-demand-plan-amendment-candidates.csv" "$PUB/v2/data/argus-demand-plan-amendment-candidates.csv"
fi
if [ -d "$STAGE/data/phase8" ]; then
  rm -rf "$PUB/data/phase8" "$PUB/v2/data/phase8"
  cp -R "$STAGE/data/phase8" "$PUB/data/phase8"
  cp -R "$STAGE/v2/data/phase8" "$PUB/v2/data/phase8"
fi
rm -rf "$PUB/briefs" "$PUB/v2/briefs"
cp -R "$STAGE/briefs" "$PUB/briefs"
cp -R "$STAGE/v2/briefs" "$PUB/v2/briefs"
rm -rf "$STAGE"
promote_public_store_if_present

echo "dashboard published to ci.chowmes.com from $APP"
