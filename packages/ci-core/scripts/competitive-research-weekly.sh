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
    --commit-message "Update weekly CI dashboard" >"$log_path" 2>&1
  then
    printf '[WARN] Dashboard publish failed. Log: %s\n' "$log_path"
  fi
}

output="$(
  python3 "$SKILL_ROOT/scripts/weekly-review.py" 2>&1
)" || {
  printf '%s\n' "$output"
  exit 1
}

publish_dashboard

period="$(
  printf '%s\n' "$output" | sed -nE 's/^=== Weekly competitive synthesis v2: (.*) ===$/\1/p' | head -1
)"
markdown_path="$(
  printf '%s\n' "$output" | sed -n 's/^Markdown saved: //p' | tail -1
)"
html_path="$(
  printf '%s\n' "$output" | sed -n 's/^HTML saved: //p' | tail -1
)"
signals="$(
  printf '%s\n' "$output" | sed -n 's/^Signals in window: //p' | tail -1
)"
owners="$(
  printf '%s\n' "$output" | sed -n 's/^Action-owner coverage: //p' | tail -1
)"
categories="$(
  printf '%s\n' "$output" | sed -n 's/^Category coverage: //p' | tail -1
)"

if [ -z "$period" ]; then
  period="latest weekly window"
fi

cat <<EOF
Weekly competitive readout - $period

Bottom line
The structured HTML report is ready. Use it as the decision artifact; this Telegram message is only the delivery wrapper.

Ledger
Signals in window: ${signals:-unknown}
Owner coverage: ${owners:-not generated}
Category coverage: ${categories:-not generated}

Artifacts
Markdown: ${markdown_path:-not generated}
HTML: ${html_path:-not generated}
$(if [ -n "$html_path" ] && [ -f "$html_path" ]; then printf 'MEDIA:%s\n' "$html_path"; fi)
EOF
