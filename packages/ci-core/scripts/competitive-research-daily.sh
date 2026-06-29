#!/usr/bin/env bash
set -euo pipefail

WORKSPACE_ROOT="${COMPETITIVE_RESEARCH_WORKSPACE_ROOT:-}"
if [ -z "$WORKSPACE_ROOT" ]; then
  for candidate in \
    "/root/.hermes/knowledge/obsidian/MyOS/Projects/Competitive Intelligence" \
    "/opt/data/knowledge/obsidian/MyOS/Projects/Competitive Intelligence"
  do
    if [ -d "$candidate" ]; then
      WORKSPACE_ROOT="$candidate"
      break
    fi
  done
fi
if [ -z "$WORKSPACE_ROOT" ]; then
  printf 'Competitive Intelligence workspace root not found.\n' >&2
  exit 2
fi
SKILL_ROOT="$WORKSPACE_ROOT/skills/competitive-research"

for env_file in /opt/data/.env /root/.hermes/.env; do
  if [ -f "$env_file" ]; then
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi
done

cd "$SKILL_ROOT"
export COMPETITIVE_RESEARCH_OUTPUT_ROOT="$WORKSPACE_ROOT/artifacts/competitive-research"
python3 "$SKILL_ROOT/scripts/ci-provider-preflight.py"

publish_dashboard() {
  repo_root="${ALGOLIA_CI_REPO_ROOT:-/opt/data/apps/algolia-competitive-intelligence}"
  if [ -z "$repo_root" ]; then
    return 0
  fi
  publisher="$repo_root/packages/ci-core/scripts/publish-dashboard.py"
  if [ ! -f "$publisher" ]; then
    printf '[WARN] Dashboard publisher not found: %s\n' "$publisher"
    return 0
  fi
  log_path="${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/dashboard-publish-latest.log"
  mkdir -p "$(dirname "$log_path")"
  if ! python3 "$publisher" \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --repo-root "$repo_root" \
    --commit-message "Update daily CI dashboard" >"$log_path" 2>&1
  then
    printf '[WARN] Dashboard publish failed. Log: %s\n' "$log_path"
  fi
}

output="$(
  python3 "$SKILL_ROOT/scripts/daily-research-run.py" --skip-search --skip-monitors --fail-on-synthesis-error 2>&1
)" || {
  printf '%s\n' "$output"
  exit 1
}

publish_dashboard

pulse="$(
  printf '%s\n' "$output" | awk '
    /^={60}$/ {
      inside = !inside
      next
    }
    inside { print }
  '
)"

if [ -n "$pulse" ]; then
  printf '%s\n' "$pulse"
else
  printf '%s\n' "$output"
fi
