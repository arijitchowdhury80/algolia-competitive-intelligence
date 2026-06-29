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
Argus did not publish the weekly synthesis.

What broke
$title

Why it matters
$detail

Next move
I saved the machine-room output here:
$log_path

Strategy built on a failed run is just theatre with charts. Fix this first.
EOF
}

preflight_log="${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/weekly-provider-preflight-latest.log"
if ! "$PYTHON_BIN" "$SKILL_ROOT/scripts/ci-provider-preflight.py" >"$preflight_log" 2>&1; then
  argus_fault \
    "Provider preflight failed." \
    "Weekly synthesis needs a healthy model/provider path. Without that, the archive may exist but the executive interpretation is not trustworthy." \
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
  if ! "$PYTHON_BIN" "$publisher" \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --repo-root "$repo_root" \
    --commit-message "Update weekly CI dashboard" >"$log_path" 2>&1
  then
    printf 'Argus note: dashboard publish failed. The weekly synthesis exists, but the dashboard may be stale. Inspect %s\n' "$log_path"
  fi
}

run_self_check() {
  markdown_path="$1"
  html_path="$2"
  run_output_file="$3"
  self_check="$SKILL_ROOT/scripts/ci_run_self_check.py"
  if [ ! -f "$self_check" ]; then
    printf 'Argus note: CI self-check script is missing. The weekly synthesis exists, but quality verification did not run. Inspect %s\n' "$self_check"
    return 0
  fi
  self_check_output="$(
    "$PYTHON_BIN" "$self_check" \
    --cadence weekly \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --markdown-path "$markdown_path" \
    --html-path "$html_path" \
    --dashboard-log "${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/dashboard-publish-latest.log" \
    --run-output-file "$run_output_file" 2>&1
  )" || {
    printf '%s\n' "$self_check_output" >"${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/weekly-self-check-latest.log"
    printf 'Argus note: weekly self-check failed. Treat this synthesis as unverified until run-audits are inspected.\n'
    return 0
  }
  printf '%s\n' "$self_check_output" >"${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/weekly-self-check-latest.log"
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
    printf 'Argus note: run-review script is missing. I could not record the learning loop for this weekly run.\n'
    return 0
  fi
  if [ -z "$audit_json" ]; then
    printf 'Argus note: run review skipped because the self-check audit path was missing.\n'
    return 0
  fi
  if ! "$PYTHON_BIN" "$review" \
    --cadence weekly \
    --output-root "$COMPETITIVE_RESEARCH_OUTPUT_ROOT" \
    --audit-json "$audit_json" \
    --run-output-file "$run_output_file" >"${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/weekly-review-latest.log" 2>&1
  then
    printf 'Argus note: weekly run review failed. Inspect run-reviews before trusting my learning state.\n'
  fi
}

print_delivery_status() {
  cat <<'EOF'
Argus weekly synthesis
Generated and reviewed by Argus. Athena supervises quality; she is not the weekly operator.

EOF
}

run_output_file="${COMPETITIVE_RESEARCH_OUTPUT_ROOT}/raw/weekly-run-latest-output.log"
mkdir -p "$(dirname "$run_output_file")"
if ! output="$(
  "$PYTHON_BIN" "$SKILL_ROOT/scripts/weekly-review.py" --fail-on-synthesis-error 2>&1
)"; then
  printf '%s\n' "$output" >"$run_output_file"
  argus_fault \
    "Weekly CI generation failed." \
    "I am not sending a ceremonial executive brief over a broken synthesis. The weekly interpretation is not trustworthy until this is repaired." \
    "$run_output_file"
  exit 1
fi

publish_dashboard
printf '%s\n' "$output" >"$run_output_file"

period="$(
  printf '%s\n' "$output" | sed -nE 's/^=== Weekly competitive synthesis v2: (.*) ===$/\1/p' | head -1
)"
markdown_path="$(
  printf '%s\n' "$output" | sed -n 's/^Markdown saved: //p' | tail -1
)"
html_path="$(
  printf '%s\n' "$output" | sed -n 's/^HTML saved: //p' | tail -1
)"
run_self_check "$markdown_path" "$html_path" "$run_output_file"
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

print_delivery_status

cat <<EOF
Weekly competitive readout - $period

Bottom line
The decision artifact is ready. I am keeping Telegram short: this is the handle, not the whole knife.

Signal map
Signals in window: ${signals:-unknown}
Owner coverage: ${owners:-not generated}
Category coverage: ${categories:-not generated}

Recommended use
Open the HTML report, review owner routes, and act only on evidence-backed deltas. If a finding is just noise wearing a blazer, leave it in the archive.

Artifacts
Markdown: ${markdown_path:-not generated}
HTML: ${html_path:-not generated}
$(if [ -n "$html_path" ] && [ -f "$html_path" ]; then printf 'MEDIA:%s\n' "$html_path"; fi)
EOF
