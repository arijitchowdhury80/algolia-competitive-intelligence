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
PYTHON_BIN="${PYTHON_BIN:-/opt/hermes/.venv/bin/python}"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi

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
export CI_MODEL_PROVIDER="${CI_MODEL_PROVIDER:-gemini}"
export COMPETITIVE_RESEARCH_PROVIDER="${COMPETITIVE_RESEARCH_PROVIDER:-gemini}"
export COMPETITIVE_RESEARCH_MODEL="${COMPETITIVE_RESEARCH_MODEL:-gemini-2.5-flash}"
"$PYTHON_BIN" "$SKILL_ROOT/scripts/ci-provider-preflight.py"

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
  if ! "$PYTHON_BIN" "$publisher" \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --repo-root "$repo_root" \
    --commit-message "Update daily CI dashboard" >"$log_path" 2>&1
  then
    printf '[WARN] Dashboard publish failed. Log: %s\n' "$log_path"
  fi
}

run_self_check() {
  markdown_path="$1"
  html_path="$2"
  run_output_file="$3"
  self_check="$SKILL_ROOT/scripts/ci_run_self_check.py"
  if [ ! -f "$self_check" ]; then
    printf '[WARN] CI self-check script not found: %s\n' "$self_check"
    return 0
  fi
  self_check_output="$(
    "$PYTHON_BIN" "$self_check" \
    --cadence daily \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --markdown-path "$markdown_path" \
    --html-path "$html_path" \
    --dashboard-log "${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/dashboard-publish-latest.log" \
    --run-output-file "$run_output_file" 2>&1
  )" || {
    printf '%s\n' "$self_check_output"
    printf '[WARN] CI daily self-check failed. Inspect run-audits before trusting delivery.\n'
    return 0
  }
  printf '%s\n' "$self_check_output"
  audit_json="$(
    printf '%s\n' "$self_check_output" | sed -n 's/^Audit JSON: //p' | tail -1
  )"
  run_post_review "$audit_json" "$run_output_file"
}

run_post_review() {
  audit_json="$1"
  run_output_file="$2"
  review="$SKILL_ROOT/scripts/ci_run_review.py"
  if [ ! -f "$review" ]; then
    printf '[WARN] CI run review script not found: %s\n' "$review"
    return 0
  fi
  if [ -z "$audit_json" ]; then
    printf '[WARN] CI daily run review skipped because self-check audit path was missing.\n'
    return 0
  fi
  if ! "$PYTHON_BIN" "$review" \
    --cadence daily \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --audit-json "$audit_json" \
    --run-output-file "$run_output_file"
  then
    printf '[WARN] CI daily run review failed. Inspect run-reviews before trusting Argus learning state.\n'
  fi
}

print_delivery_status() {
  cat <<'EOF'
Delivery status
Operator: Argus generated and reviewed this CI run.
Current delivery path: dedicated Argus Telegram gateway.
Athena role: supervisor only, not daily CI operator.

EOF
}

output="$(
  "$PYTHON_BIN" "$SKILL_ROOT/scripts/daily-research-run.py" --skip-search --skip-monitors --fail-on-synthesis-error 2>&1
)" || {
  printf '%s\n' "$output"
  exit 1
}

publish_dashboard
run_output_file="${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/daily-run-latest-output.log"
mkdir -p "$(dirname "$run_output_file")"
printf '%s\n' "$output" >"$run_output_file"
markdown_path="$(
  printf '%s\n' "$output" | sed -n 's/^Markdown saved: //p' | tail -1
)"
html_path="$(
  printf '%s\n' "$output" | sed -n 's/^HTML saved: //p' | tail -1
)"
run_self_check "$markdown_path" "$html_path" "$run_output_file"
print_delivery_status

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
