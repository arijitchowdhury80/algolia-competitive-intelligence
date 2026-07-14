"""Behavior tests for the Hermes cron wrapper that publishes CI-OS artifacts."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / "deploy" / "cios-daily.sh"


def _write_executable(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    path.chmod(0o755)


def _make_fake_app(tmp_path: Path, python_body: str) -> tuple[Path, Path, Path]:
    app = tmp_path / "app"
    public = tmp_path / "public"
    env_file = tmp_path / "cios-env"
    (app / "scripts").mkdir(parents=True)
    public.mkdir(parents=True)
    env_file.write_text("CIOS_DATABASE_URL=postgresql://example\n", encoding="utf-8")
    _write_executable(app / ".venv" / "bin" / "python", python_body)
    return app, public, env_file


def _run_wrapper(
    app: Path,
    public: Path,
    env_file: Path,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "CIOS_APP_DIR": str(app),
            "CIOS_PUBLIC_DIR": str(public),
            "CIOS_ENV_FILE": str(env_file),
        }
    )
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        ["sh", str(WRAPPER)],
        cwd=str(ROOT),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_hermes_wrapper_hands_off_to_app_user_runner_when_enabled(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
echo "daily body should not run before app-user handoff" >&2
exit 99
""",
    )
    queue = app / "run-queue"
    watcher = subprocess.Popen(
        [
            "sh",
            "-c",
            (
                "set -eu; "
                f"queue={queue}; "
                "while :; do "
                'for request in "$queue"/*.request; do '
                '[ -e "$request" ] || continue; '
                'base="${request%.request}"; '
                'printf "runner log\\n" > "$base.log"; '
                'printf "17\\n" > "$base.result"; '
                "exit 0; "
                "done; "
                "sleep 1; "
                "done"
            ),
        ],
        text=True,
    )
    try:
        result = _run_wrapper(
            app,
            public,
            env_file,
            {
                "CIOS_RUNNER_HANDOFF": "1",
                "CIOS_RUNNER_QUEUE_DIR": str(queue),
                "CIOS_RUNNER_WAIT_SECONDS": "8",
            },
        )
    finally:
        watcher.terminate()
        watcher.wait(timeout=5)

    assert result.returncode == 17
    assert result.stdout == "runner log\n"
    assert "queued CI-OS runner handoff request" in result.stderr
    assert "daily body should not run" not in result.stderr
    assert list(queue.glob("*.request"))
    assert list(queue.glob("*.result"))


def test_hermes_wrapper_enables_product_market_spine_by_default_and_publishes_same_run_artifacts(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
printf "%s" "$CIOS_ENABLE_PRODUCT_MARKET_INTELLIGENCE" > "$OUT/product-market-flag.txt"
printf "%s" "$CIOS_SCOUT_BIN" > "$OUT/scout-bin.txt"
printf "%s" "$CIOS_PRODUCT_MARKET_PROVIDER" > "$OUT/product-market-provider.txt"
printf "%s" "$CIOS_PRODUCT_MARKET_EXPORT_MAX_WORKERS" > "$OUT/product-market-workers.txt"
printf "%s" "$CIOS_MAX_SYNTH_COMPETITORS" > "$OUT/max-synth-competitors.txt"
printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
printf "current brief" > "$OUT/brief.html"
printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
printf '{"status":"blocked_missing_demand_source"}' > "$OUT/argus-demand-readiness.json"
printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$OUT/argus-demand-plan-template.csv"
printf '{"status":"ready","topic_count":1}' > "$OUT/argus-demand-work-order-guide.json"
printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$OUT/argus-demand-intake.json"
printf '{"work_item_count":0,"items":[]}' > "$OUT/argus-evidence-work-queue.json"
printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$OUT/argus-product-muscle-work-queue.json"
printf '{"status":"ready_for_operator_review"}' > "$OUT/argus-operator-handoff.json"
printf '{"schema_version":1,"status":"ready_for_operator_review"}' > "$OUT/argus-data-plane-manifest.json"
mkdir -p "$OUT/briefs/algolia"
printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (app / "out" / "product-market-flag.txt").read_text(encoding="utf-8") == "1"
    assert (app / "out" / "scout-bin.txt").read_text(encoding="utf-8") == str(app / "scripts" / "scout_http_shim")
    assert (app / "out" / "product-market-provider.txt").read_text(encoding="utf-8") == "gemini/gemini-2.5-flash"
    assert (app / "out" / "product-market-workers.txt").read_text(encoding="utf-8") == "3"
    assert (app / "out" / "max-synth-competitors.txt").read_text(encoding="utf-8") == "4"
    assert (public / "index.html").read_text(encoding="utf-8") == "current cockpit"
    assert (public / "brief.html").read_text(encoding="utf-8") == "current brief"
    assert (public / "data" / "semantic-dashboard.json").read_text(encoding="utf-8") == '{"schema_version":11}'
    assert (public / "data" / "argus-data-plane-manifest.json").read_text(encoding="utf-8") == (
        '{"schema_version":1,"status":"ready_for_operator_review"}'
    )
    assert (public / "data" / "argus-demand-plan-template.csv").read_text(encoding="utf-8").startswith(
        "Page title,Page path,Engaged sessions"
    )
    assert (public / "data" / "argus-demand-work-order-guide.json").read_text(encoding="utf-8") == (
        '{"status":"ready","topic_count":1}'
    )
    assert (public / "briefs" / "algolia" / "constructor.html").read_text(encoding="utf-8") == "constructor brief"
    assert (public / "v2" / "index.html").read_text(encoding="utf-8") == "current cockpit"
    assert (public / "v2" / "data" / "semantic-dashboard.json").read_text(encoding="utf-8") == '{"schema_version":11}'
    assert (public / "v2" / "data" / "argus-data-plane-manifest.json").read_text(encoding="utf-8") == (
        '{"schema_version":1,"status":"ready_for_operator_review"}'
    )
    assert (public / "v2" / "data" / "argus-demand-plan-template.csv").exists()
    assert (public / "v2" / "data" / "argus-demand-work-order-guide.json").exists()


def test_hermes_wrapper_exposes_package_src_on_pythonpath(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
case ":${PYTHONPATH:-}:" in
  *":$PWD/src:"*) ;;
  *) echo "missing app src on PYTHONPATH: ${PYTHONPATH:-}" >&2; exit 42 ;;
esac
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
printf "current brief" > "$OUT/brief.html"
printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
printf '{"status":"blocked_missing_demand_source"}' > "$OUT/argus-demand-readiness.json"
printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$OUT/argus-demand-plan-template.csv"
printf '{"status":"ready","topic_count":1}' > "$OUT/argus-demand-work-order-guide.json"
printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$OUT/argus-demand-intake.json"
printf '{"work_item_count":0,"items":[]}' > "$OUT/argus-evidence-work-queue.json"
printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$OUT/argus-product-muscle-work-queue.json"
printf '{"status":"ready_for_operator_review"}' > "$OUT/argus-operator-handoff.json"
printf '{"schema_version":1,"status":"ready_for_operator_review"}' > "$OUT/argus-data-plane-manifest.json"
mkdir -p "$OUT/briefs/algolia"
printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 0, result.stderr + result.stdout


def test_hermes_wrapper_refuses_to_publish_stale_output_when_runner_writes_nothing(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
exit 0
""",
    )
    stale_out = app / "out"
    stale_out.mkdir(parents=True)
    (stale_out / ".cios-output-dir").write_text("managed by CI-OS\n", encoding="utf-8")
    (stale_out / "argus-dashboard.html").write_text("stale cockpit", encoding="utf-8")
    (stale_out / "brief.html").write_text("stale brief", encoding="utf-8")
    (stale_out / "argus-dashboard.json").write_text('{"stale":true}', encoding="utf-8")

    result = _run_wrapper(app, public, env_file)

    assert result.returncode != 0
    assert "missing dashboard artifact from current run" in result.stderr
    assert not (public / "index.html").exists()
    assert not (public / "brief.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()


def test_hermes_wrapper_refuses_unmarked_existing_output_dir(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
exit 0
""",
    )
    stale_out = app / "out"
    stale_out.mkdir(parents=True)
    (stale_out / "argus-dashboard.html").write_text("stale cockpit", encoding="utf-8")

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 2
    assert "refusing to clean unmarked CIOS output directory" in result.stderr
    assert (stale_out / "argus-dashboard.html").exists()


@pytest.mark.parametrize(
    ("daily_exit_code", "expected_wrapper_code"),
    [(2, 2), (3, 0)],
)
def test_hermes_wrapper_writes_demand_source_gate_when_daily_blocks_publish(
    tmp_path,
    daily_exit_code,
    expected_wrapper_code,
):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
CALLS="$OUT/calls.txt"
case "$1" in
  *verify_hermes_package_contract.py|*audit_learning_policies.py|*apply_product_market_schema.py)
    ;;
  *daily_production_run.py)
    echo "daily" >> "$CALLS"
    printf "blocked cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "blocked brief" > "$OUT/brief.html"
    printf '{"schema_version":17,"product_market_run":{"demand_plane_status":"missing"}}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    echo "ABORT: dashboard publish blocked for algolia" >&2
    exit DAILY_EXIT_CODE
    ;;
  *check_argus_demand_source_gate.py)
    echo "demand-source-gate" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"fail","exit_code":2,"readiness_status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *export_argus_demand_readiness.py)
    echo "demand-readiness" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    echo "demand-plan-template" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1";; --guide-output) shift; printf '{"status":"ready","topic_count":1}' > "$1";; esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    echo "demand-intake" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *execute_product_muscle_gap_discovery.py)
    echo "gap-discovery" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed","candidate_url_count":8,"heuristic_candidate_url_count":8,"stored_candidate_count":2}' > "$1";; esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    echo "candidate-promotion" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed","promoted_count":2}' > "$1";; esac
      shift
    done
    ;;
  *attach_post_run_summaries.py)
    echo "post-run-attach" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --gap-summary) shift; printf "%s" "$1" > "$OUT/blocked-attach-gap-summary-arg.txt";;
        --candidate-promotion-summary) shift; printf "%s" "$1" > "$OUT/blocked-attach-promotion-summary-arg.txt";;
        --demand-readiness) shift; printf "%s" "$1" > "$OUT/blocked-attach-demand-readiness-arg.txt";;
      esac
      shift
    done
    ;;
  *rerender_dashboard.py)
    echo "rerender" >> "$CALLS"
    ;;
  *export_argus_evidence_work_queue.py)
    echo "evidence-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":1,"blocking_count":1,"items":[{"work_item_id":"argus-evidence:37:demand","evidence_plane":"demand","severity":"blocks_action"}]}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    echo "product-muscle-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    echo "operator-handoff" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_on_evidence"}' > "$1";; esac
      shift
    done
    ;;
  *attach_operator_handoff_to_dashboard.py)
    echo "dashboard-handoff-attach" >> "$CALLS"
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"schema_version":1,"status":"blocked_on_evidence"}' > "$1";; esac
      shift
    done
    ;;
  *export_public_run_status.py)
    echo "public-run-status" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"schema_version":1,"publish_status":"blocked","status":"blocked_on_evidence","public_dashboard_updated":false}' > "$1";; esac
      shift
    done
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 97
    ;;
esac
""".replace("DAILY_EXIT_CODE", str(daily_exit_code)),
    )
    (app / "scripts" / "export_public_run_status.py").write_text("", encoding="utf-8")

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == expected_wrapper_code
    if daily_exit_code == 3:
        assert "runtime completed with blocked evidence readiness" in result.stderr
    assert (app / "out" / "calls.txt").read_text(encoding="utf-8").splitlines() == [
        "daily",
        "demand-source-gate",
        "gap-discovery",
        "candidate-promotion",
        "demand-readiness",
        "demand-plan-template",
        "demand-intake",
        "post-run-attach",
        "rerender",
        "evidence-work-queue",
        "product-muscle-work-queue",
        "operator-handoff",
        "dashboard-handoff-attach",
        "data-plane-manifest",
        "public-run-status",
    ]
    assert (app / "out" / "argus-demand-source-gate.json").read_text(encoding="utf-8") == (
        '{"status":"fail","exit_code":2,"readiness_status":"blocked_missing_demand_source"}'
    )
    assert (app / "out" / "product-muscle-gap-discovery-summary.json").read_text(encoding="utf-8") == (
        '{"status":"completed","candidate_url_count":8,"heuristic_candidate_url_count":8,"stored_candidate_count":2}'
    )
    assert (app / "out" / "product-surface-candidate-promotion-summary.json").read_text(encoding="utf-8") == (
        '{"status":"completed","promoted_count":2}'
    )
    assert (app / "out" / "blocked-attach-gap-summary-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "product-muscle-gap-discovery-summary.json"
    )
    assert (app / "out" / "blocked-attach-promotion-summary-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "product-surface-candidate-promotion-summary.json"
    )
    assert (app / "out" / "blocked-attach-demand-readiness-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "argus-demand-readiness.json").exists()
    assert (app / "out" / "argus-evidence-work-queue.json").exists()
    assert (app / "out" / "argus-product-muscle-work-queue.json").exists()
    assert (app / "out" / "argus-operator-handoff.json").exists()
    assert (app / "out" / "argus-data-plane-manifest.json").exists()
    assert (app / "out" / "argus-public-run-status.json").exists()
    assert not (public / "index.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()
    assert (public / "data" / "argus-latest-run-status.json").read_text(encoding="utf-8") == (
        '{"schema_version":1,"publish_status":"blocked","status":"blocked_on_evidence","public_dashboard_updated":false}'
    )
    assert (public / "v2" / "data" / "argus-latest-run-status.json").read_text(encoding="utf-8") == (
        '{"schema_version":1,"publish_status":"blocked","status":"blocked_on_evidence","public_dashboard_updated":false}'
    )
    assert (public / "data" / "argus-demand-plan-template.csv").read_text(encoding="utf-8").startswith(
        "Page title,Page path,Engaged sessions"
    )
    assert (public / "v2" / "data" / "argus-demand-plan-template.csv").exists()


def test_hermes_wrapper_runs_preflight_before_daily_runner(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
case "$1" in
  *verify_hermes_package_contract.py)
    echo "missing required Scout binary: scout" >&2
    exit 2
    ;;
  *)
    echo "daily runner should not execute after preflight failure" >&2
    exit 99
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 2
    assert "missing required Scout binary: scout" in result.stderr
    assert "daily runner should not execute" not in result.stderr
    assert not (public / "index.html").exists()


def test_hermes_wrapper_runs_learning_policy_audit_before_schema_and_daily_runner(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
CALLS="$OUT/calls.txt"
case "$1" in
  *verify_hermes_package_contract.py)
    echo "preflight" >> "$CALLS"
    ;;
  *audit_learning_policies.py)
    echo "policy-audit" >> "$CALLS"
    echo "learning policy drift detected" >&2
    exit 2
    ;;
  *apply_product_market_schema.py)
    echo "schema should not execute after policy audit failure" >&2
    exit 99
    ;;
  *daily_production_run.py)
    echo "daily should not execute after policy audit failure" >&2
    exit 98
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 97
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 2
    assert "learning policy drift detected" in result.stderr
    assert "schema should not execute" not in result.stderr
    assert "daily should not execute" not in result.stderr
    assert (app / "out" / "calls.txt").read_text(encoding="utf-8").splitlines() == [
        "preflight",
        "policy-audit",
    ]
    assert not (public / "index.html").exists()


def test_hermes_wrapper_applies_product_market_schema_before_daily_runner(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
CALLS="$OUT/calls.txt"
case "$1" in
  *verify_hermes_package_contract.py)
    echo "preflight" >> "$CALLS"
    ;;
  *audit_learning_policies.py)
    echo "policy-audit" >> "$CALLS"
    ;;
  *apply_product_market_schema.py)
    echo "schema" >> "$CALLS"
    ;;
  *daily_production_run.py)
    echo "daily" >> "$CALLS"
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    echo "gap-discovery" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"completed","candidate_url_count":0}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    echo "candidate-promotion" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"completed","promoted_count":0}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    echo "demand-readiness" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"blocked_missing_demand_source"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    echo "demand-plan-template" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1"
          ;;
        --guide-output)
          shift
          printf '{"status":"ready","topic_count":1}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    echo "demand-intake" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1"
          ;;
      esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py)
    echo "post-run-attach" >> "$CALLS"
    ;;
  *rerender_dashboard.py)
    echo "rerender" >> "$CALLS"
    ;;
  *export_argus_evidence_work_queue.py)
    echo "evidence-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"work_item_count":0,"items":[]}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    echo "product-muscle-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    echo "operator-handoff" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"ready_for_operator_review"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *attach_operator_handoff_to_dashboard.py)
    echo "dashboard-handoff-attach" >> "$CALLS"
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"ready_for_operator_review"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (app / "out" / "calls.txt").read_text(encoding="utf-8").splitlines() == [
        "preflight",
        "policy-audit",
        "schema",
        "daily",
        "gap-discovery",
        "candidate-promotion",
        "demand-readiness",
        "demand-plan-template",
        "demand-intake",
        "post-run-attach",
        "rerender",
        "evidence-work-queue",
        "product-muscle-work-queue",
        "operator-handoff",
        "dashboard-handoff-attach",
        "data-plane-manifest",
    ]


def test_hermes_wrapper_executes_product_muscle_gap_discovery_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
CALLS="$OUT/calls.txt"
case "$1" in
  *verify_hermes_package_contract.py)
    echo "preflight" >> "$CALLS"
    ;;
  *audit_learning_policies.py)
    echo "policy-audit" >> "$CALLS"
    ;;
  *apply_product_market_schema.py)
    echo "schema" >> "$CALLS"
    ;;
  *daily_production_run.py)
    echo "daily" >> "$CALLS"
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11,"product_market_run":{"product_muscle_gap_plan":{"feature_unknown_collection_targets":[]}}}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    echo "gap-discovery" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/gap-tenant-arg.txt"
          ;;
        --tenant-id)
          echo "gap discovery should use tenant slug, not tenant id" >&2
          exit 97
          ;;
        --gap-plan)
          shift
          printf "%s" "$1" > "$OUT/gap-plan-arg.txt"
          ;;
        --output)
          shift
          printf '{"status":"completed","candidate_url_count":0}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    echo "candidate-promotion" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"completed","promoted_count":0}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    echo "demand-readiness" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/demand-readiness-tenant-arg.txt"
          ;;
        --app-dir)
          shift
          printf "%s" "$1" > "$OUT/demand-readiness-app-dir-arg.txt"
          ;;
        --work-root)
          shift
          printf "%s" "$1" > "$OUT/demand-readiness-work-root-arg.txt"
          ;;
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/demand-readiness-dashboard-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/demand-readiness-output-arg.txt"
          printf '{"status":"blocked_missing_demand_source"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    echo "demand-plan-template" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --readiness)
          shift
          printf "%s" "$1" > "$OUT/demand-plan-readiness-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/demand-plan-output-arg.txt"
          printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1"
          ;;
        --guide-output)
          shift
          printf "%s" "$1" > "$OUT/demand-plan-guide-output-arg.txt"
          printf '{"status":"ready","topic_count":1}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    echo "demand-intake" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-tenant-arg.txt"
          ;;
        --app-dir)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-app-dir-arg.txt"
          ;;
        --work-root)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-work-root-arg.txt"
          ;;
        --out-dir)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-out-dir-arg.txt"
          ;;
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-dashboard-arg.txt"
          ;;
        --python-bin)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-python-bin-arg.txt"
          ;;
        --record-history)
          printf "yes" > "$OUT/demand-intake-record-history-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/demand-intake-output-arg.txt"
          printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1"
          ;;
      esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py)
    echo "post-run-attach" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/attach-dashboard-arg.txt"
          ;;
        --gap-summary)
          shift
          printf "%s" "$1" > "$OUT/attach-gap-summary-arg.txt"
          ;;
        --candidate-promotion-summary)
          shift
          printf "%s" "$1" > "$OUT/attach-promotion-summary-arg.txt"
          ;;
        --demand-readiness)
          shift
          printf "%s" "$1" > "$OUT/attach-demand-readiness-arg.txt"
          ;;
      esac
      shift
    done
    ;;
  *rerender_dashboard.py)
    echo "rerender" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/rerender-tenant-arg.txt"
          ;;
        --out-dir)
          shift
          printf "%s" "$1" > "$OUT/rerender-out-dir-arg.txt"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_evidence_work_queue.py)
    echo "evidence-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/evidence-work-queue-tenant-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/evidence-work-queue-output-arg.txt"
          printf '{"work_item_count":0,"items":[]}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    echo "product-muscle-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/product-muscle-work-queue-tenant-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/product-muscle-work-queue-output-arg.txt"
          printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    echo "operator-handoff" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-tenant-arg.txt"
          ;;
        --work-queue)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-work-queue-arg.txt"
          ;;
        --product-muscle-queue)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-product-muscle-queue-arg.txt"
          ;;
        --demand-readiness)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-demand-readiness-arg.txt"
          ;;
        --demand-plan-template)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-demand-plan-template-arg.txt"
          ;;
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-dashboard-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-output-arg.txt"
          printf '{"status":"ready_for_operator_review"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *attach_operator_handoff_to_dashboard.py)
    echo "dashboard-handoff-attach" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/dashboard-handoff-attach-dashboard-arg.txt"
          ;;
        --handoff)
          shift
          printf "%s" "$1" > "$OUT/dashboard-handoff-attach-handoff-arg.txt"
          ;;
        --html)
          shift
          printf "%s" "$1" > "$OUT/dashboard-handoff-attach-html-arg.txt"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-tenant-arg.txt"
          ;;
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-dashboard-arg.txt"
          ;;
        --demand-readiness)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-demand-readiness-arg.txt"
          ;;
        --demand-plan-template)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-demand-plan-template-arg.txt"
          ;;
        --demand-intake)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-demand-intake-arg.txt"
          ;;
        --evidence-work-queue)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-evidence-work-queue-arg.txt"
          ;;
        --product-muscle-work-queue)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-product-muscle-work-queue-arg.txt"
          ;;
        --operator-handoff)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-operator-handoff-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/data-plane-manifest-output-arg.txt"
          printf '{"schema_version":1,"status":"ready_for_operator_review"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"blocked_on_evidence"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"blocked_on_evidence"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"blocked_on_evidence"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"blocked_on_evidence"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (app / "out" / "calls.txt").read_text(encoding="utf-8").splitlines() == [
        "preflight",
        "policy-audit",
        "schema",
        "daily",
        "gap-discovery",
        "candidate-promotion",
        "demand-readiness",
        "demand-plan-template",
        "demand-intake",
        "post-run-attach",
        "rerender",
        "evidence-work-queue",
        "product-muscle-work-queue",
        "operator-handoff",
        "dashboard-handoff-attach",
        "data-plane-manifest",
    ]
    assert (app / "out" / "gap-plan-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "gap-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "product-muscle-gap-discovery-summary.json").exists()
    assert (app / "out" / "attach-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "attach-gap-summary-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "product-muscle-gap-discovery-summary.json"
    )
    assert (app / "out" / "attach-promotion-summary-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "product-surface-candidate-promotion-summary.json"
    )
    assert (app / "out" / "demand-readiness-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "demand-readiness-app-dir-arg.txt").read_text(encoding="utf-8") == str(app)
    assert (app / "out" / "demand-readiness-work-root-arg.txt").read_text(encoding="utf-8") == (
        str(app / "tmp" / "product-market")
    )
    assert (app / "out" / "demand-readiness-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "demand-readiness-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "demand-plan-readiness-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "demand-plan-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-plan-template.csv"
    )
    assert (app / "out" / "demand-intake-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "demand-intake-app-dir-arg.txt").read_text(encoding="utf-8") == str(app)
    assert (app / "out" / "demand-intake-work-root-arg.txt").read_text(encoding="utf-8") == (
        str(app / "tmp" / "product-market")
    )
    assert (app / "out" / "demand-intake-out-dir-arg.txt").read_text(encoding="utf-8") == str(app / "out")
    assert (app / "out" / "demand-intake-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "demand-intake-python-bin-arg.txt").read_text(encoding="utf-8") == ".venv/bin/python"
    assert (app / "out" / "demand-intake-record-history-arg.txt").read_text(encoding="utf-8") == "yes"
    assert (app / "out" / "demand-intake-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-intake.json"
    )
    assert (app / "out" / "attach-demand-readiness-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "rerender-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "rerender-out-dir-arg.txt").read_text(encoding="utf-8") == str(app / "out")
    assert (app / "out" / "evidence-work-queue-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "evidence-work-queue-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-evidence-work-queue.json"
    )
    assert (app / "out" / "product-muscle-work-queue-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "product-muscle-work-queue-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-product-muscle-work-queue.json"
    )
    assert (app / "out" / "operator-handoff-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "operator-handoff-work-queue-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-evidence-work-queue.json"
    )
    assert (app / "out" / "operator-handoff-product-muscle-queue-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-product-muscle-work-queue.json"
    )
    assert (app / "out" / "operator-handoff-demand-readiness-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "operator-handoff-demand-plan-template-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-plan-template.csv"
    )
    assert (app / "out" / "operator-handoff-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "operator-handoff-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-operator-handoff.json"
    )
    assert (app / "out" / "dashboard-handoff-attach-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "dashboard-handoff-attach-handoff-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-operator-handoff.json"
    )
    assert (app / "out" / "dashboard-handoff-attach-html-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.html"
    )
    assert (app / "out" / "data-plane-manifest-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "data-plane-manifest-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "data-plane-manifest-demand-readiness-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "data-plane-manifest-demand-plan-template-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-plan-template.csv"
    )
    assert (app / "out" / "data-plane-manifest-demand-intake-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-intake.json"
    )
    assert (app / "out" / "data-plane-manifest-evidence-work-queue-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-evidence-work-queue.json"
    )
    assert (app / "out" / "data-plane-manifest-product-muscle-work-queue-arg.txt").read_text(
        encoding="utf-8"
    ) == str(app / "out" / "argus-product-muscle-work-queue.json")
    assert (app / "out" / "data-plane-manifest-operator-handoff-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-operator-handoff.json"
    )
    assert (app / "out" / "data-plane-manifest-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-data-plane-manifest.json"
    )


def test_hermes_wrapper_promotes_validated_product_surface_candidates_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
CALLS="$OUT/calls.txt"
case "$1" in
  *verify_hermes_package_contract.py)
    echo "preflight" >> "$CALLS"
    ;;
  *audit_learning_policies.py)
    echo "policy-audit" >> "$CALLS"
    ;;
  *apply_product_market_schema.py)
    echo "schema" >> "$CALLS"
    ;;
  *daily_production_run.py)
    echo "daily" >> "$CALLS"
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    echo "gap-discovery" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"completed","stored_candidate_count":1}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    echo "candidate-promotion" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/promotion-tenant-arg.txt"
          ;;
        --tenant-id)
          echo "candidate promotion should use tenant slug, not tenant id" >&2
          exit 96
          ;;
        --discovery-source)
          shift
          printf "%s" "$1" > "$OUT/promotion-discovery-source.txt"
          ;;
        --promoted-by)
          shift
          printf "%s" "$1" > "$OUT/promotion-promoted-by.txt"
          ;;
        --output)
          shift
          printf '{"status":"completed","promoted_count":1}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    echo "demand-readiness" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"blocked_missing_demand_source"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    echo "demand-plan-template" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1"
          ;;
        --guide-output)
          shift
          printf '{"status":"ready","topic_count":1}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    echo "demand-intake" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1"
          ;;
      esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py)
    echo "post-run-attach" >> "$CALLS"
    ;;
  *rerender_dashboard.py)
    echo "rerender" >> "$CALLS"
    ;;
  *export_argus_evidence_work_queue.py)
    echo "evidence-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"work_item_count":0,"items":[]}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    echo "product-muscle-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    echo "operator-handoff" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"status":"ready_for_operator_review"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *attach_operator_handoff_to_dashboard.py)
    echo "dashboard-handoff-attach" >> "$CALLS"
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"ready_for_operator_review"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (app / "out" / "calls.txt").read_text(encoding="utf-8").splitlines() == [
        "preflight",
        "policy-audit",
        "schema",
        "daily",
        "gap-discovery",
        "candidate-promotion",
        "demand-readiness",
        "demand-plan-template",
        "demand-intake",
        "post-run-attach",
        "rerender",
        "evidence-work-queue",
        "product-muscle-work-queue",
        "operator-handoff",
        "dashboard-handoff-attach",
        "data-plane-manifest",
    ]
    assert (app / "out" / "promotion-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "promotion-discovery-source.txt").read_text(encoding="utf-8") == "product_muscle_gap_plan"
    assert (app / "out" / "promotion-promoted-by.txt").read_text(encoding="utf-8") == "hermes"
    assert (app / "out" / "product-surface-candidate-promotion-summary.json").exists()


def test_hermes_wrapper_validates_all_required_artifacts_before_touching_public_site(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
mkdir -p "$OUT/briefs/algolia"
printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode != 0
    assert "missing brief artifact from current run" in result.stderr
    assert not (public / "index.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()


def test_hermes_wrapper_requires_evidence_work_queue_artifact_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
case "$1" in
  *verify_hermes_package_contract.py|*audit_learning_policies.py|*apply_product_market_schema.py)
    ;;
  *daily_production_run.py)
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1";; --guide-output) shift; printf '{"status":"ready","topic_count":1}' > "$1";; esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py|*rerender_dashboard.py)
    ;;
  *export_argus_evidence_work_queue.py)
    # Simulate a broken exporter that exits 0 but writes nothing.
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode != 0
    assert "missing evidence work queue artifact from current run" in result.stderr
    assert not (public / "index.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()


def test_hermes_wrapper_requires_product_muscle_work_queue_artifact_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
case "$1" in
  *verify_hermes_package_contract.py|*audit_learning_policies.py|*apply_product_market_schema.py)
    ;;
  *daily_production_run.py)
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1";; --guide-output) shift; printf '{"status":"ready","topic_count":1}' > "$1";; esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py|*rerender_dashboard.py)
    ;;
  *export_argus_evidence_work_queue.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    # Simulate a broken exporter that exits 0 but writes nothing.
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode != 0
    assert "missing product muscle work queue artifact from current run" in result.stderr
    assert not (public / "index.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()


def test_hermes_wrapper_builds_argus_operator_handoff_from_evidence_queue_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
CALLS="$OUT/calls.txt"
case "$1" in
  *verify_hermes_package_contract.py)
    echo "preflight" >> "$CALLS"
    ;;
  *audit_learning_policies.py)
    echo "policy-audit" >> "$CALLS"
    ;;
  *apply_product_market_schema.py)
    echo "schema" >> "$CALLS"
    ;;
  *daily_production_run.py)
    echo "daily" >> "$CALLS"
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    echo "gap-discovery" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    echo "candidate-promotion" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    echo "demand-readiness" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    echo "demand-plan-template" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1";; --guide-output) shift; printf '{"status":"ready","topic_count":1}' > "$1";; esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    echo "demand-intake" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py)
    echo "post-run-attach" >> "$CALLS"
    ;;
  *rerender_dashboard.py)
    echo "rerender" >> "$CALLS"
    ;;
  *export_argus_evidence_work_queue.py)
    echo "evidence-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":1,"blocking_count":1,"items":[{"work_item_id":"argus-evidence:17:demand"}]}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    echo "product-muscle-work-queue" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    echo "operator-handoff" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --tenant)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-tenant-arg.txt"
          ;;
        --work-queue)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-work-queue-arg.txt"
          ;;
        --product-muscle-queue)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-product-muscle-queue-arg.txt"
          ;;
        --demand-readiness)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-demand-readiness-arg.txt"
          ;;
        --demand-plan-template)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-demand-plan-template-arg.txt"
          ;;
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-dashboard-arg.txt"
          ;;
        --output)
          shift
          printf "%s" "$1" > "$OUT/operator-handoff-output-arg.txt"
          printf '{"status":"blocked_on_evidence"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *attach_operator_handoff_to_dashboard.py)
    echo "dashboard-handoff-attach" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --dashboard)
          shift
          printf "%s" "$1" > "$OUT/dashboard-handoff-attach-dashboard-arg.txt"
          ;;
        --handoff)
          shift
          printf "%s" "$1" > "$OUT/dashboard-handoff-attach-handoff-arg.txt"
          ;;
        --html)
          shift
          printf "%s" "$1" > "$OUT/dashboard-handoff-attach-html-arg.txt"
          ;;
      esac
      shift
    done
    ;;
  *export_argus_data_plane_manifest.py)
    echo "data-plane-manifest" >> "$CALLS"
    while [ "$#" -gt 0 ]; do
      case "$1" in
        --output)
          shift
          printf '{"schema_version":1,"status":"blocked_on_evidence"}' > "$1"
          ;;
      esac
      shift
    done
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode == 0, result.stderr + result.stdout
    assert (app / "out" / "calls.txt").read_text(encoding="utf-8").splitlines() == [
        "preflight",
        "policy-audit",
        "schema",
        "daily",
        "gap-discovery",
        "candidate-promotion",
        "demand-readiness",
        "demand-plan-template",
        "demand-intake",
        "post-run-attach",
        "rerender",
        "evidence-work-queue",
        "product-muscle-work-queue",
        "operator-handoff",
        "dashboard-handoff-attach",
        "data-plane-manifest",
    ]
    assert (app / "out" / "operator-handoff-tenant-arg.txt").read_text(encoding="utf-8") == "algolia"
    assert (app / "out" / "operator-handoff-work-queue-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-evidence-work-queue.json"
    )
    assert (app / "out" / "operator-handoff-product-muscle-queue-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-product-muscle-work-queue.json"
    )
    assert (app / "out" / "operator-handoff-demand-readiness-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-readiness.json"
    )
    assert (app / "out" / "operator-handoff-demand-plan-template-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-demand-plan-template.csv"
    )
    assert (app / "out" / "operator-handoff-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "operator-handoff-output-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-operator-handoff.json"
    )
    assert (app / "out" / "dashboard-handoff-attach-dashboard-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.json"
    )
    assert (app / "out" / "dashboard-handoff-attach-handoff-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-operator-handoff.json"
    )
    assert (app / "out" / "dashboard-handoff-attach-html-arg.txt").read_text(encoding="utf-8") == str(
        app / "out" / "argus-dashboard.html"
    )


def test_hermes_wrapper_requires_argus_operator_handoff_artifact_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
case "$1" in
  *verify_hermes_package_contract.py|*audit_learning_policies.py|*apply_product_market_schema.py)
    ;;
  *daily_production_run.py)
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1";; --guide-output) shift; printf '{"status":"ready","topic_count":1}' > "$1";; esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py|*rerender_dashboard.py)
    ;;
  *export_argus_evidence_work_queue.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    # Simulate a broken handoff builder that exits 0 but writes nothing.
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode != 0
    assert "missing Argus operator handoff artifact from current run" in result.stderr
    assert not (public / "index.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()


def test_hermes_wrapper_requires_argus_data_plane_manifest_before_publish(tmp_path):
    app, public, env_file = _make_fake_app(
        tmp_path,
        """#!/bin/sh
set -eu
OUT="$(dirname "$CIOS_DASHBOARD_OUT")"
case "$1" in
  *verify_hermes_package_contract.py|*audit_learning_policies.py|*apply_product_market_schema.py)
    ;;
  *daily_production_run.py)
    printf "current cockpit" > "$CIOS_DASHBOARD_OUT"
    printf "current brief" > "$OUT/brief.html"
    printf '{"schema_version":11}' > "$OUT/argus-dashboard.json"
    mkdir -p "$OUT/briefs/algolia"
    printf "constructor brief" > "$OUT/briefs/algolia/constructor.html"
    ;;
  *execute_product_muscle_gap_discovery.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *promote_product_surface_candidates.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"completed"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_readiness.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source"}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_demand_plan_template.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf 'Page title,Page path,Engaged sessions,Engaged sessions previous period,Period start,Period end,Looker Studio URL,Argus topic,Capability key,Assessment,Suggested filters,Related competitors,Why collect,Evidence URLs\n' > "$1";; --guide-output) shift; printf '{"status":"ready","topic_count":1}' > "$1";; esac
      shift
    done
    ;;
  *run_argus_demand_intake.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"blocked_missing_demand_source","exit_code":2}' > "$1";; esac
      shift
    done
    exit 2
    ;;
  *attach_post_run_summaries.py|*rerender_dashboard.py)
    ;;
  *export_argus_evidence_work_queue.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *export_argus_product_muscle_work_queue.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"work_item_count":0,"blocking_count":0,"limiting_count":0,"items":[]}' > "$1";; esac
      shift
    done
    ;;
  *build_argus_operator_handoff.py)
    while [ "$#" -gt 0 ]; do
      case "$1" in --output) shift; printf '{"status":"ready_for_operator_review"}' > "$1";; esac
      shift
    done
    ;;
  *attach_operator_handoff_to_dashboard.py)
    ;;
  *export_argus_data_plane_manifest.py)
    # Simulate a broken manifest exporter that exits 0 but writes nothing.
    ;;
  *)
    echo "unexpected python target: $1" >&2
    exit 98
    ;;
esac
""",
    )

    result = _run_wrapper(app, public, env_file)

    assert result.returncode != 0
    assert "missing Argus data-plane manifest artifact from current run" in result.stderr
    assert not (public / "index.html").exists()
    assert not (public / "data" / "semantic-dashboard.json").exists()
    assert not (public / "data" / "argus-data-plane-manifest.json").exists()
