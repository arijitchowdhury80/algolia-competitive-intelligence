"""Tests for reading the Hermes-produced Argus data-plane manifest."""

from __future__ import annotations

import json

from cios.admin.data_plane_manifest import ArgusDataPlaneManifestStore


def _manifest_payload(**overrides):
    payload = {
        "schema_version": 1,
        "tenant_slug": "algolia",
        "generated_at": "2026-07-12T04:05:00Z",
        "dashboard_generated_at": "2026-07-12T04:04:00Z",
        "status": "blocked_on_evidence",
        "argus_readiness": "not_actionable",
        "next_hermes_action": "configure_ga4_or_upload_demand_export",
        "source_of_truth": {
            "runtime": "Hermes",
            "domain_package": "CI-OS",
            "database": "Postgres evidence ledger",
            "ui_role": "derived readout only",
        },
        "artifact_refs": {"dashboard": "/tmp/argus-dashboard.json"},
        "planes": {
            "registry_coverage": {
                "status": "present",
                "summary": "Registry and source coverage are represented.",
                "blocks_action": False,
                "storage": ["competitors", "sources"],
                "counts": {"monitored_competitor_count": 27, "active_source_count": 48},
            },
            "audience_demand": {
                "status": "blocked_missing_demand_source",
                "summary": "Tenant-side demand is missing.",
                "blocks_action": True,
                "storage": ["demand_signals"],
                "counts": {"demand_signal_count": 0, "looker_ready_count": 0},
                "next_hermes_action": "configure_ga4_or_upload_demand_export",
                "details": {
                    "manual_import": {"ready_count": 0},
                    "ga4_connector": {"ready": False},
                },
            },
        },
        "blockers": [
            {
                "plane": "audience_demand",
                "severity": "blocks_action",
                "title": "Demand plane missing",
                "next_step": "Configure GA4 or upload a GA / Looker export.",
                "work_item_id": "argus-evidence:88:demand",
            }
        ],
        "safety": {
            "ui_must_not_invent_semantics": True,
            "recommendations_require_backend_scorecards": True,
            "empty_or_missing_plane_blocks_promotion": True,
        },
    }
    payload.update(overrides)
    return payload


def test_data_plane_manifest_store_reads_artifact_from_output_dir(tmp_path) -> None:
    artifact = tmp_path / "argus-data-plane-manifest.json"
    artifact.write_text(json.dumps(_manifest_payload()), encoding="utf-8")

    status = ArgusDataPlaneManifestStore(out_dir=tmp_path).status("algolia")

    assert status.tenant_slug == "algolia"
    assert status.status == "blocked_on_evidence"
    assert status.argus_readiness == "not_actionable"
    assert status.next_hermes_action == "configure_ga4_or_upload_demand_export"
    assert status.planes["audience_demand"].blocks_action is True
    assert status.planes["audience_demand"].counts["demand_signal_count"] == 0
    assert status.blockers[0]["title"] == "Demand plane missing"
    assert status.artifact_found is True
    assert status.artifact_path == str(artifact)


def test_data_plane_manifest_store_returns_not_recorded_when_artifact_missing(tmp_path) -> None:
    status = ArgusDataPlaneManifestStore(out_dir=tmp_path).status("algolia")

    assert status.tenant_slug == "algolia"
    assert status.status == "not_recorded"
    assert status.argus_readiness == "unknown"
    assert status.next_hermes_action == "run_dashboard_refresh"
    assert status.planes == {}
    assert status.blockers == []
    assert status.artifact_found is False
    assert status.artifact_path == str(tmp_path / "argus-data-plane-manifest.json")


def test_data_plane_manifest_store_rejects_wrong_tenant_artifact(tmp_path) -> None:
    artifact = tmp_path / "argus-data-plane-manifest.json"
    artifact.write_text(json.dumps(_manifest_payload(tenant_slug="wrong-tenant")), encoding="utf-8")

    status = ArgusDataPlaneManifestStore(out_dir=tmp_path).status("algolia")

    assert status.tenant_slug == "algolia"
    assert status.status == "artifact_error"
    assert status.argus_readiness == "unknown"
    assert "does not match algolia" in status.next_hermes_action
    assert status.artifact_found is False
