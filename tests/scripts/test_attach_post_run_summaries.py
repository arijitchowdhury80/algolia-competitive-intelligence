from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "attach_post_run_summaries.py"


def test_attach_post_run_summaries_updates_dashboard_json_atomically(tmp_path):
    dashboard = tmp_path / "argus-dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "schema_version": 16,
                "product_market_run": {
                    "status": "ran",
                    "product_muscle_gap_plan": {
                        "feature_unknown_collection_targets": [
                            {"company_name": "Coveo", "surface_family": "docs"}
                        ]
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    gap_summary = tmp_path / "product-muscle-gap-discovery-summary.json"
    gap_summary.write_text(
        json.dumps(
            {
                "status": "completed",
                "candidate_url_count": 12,
                "stored_candidate_count": 6,
                "rejected_count": 1,
            }
        ),
        encoding="utf-8",
    )
    promotion_summary = tmp_path / "product-surface-candidate-promotion-summary.json"
    promotion_summary.write_text(
        json.dumps(
            {
                "status": "completed",
                "promoted_count": 2,
                "skipped_count": 4,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dashboard",
            str(dashboard),
            "--gap-summary",
            str(gap_summary),
            "--candidate-promotion-summary",
            str(promotion_summary),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(dashboard.read_text(encoding="utf-8"))
    run = payload["product_market_run"]
    assert run["post_run_product_muscle_gap_discovery"]["stored_candidate_count"] == 6
    assert run["post_run_product_surface_promotion"]["promoted_count"] == 2
    assert run["post_run_next_sweep_status"] == (
        "Hermes queued 6 candidate product surfaces and activated 2 validated sources "
        "for the next sweep."
    )


def test_attach_post_run_summaries_attaches_demand_readiness_sidecar(tmp_path):
    dashboard = tmp_path / "argus-dashboard.json"
    dashboard.write_text(
        json.dumps(
            {
                "schema_version": 20,
                "product_market_run": {
                    "status": "ran",
                    "demand_plane_status": "missing",
                },
            }
        ),
        encoding="utf-8",
    )
    readiness = tmp_path / "argus-demand-readiness.json"
    readiness.write_text(
        json.dumps(
            {
                "tenant_slug": "algolia",
                "status": "blocked_missing_configuration",
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "manual_import": {"template_fields": ["Page title", "Page path"]},
                "ga4_connector": {"enabled": True, "ready": False},
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dashboard",
            str(dashboard),
            "--demand-readiness",
            str(readiness),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    run = json.loads(dashboard.read_text(encoding="utf-8"))["product_market_run"]
    assert run["demand_readiness"]["status"] == "blocked_missing_configuration"
    assert run["demand_readiness"]["next_hermes_action"] == "configure_ga4_or_upload_demand_export"


def test_attach_post_run_summaries_is_honest_when_sidecar_files_are_missing(tmp_path):
    dashboard = tmp_path / "argus-dashboard.json"
    dashboard.write_text(json.dumps({"schema_version": 16}), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--dashboard", str(dashboard)],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    payload = json.loads(dashboard.read_text(encoding="utf-8"))
    run = payload["product_market_run"]
    assert run["post_run_product_muscle_gap_discovery"] == {}
    assert run["post_run_product_surface_promotion"] == {}
    assert run["post_run_next_sweep_status"] == "No post-run product muscle loop summaries were recorded."


def test_attach_post_run_summaries_does_not_claim_queue_when_all_candidates_rejected(tmp_path):
    dashboard = tmp_path / "argus-dashboard.json"
    dashboard.write_text(json.dumps({"schema_version": 17}), encoding="utf-8")
    gap_summary = tmp_path / "product-muscle-gap-discovery-summary.json"
    gap_summary.write_text(
        json.dumps(
            {
                "status": "completed",
                "candidate_url_count": 46,
                "stored_candidate_count": 0,
                "rejected_count": 46,
                "duplicate_source_count": 46,
                "new_candidate_rejected_count": 0,
            }
        ),
        encoding="utf-8",
    )
    promotion_summary = tmp_path / "product-surface-candidate-promotion-summary.json"
    promotion_summary.write_text(
        json.dumps({"status": "completed", "promoted_count": 0}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dashboard",
            str(dashboard),
            "--gap-summary",
            str(gap_summary),
            "--candidate-promotion-summary",
            str(promotion_summary),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    status = json.loads(dashboard.read_text(encoding="utf-8"))["product_market_run"][
        "post_run_next_sweep_status"
    ]
    assert status == (
        "Hermes rechecked 46 already-monitored product surfaces; no new sweepable sources "
        "were added for the next sweep."
    )
    assert "queued" not in status


def test_attach_post_run_summaries_explains_mixed_duplicate_and_rejected_candidates(tmp_path):
    dashboard = tmp_path / "argus-dashboard.json"
    dashboard.write_text(json.dumps({"schema_version": 17}), encoding="utf-8")
    gap_summary = tmp_path / "product-muscle-gap-discovery-summary.json"
    gap_summary.write_text(
        json.dumps(
            {
                "status": "completed",
                "candidate_url_count": 10,
                "stored_candidate_count": 0,
                "rejected_count": 10,
                "duplicate_source_count": 7,
                "new_candidate_rejected_count": 3,
            }
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--dashboard",
            str(dashboard),
            "--gap-summary",
            str(gap_summary),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    status = json.loads(dashboard.read_text(encoding="utf-8"))["product_market_run"][
        "post_run_next_sweep_status"
    ]
    assert status == (
        "Hermes reviewed 10 product-surface checks: 7 were already monitored and "
        "3 were rejected; no new sweepable sources were added."
    )
