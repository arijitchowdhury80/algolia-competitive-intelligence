#!/bin/sh
# Finalize an interrupted CI-OS systemd run after its cgroup has been stopped.
set -eu

APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
QUEUE="${CIOS_RUNNER_QUEUE_DIR:-$APP/run-queue}"
service_result="${SERVICE_RESULT:-unknown}"
PYTHON="${CIOS_PYTHON_BIN:-$APP/.venv/bin/python}"
HELPER="${CIOS_RUN_QUEUE_HELPER:-$APP/scripts/cios_run_queue.py}"

exec "$PYTHON" "$HELPER" finalize \
  --queue "$QUEUE" \
  --public "$PUB" \
  --service-result "$service_result"
