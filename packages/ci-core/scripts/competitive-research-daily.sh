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
mkdir -p "${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw"

argus_fault() {
  title="$1"
  detail="$2"
  log_path="$3"
  cat <<EOF
Argus did not publish the daily brief.

What broke
$title

Why it matters
$detail

Next move
I saved the machine-room output here:
$log_path

No poetry from a broken pipe. Fix the pipe, then let me talk.
EOF
}

preflight_log="${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/daily-provider-preflight-latest.log"
if ! "$PYTHON_BIN" "$SKILL_ROOT/scripts/ci-provider-preflight.py" >"$preflight_log" 2>&1; then
  argus_fault \
    "Provider preflight failed." \
    "Collection may still be possible, but synthesis is not trustworthy until the model/provider path is healthy." \
    "$preflight_log"
  exit 1
fi

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
  publish_args=(
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT"
    --repo-root "$repo_root"
    --commit-message "Update daily CI dashboard"
  )
  if [ "${DASHBOARD_GIT_PUBLISH:-0}" != "1" ]; then
    publish_args+=(--no-git)
  fi
  if ! "$PYTHON_BIN" "$publisher" \
    "${publish_args[@]}" >"$log_path" 2>&1
  then
    printf 'Argus note: dashboard publish failed. The brief exists, but the dashboard may be stale. Inspect %s\n' "$log_path"
  fi
}

run_self_check() {
  markdown_path="$1"
  html_path="$2"
  run_output_file="$3"
  self_check="$SKILL_ROOT/scripts/ci_run_self_check.py"
  if [ ! -f "$self_check" ]; then
    printf 'Argus note: CI self-check script is missing. The brief exists, but quality verification did not run. Inspect %s\n' "$self_check"
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
    printf '%s\n' "$self_check_output" >"${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/daily-self-check-latest.log"
    printf 'Argus note: daily self-check failed. Treat this brief as unverified until run-audits are inspected.\n'
    return 0
  }
  printf '%s\n' "$self_check_output" >"${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/daily-self-check-latest.log"
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
    printf 'Argus note: run-review script is missing. I could not record the learning loop for this run.\n'
    return 0
  fi
  if [ -z "$audit_json" ]; then
    printf 'Argus note: run review skipped because the self-check audit path was missing.\n'
    return 0
  fi
  if ! "$PYTHON_BIN" "$review" \
    --cadence daily \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --audit-json "$audit_json" \
    --run-output-file "$run_output_file" >"${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/daily-review-latest.log" 2>&1
  then
    printf 'Argus note: daily run review failed. Inspect run-reviews before trusting my learning state.\n'
  fi
}

record_delivery() {
  markdown_path="$1"
  html_path="$2"
  "$PYTHON_BIN" - "$SKILL_ROOT" "$markdown_path" "$html_path" <<'PY' || {
    printf 'Argus note: delivery observability write failed. The Telegram handoff continues, but bot_deliveries is stale.\n'
    return 0
  }
import os
import sys
from pathlib import Path

skill_root, markdown_path, html_path = sys.argv[1:4]
sys.path.insert(0, str(Path(skill_root) / "scripts"))
from ci_core import connect_db, record_bot_delivery

conn = connect_db()
row = conn.execute(
    "select id from report_index where cadence = ? and markdown_path = ? order by id desc limit 1",
    ("daily", markdown_path),
).fetchone()
recipient = (
    os.environ.get("ARGUS_TELEGRAM_HOME_CHANNEL")
    or os.environ.get("TELEGRAM_HOME_CHANNEL")
    or os.environ.get("TELEGRAM_ALLOWED_USERS")
    or "argus-telegram"
)
record_bot_delivery(
    conn,
    report_id=int(row["id"]) if row else None,
    cadence="daily",
    bot_profile="argus",
    channel="telegram",
    recipient=recipient,
    status="queued_for_telegram",
    markdown_path=markdown_path,
    html_path=html_path,
    dashboard_url="https://ci.chowmes.com/",
    artifact_paths=[p for p in [markdown_path, html_path] if p],
    delivery_metadata={"source": "argus_cron_stdout", "wrapper": "competitive-research-daily.sh"},
)
PY
}

print_delivery_status() {
  cat <<'EOF'
Argus daily pulse
Generated and reviewed by Argus. Athena supervises quality; she is not the daily operator.

EOF
}

run_output_file="${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/daily-run-latest-output.log"
mkdir -p "$(dirname "$run_output_file")"
if ! output="$(
  "$PYTHON_BIN" "$SKILL_ROOT/scripts/daily-research-run.py" --skip-search --skip-monitors --fail-on-synthesis-error 2>&1
)"; then
  printf '%s\n' "$output" >"$run_output_file"
  argus_fault \
    "Daily CI generation failed." \
    "I am not sending a decorative summary over a failed run. The ledger/report state is not trustworthy until this is repaired." \
    "$run_output_file"
  exit 1
fi

publish_dashboard
printf '%s\n' "$output" >"$run_output_file"
markdown_path="$(
  printf '%s\n' "$output" | sed -n 's/^Markdown saved: //p' | tail -1
)"
html_path="$(
  printf '%s\n' "$output" | sed -n 's/^HTML saved: //p' | tail -1
)"
run_self_check "$markdown_path" "$html_path" "$run_output_file"
record_delivery "$markdown_path" "$html_path"
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
