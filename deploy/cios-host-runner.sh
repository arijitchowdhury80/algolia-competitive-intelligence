#!/bin/sh
# Host-side CI-OS runner. Hermes schedules a request; systemd executes this as
# the dedicated `cios` app user and writes the result back for Hermes cron.
set -eu

APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
QUEUE="${CIOS_RUNNER_QUEUE_DIR:-$APP/run-queue}"
PYTHON="${CIOS_PYTHON_BIN:-$APP/.venv/bin/python}"
HELPER="${CIOS_RUN_QUEUE_HELPER:-$APP/scripts/cios_run_queue.py}"

exec "$PYTHON" "$HELPER" run-one --queue "$QUEUE" --app "$APP" --public "$PUB"
