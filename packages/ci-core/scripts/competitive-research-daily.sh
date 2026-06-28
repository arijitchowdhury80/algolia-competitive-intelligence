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

if [ -f /root/.hermes/.env ]; then
  set -a
  # shellcheck disable=SC1091
  source /root/.hermes/.env
  set +a
fi

cd "$SKILL_ROOT"
export COMPETITIVE_RESEARCH_OUTPUT_ROOT="$WORKSPACE_ROOT/artifacts/competitive-research"

output="$(
  python3 "$SKILL_ROOT/scripts/daily-research-run.py" --skip-search --skip-monitors 2>&1
)" || {
  printf '%s\n' "$output"
  exit 1
}

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
