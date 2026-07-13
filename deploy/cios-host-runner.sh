#!/bin/sh
# Host-side CI-OS runner. Hermes schedules a request; systemd executes this as
# the dedicated `cios` app user and writes the result back for Hermes cron.
set -eu

APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
QUEUE="${CIOS_RUNNER_QUEUE_DIR:-$APP/run-queue}"

mkdir -p "$QUEUE"
chmod 2775 "$QUEUE" 2>/dev/null || true

found=0
for request in "$QUEUE"/*.request; do
  [ -e "$request" ] || continue
  found=1
  base="${request%.request}"
  running="$base.running"
  log="$base.log"
  result="$base.result"
  if ! mv "$request" "$running" 2>/dev/null; then
    continue
  fi

  set +e
  CIOS_DISABLE_RUNNER_HANDOFF=1 \
    CIOS_APP_DIR="$APP" \
    CIOS_PUBLIC_DIR="$PUB" \
    "$APP/deploy/cios-daily.sh" > "$log" 2>&1
  code=$?
  set -e

  printf '%s\n' "$code" > "$result.tmp"
  mv "$result.tmp" "$result"
  mv "$running" "$base.done" 2>/dev/null || true
done

if [ "$found" -eq 0 ]; then
  echo "no CI-OS runner requests found"
fi

exit 0
