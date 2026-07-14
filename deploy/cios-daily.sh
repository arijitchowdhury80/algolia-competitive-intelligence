#!/bin/sh
# Hermes cron entrypoint. Only the cios account may cross into app execution.
set -eu

APP=/opt/cios/app
PUB=/opt/cios/public
HOST_CLIENT_ROOT=/opt/cios/app
HERMES_CLIENT_ROOT=/opt/data/apps/cios
WAIT_SECONDS=1800
ENV=/usr/bin/env

current_user="$(/usr/bin/id -un 2>/dev/null || printf unknown)"
if [ "$current_user" = "cios" ]; then
  exec "$APP/deploy/cios-daily-app.sh"
fi

if [ -d "$HOST_CLIENT_ROOT" ] && [ ! -L "$HOST_CLIENT_ROOT" ]; then
  CLIENT_ROOT="$HOST_CLIENT_ROOT"
elif [ -d "$HERMES_CLIENT_ROOT" ] && [ ! -L "$HERMES_CLIENT_ROOT" ]; then
  CLIENT_ROOT="$HERMES_CLIENT_ROOT"
else
  echo "CI-OS runner client is unavailable" >&2
  exit 2
fi

QUEUE="$CLIENT_ROOT/run-queue"
PYTHON="$CLIENT_ROOT/.venv/bin/python"
HELPER="$CLIENT_ROOT/scripts/cios_run_queue.py"

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
