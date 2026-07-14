#!/bin/sh
# Hermes cron entrypoint. Only the cios account may cross into app execution.
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

current_user="$(/usr/bin/id -un 2>/dev/null || printf unknown)"
if [ "$current_user" = "cios" ]; then
  exec "$APP/deploy/cios-daily-app.sh"
fi

queue_dir="${CIOS_RUNNER_QUEUE_DIR:-/opt/cios/app/run-queue}"
wait_seconds="${CIOS_RUNNER_WAIT_SECONDS:-1800}"
queue_python="${CIOS_PYTHON_BIN:-$APP/.venv/bin/python}"
queue_helper="${CIOS_RUN_QUEUE_HELPER:-$APP/scripts/cios_run_queue.py}"
case "$wait_seconds" in
  ''|*[!0-9]*)
    echo "invalid CIOS_RUNNER_WAIT_SECONDS: $wait_seconds" >&2
    exit 2
    ;;
esac
if [ ! -d "$queue_dir" ] || [ -L "$queue_dir" ]; then
  echo "CI-OS runner queue is unavailable" >&2
  exit 2
fi
queue_python_path="$(command -v "$queue_python" 2>/dev/null || true)"
if [ -z "$queue_python_path" ] || [ ! -f "$queue_helper" ] || [ -L "$queue_helper" ]; then
  echo "CI-OS secure queue helper is unavailable" >&2
  exit 2
fi
request_id="$("$queue_python_path" "$queue_helper" enqueue \
  --queue "$queue_dir" \
  --requested-by "$current_user" \
  --app-user cios \
  --app "$APP" \
  --public "$PUB")"
echo "queued CI-OS runner handoff request: $request_id" >&2

elapsed=0
while :; do
  set +e
  code="$("$queue_python_path" "$queue_helper" read-result --queue "$queue_dir" --request-id "$request_id")"
  result_status=$?
  set -e
  if [ "$result_status" -eq 0 ]; then
    exit "$code"
  fi
  if [ "$result_status" -ne 3 ]; then
    echo "invalid CI-OS runner result for request: $request_id" >&2
    exit 2
  fi
  if [ "$elapsed" -ge "$wait_seconds" ]; then
    echo "CI-OS runner handoff timed out after ${wait_seconds}s: $request_id" >&2
    exit 124
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
