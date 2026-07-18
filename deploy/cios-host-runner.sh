#!/bin/sh
# Host-side CI-OS runner. Hermes schedules a request; systemd executes this as
# the dedicated `cios` app user and writes the result back for Hermes cron.
set -eu

APP=/opt/cios/app
PUB=/opt/cios/public
QUEUE=/opt/cios/app/run-queue
PYTHON=/opt/cios/app/.venv/bin/python
HELPER=/opt/cios/app/scripts/cios_run_queue.py

if [ "$(/usr/bin/id -un)" != "cios" ]; then
  echo "CI-OS host runner must run as cios" >&2
  exit 2
fi

exec "$PYTHON" "$HELPER" run-pending --queue "$QUEUE" --app "$APP" --public "$PUB"
