#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export COMPETITIVE_RESEARCH_OUTPUT_ROOT="${COMPETITIVE_RESEARCH_OUTPUT_ROOT:-$REPO_ROOT/.local/competitive-research}"

python3 "$REPO_ROOT/packages/ci-core/scripts/daily-research-run.py" --skip-search --skip-monitors "$@"

