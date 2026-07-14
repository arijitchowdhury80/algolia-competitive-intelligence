#!/bin/sh
# Hermes cron entrypoint. Only the cios account may cross into app execution.
set -eu

APP=/opt/cios/app
PUB=/opt/cios/public
QUEUE=/opt/cios/app/run-queue
PYTHON=/opt/cios/app/.venv/bin/python
HELPER=/opt/cios/app/scripts/cios_run_queue.py
WAIT_SECONDS=1800
ENV=/usr/bin/env

current_user="$(/usr/bin/id -un 2>/dev/null || printf unknown)"
if [ "$current_user" = "cios" ]; then
  exec "$APP/deploy/cios-daily-app.sh"
fi

if [ ! -d "$QUEUE" ] || [ -L "$QUEUE" ]; then
  echo "CI-OS runner queue is unavailable" >&2
  exit 2
fi
if [ ! -x "$PYTHON" ] || [ ! -f "$HELPER" ] || [ -L "$HELPER" ]; then
  echo "CI-OS secure queue helper is unavailable" >&2
  exit 2
fi
request_id="$("$ENV" -i PATH=/usr/bin:/bin "$PYTHON" "$HELPER" enqueue \
  --queue "$QUEUE" \
  --requested-by "$current_user" \
  --app-user cios \
  --app "$APP" \
  --public "$PUB")"
echo "queued CI-OS runner handoff request: $request_id" >&2

elapsed=0
while :; do
  set +e
  code="$("$ENV" -i PATH=/usr/bin:/bin "$PYTHON" "$HELPER" read-result --queue "$QUEUE" --request-id "$request_id")"
  result_status=$?
  set -e
  if [ "$result_status" -eq 0 ]; then
    exit "$code"
  fi
  if [ "$result_status" -ne 3 ]; then
    echo "invalid CI-OS runner result for request: $request_id" >&2
    exit 2
  fi
  if [ "$elapsed" -ge "$WAIT_SECONDS" ]; then
    echo "CI-OS runner handoff timed out after ${WAIT_SECONDS}s: $request_id" >&2
    exit 124
  fi
  sleep 2
  elapsed=$((elapsed + 2))
done
