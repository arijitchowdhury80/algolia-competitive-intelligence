#!/bin/sh
# Finalize an interrupted CI-OS systemd run after its cgroup has been stopped.
set -eu

APP=/opt/cios/app
PUB=/opt/cios/public
QUEUE=/opt/cios/app/run-queue
service_result="${SERVICE_RESULT:-unknown}"
PYTHON=/opt/cios/app/.venv/bin/python
HELPER=/opt/cios/app/scripts/cios_run_queue.py

if [ "$(/usr/bin/id -un)" != "cios" ]; then
  echo "CI-OS run finalizer must run as cios" >&2
  exit 2
fi

exec "$PYTHON" "$HELPER" finalize \
  --queue "$QUEUE" \
  --public "$PUB" \
  --service-result "$service_result"
