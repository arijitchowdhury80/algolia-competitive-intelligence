"""Smoke contract for the Hermes-callable Argus product-muscle work queue export."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from cios.admin.feature_comparison import build_feature_comparison_state
from cios.admin.types import (
    CompetitorAdminRecord,
    EvidenceLedgerState,
    FeatureMatrixAdminRecord,
    ProductSurfaceAdminRecord,
    RegistryState,
)


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "export_argus_product_muscle_work_queue.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("export_argus_product_muscle_work_queue", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_export_argus_product_muscle_work_queue_script_exists_and_imports() -> None:
    module = _load_module()

    assert hasattr(module, "main")
    assert hasattr(module, "resolve_tenant_id")
    assert hasattr(module, "build_product_muscle_work_queue_payload")


def test_build_product_muscle_work_queue_payload_is_machine_readable_and_traceable() -> None:
    module = _load_module()
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=2,
                competitor_name="Bloomreach",
                domain="bloomreach.com",
                category="commerce search",
                priority=2,
                status="active",
                product_surfaces=[],
            )
        ],
    )
    comparison = build_feature_comparison_state(
        registry=registry,
        feature_matrix=[
            FeatureMatrixAdminRecord(
                capability_text="agentic product discovery",
                company_name="Algolia",
                company_role="own",
                position_status="proven",
                evidence_refs=[{"source_url": "https://www.algolia.com/docs"}],
            )
        ],
    )

    payload = module.build_product_muscle_work_queue_payload(
        tenant_slug="algolia",
        tenant_id=1,
        registry=registry,
        feature_comparison=comparison,
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        generated_at="2026-07-12T05:20:00Z",
    )

    assert payload["tenant_slug"] == "algolia"
    assert payload["tenant_id"] == 1
    assert payload["generated_at"] == "2026-07-12T05:20:00Z"
    assert payload["work_item_count"] == 1
    assert payload["blocking_count"] == 1
    assert payload["limiting_count"] == 0
    assert payload["items"][0]["work_item_id"] == "product-muscle:competitor:2:missing-surfaces"
    assert payload["items"][0]["company_name"] == "Bloomreach"
    assert payload["items"][0]["severity"] == "blocks_feature_matrix"
    assert payload["items"][0]["primary_action_label"] == "Add product surface"


def test_build_product_muscle_work_queue_payload_runs_extraction_for_active_surfaces_without_feature_evidence() -> None:
    module = _load_module()
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=9,
                competitor_name="Klevu",
                domain="klevu.com",
                category="search/discovery",
                priority=2,
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=44,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.klevu.com/",
                        status="active",
                    )
                ],
            )
        ],
    )

    payload = module.build_product_muscle_work_queue_payload(
        tenant_slug="algolia",
        tenant_id=1,
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        generated_at="2026-07-12T21:10:00Z",
    )

    item = payload["items"][0]
    assert item["work_item_id"] == "product-muscle:competitor:9:no-feature-evidence"
    assert item["primary_action_label"] == "Run surface extraction"
    assert item["primary_action_href"] == (
        "/admin/algolia/argus/product-surface-extraction?company_name=Klevu"
    )
    assert item["primary_action_method"] == "post"
    assert item["secondary_action_label"] == "Open product surfaces"


def test_build_product_muscle_work_queue_payload_includes_argus_planned_capability_tasks() -> None:
    module = _load_module()
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=5,
                competitor_name="Coveo",
                domain="coveo.com",
                category="search/discovery",
                priority=2,
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=9,
                        company_name="Coveo",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.coveo.com/en/",
                        status="active",
                    )
                ],
            )
        ],
    )
    feature_comparison = build_feature_comparison_state(
        registry=registry,
        feature_matrix=[
            FeatureMatrixAdminRecord(
                capability_text="semantic ranking",
                company_name="Coveo",
                company_role="competitor",
                position_status="proven",
                evidence_refs=[{"source_url": "https://docs.coveo.com/en/semantic-ranking"}],
            )
        ],
        planned_capabilities=["Channel Assistant"],
    )

    payload = module.build_product_muscle_work_queue_payload(
        tenant_slug="algolia",
        tenant_id=1,
        registry=registry,
        feature_comparison=feature_comparison,
        evidence_ledger=EvidenceLedgerState(
            tenant_slug="algolia",
            tenant_id=1,
            product_events=[
                {
                    "product_event_id": 501,
                    "company_name": "Coveo",
                    "company_role": "competitor",
                    "capability_text": "semantic ranking",
                    "change_type": "docs",
                    "summary": "Coveo has semantic ranking docs.",
                    "evidence_refs": [{"source_url": "https://docs.coveo.com/en/semantic-ranking"}],
                }
            ],
        ),
        generated_at="2026-07-12T21:10:00Z",
    )

    item = payload["items"][0]
    assert item["work_item_id"] == "product-muscle:competitor:5:capability:channel-assistant"
    assert item["title"] == "Coveo has no product proof for Channel Assistant"
    assert item["observed_state"]["capability_text"] == "Channel Assistant"
    assert item["primary_action_label"] == "Run surface extraction"


def test_product_muscle_export_extracts_planned_capabilities_from_demand_readiness() -> None:
    module = _load_module()

    capabilities = module.planned_capabilities_from_demand_readiness(
        {
            "demand_collection_plan": {
                "topics": [
                    {"topic": "Channel Assistant", "capability_key": "channel-assistant"},
                    {"topic": "Channel Assistant", "capability_key": "duplicate"},
                    {"capability_key": "context engineering"},
                    {"topic": " "},
                ]
            }
        }
    )

    assert capabilities == ["Channel Assistant", "context engineering"]


def test_build_product_muscle_work_queue_payload_includes_product_surface_execution_trace() -> None:
    module = _load_module()
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=5,
                competitor_name="Coveo",
                domain="coveo.com",
                category="search/discovery",
                priority=2,
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=9,
                        company_name="Coveo",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.coveo.com/en/",
                        status="active",
                    )
                ],
            )
        ],
    )

    payload = module.build_product_muscle_work_queue_payload(
        tenant_slug="algolia",
        tenant_id=1,
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        product_surface_execution_trace={
            ("coveo", "competitor"): {
                "planned_surface_count": 1,
                "succeeded_surface_count": 1,
                "failed_surface_count": 0,
                "row_count": 0,
                "empty_output_count": 1,
                "summary_path": "/tmp/cios-product-market/algolia/product-surface-execution-summary.json",
            }
        },
        generated_at="2026-07-12T05:20:00Z",
    )

    item = payload["items"][0]
    assert item["work_item_id"] == "product-muscle:competitor:5:no-feature-evidence"
    assert item["observed_state"]["latest_surface_export_planned_count"] == 1
    assert item["observed_state"]["latest_surface_export_succeeded_count"] == 1
    assert item["observed_state"]["latest_surface_export_failed_count"] == 0
    assert item["observed_state"]["latest_surface_export_row_count"] == 0
    assert item["observed_state"]["latest_surface_export_empty_output_count"] == 1
    assert item["observed_state"]["latest_surface_export_failure_category"] == "empty_extraction"
    assert item["next_step"].startswith("Review the product-surface extraction prompt")
    assert item["primary_action_label"] == "Run repair retry"
    assert item["primary_action_href"] == (
        "/admin/algolia/argus/product-surface-repair?company_name=Coveo&category=empty_extraction"
    )
    assert item["primary_action_method"] == "post"


def test_export_argus_product_muscle_work_queue_writes_output_file(tmp_path) -> None:
    module = _load_module()
    payload = {
        "tenant_slug": "algolia",
        "tenant_id": 1,
        "generated_at": "2026-07-12T05:20:00Z",
        "work_item_count": 0,
        "blocking_count": 0,
        "limiting_count": 0,
        "items": [],
    }
    output = tmp_path / "work" / "argus-product-muscle-work-queue.json"

    module.write_payload(payload, output)

    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_export_argus_product_muscle_work_queue_resolves_tenant_slug() -> None:
    module = _load_module()

    class Conn:
        def execute(self, sql, params):
            assert "FROM tenants" in sql
            assert params == ("algolia",)
            return self

        def fetchone(self):
            return {"id": 42}

    assert module.resolve_tenant_id(Conn(), "algolia") == 42
