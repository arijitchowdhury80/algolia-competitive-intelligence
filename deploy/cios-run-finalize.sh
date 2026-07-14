#!/bin/sh
# Finalize an interrupted CI-OS systemd run after its cgroup has been stopped.
set -eu

APP="${CIOS_APP_DIR:-/opt/cios/app}"
PUB="${CIOS_PUBLIC_DIR:-/opt/cios/public}"
QUEUE="${CIOS_RUNNER_QUEUE_DIR:-$APP/run-queue}"
service_result="${SERVICE_RESULT:-unknown}"
ACTIVE="$QUEUE/.active-run"

if [ -f "$ACTIVE" ]; then
  request_id="$(sed -n '1p' "$ACTIVE")"
  case "$request_id" in
    ''|.*|*[!A-Za-z0-9._-]*)
      rm -f "$ACTIVE"
      exit 2
      ;;
  esac
  base="$QUEUE/$request_id"
  running="$base.running"
  if [ ! -f "$running" ]; then
    rm -f "$ACTIVE"
    exit 0
  fi
  log="$base.log"
  result="$base.result"
  if [ "$service_result" = "timeout" ] || [ "$service_result" = "watchdog" ]; then
    code=124
    message="systemd runtime timeout"
  else
    code=2
    message="systemd stopped CI-OS before normal completion"
  fi
  printf '%s: %s\n' "$(date -u +"%Y-%m-%dT%H:%M:%SZ")" "$message" >> "$log"
  printf '%s\n' "$code" > "$result.tmp"
  mv "$result.tmp" "$result"
  mv "$running" "$base.done"
  rm -f "$ACTIVE"

  if [ "$code" -eq 124 ]; then
    generated_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
    status_tmp="$QUEUE/$request_id.status.tmp"
    {
      printf '{\n'
      printf '  "schema_version": 1,\n'
      printf '  "generated_at": "%s",\n' "$generated_at"
      printf '  "request_id": "%s",\n' "$request_id"
      printf '  "publish_status": "blocked",\n'
      printf '  "status": "blocked_runtime_timeout",\n'
      printf '  "public_dashboard_updated": false\n'
      printf '}\n'
    } > "$status_tmp"
    mkdir -p "$PUB/data" "$PUB/v2/data"
    cp "$status_tmp" "$PUB/data/.argus-latest-run-status.json.tmp"
    mv "$PUB/data/.argus-latest-run-status.json.tmp" "$PUB/data/argus-latest-run-status.json"
    cp "$status_tmp" "$PUB/v2/data/.argus-latest-run-status.json.tmp"
    mv "$PUB/v2/data/.argus-latest-run-status.json.tmp" "$PUB/v2/data/argus-latest-run-status.json"
    rm -f "$status_tmp"
  fi
fi

exit 0
