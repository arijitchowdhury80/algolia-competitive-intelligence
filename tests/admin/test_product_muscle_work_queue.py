from __future__ import annotations

from cios.admin.feature_comparison import build_feature_comparison_state
from cios.admin.product_muscle_work_queue import build_product_muscle_work_queue
from cios.admin.types import (
    CompetitorAdminRecord,
    EvidenceLedgerState,
    FeatureMatrixAdminRecord,
    ProductSurfaceAdminRecord,
    RegistryState,
)


def test_product_muscle_queue_blocks_competitor_with_no_active_product_surfaces() -> None:
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

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=comparison,
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
    )

    assert len(items) == 1
    item = items[0]
    assert item.work_item_id == "product-muscle:competitor:2:missing-surfaces"
    assert item.company_name == "Bloomreach"
    assert item.severity == "blocks_feature_matrix"
    assert item.title == "Bloomreach has no active product surfaces"
    assert item.blocks == ["feature comparison", "product gap scoring", "product-backed recommendations"]
    assert item.primary_action_href == "/admin?tenant=algolia#add-product-surface"
    assert item.secondary_action_href == "/admin/algolia/argus/ledger-refresh"
    assert item.observed_state["active_product_surface_count"] == 0
    assert item.observed_state["known_capability_cell_count"] == 0


def test_product_muscle_queue_skips_unclassified_source_buckets_without_product_relevance() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=21,
                competitor_name="CMSWire Digital Experience",
                domain=None,
                category=None,
                priority=3,
                status="active",
                product_surfaces=[],
            ),
            CompetitorAdminRecord(
                competitor_id=28,
                competitor_name="Gartner MQ Search & Product Discovery",
                domain=None,
                category=None,
                priority=3,
                status="active",
                product_surfaces=[],
            ),
            CompetitorAdminRecord(
                competitor_id=22,
                competitor_name="Community",
                domain=None,
                category=None,
                priority=3,
                status="active",
                product_surfaces=[],
            ),
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
    )

    assert items == []


def test_product_muscle_queue_keeps_domain_only_admin_added_competitor_relevant() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=42,
                competitor_name="New Search Co",
                domain="newsearch.example",
                category=None,
                priority=3,
                status="active",
                product_surfaces=[],
            ),
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
    )

    assert len(items) == 1
    assert items[0].work_item_id == "product-muscle:competitor:42:missing-surfaces"
    assert items[0].company_name == "New Search Co"


def test_product_muscle_queue_skips_explicit_non_product_categories_without_product_evidence() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=52,
                competitor_name="Market Newsletter",
                domain="newsletter.example",
                category="media publication",
                priority=3,
                status="active",
                product_surfaces=[],
            ),
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
    )

    assert items == []


def test_product_muscle_queue_limits_confidence_when_surfaces_have_no_extracted_feature_evidence() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=3,
                competitor_name="Coveo",
                domain="coveo.com",
                category="commerce search",
                priority=2,
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=30,
                        company_name="Coveo",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://www.coveo.com/en/docs",
                        status="active",
                    )
                ],
            )
        ],
    )
    comparison = build_feature_comparison_state(
        registry=registry,
        feature_matrix=[
            FeatureMatrixAdminRecord(
                capability_text="agentic product discovery",
                company_name="Constructor",
                company_role="competitor",
                position_status="proven",
                evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=comparison,
        evidence_ledger=EvidenceLedgerState(
            tenant_slug="algolia",
            tenant_id=1,
            product_events=[],
        ),
        product_surface_execution_trace={
            ("coveo", "competitor"): {
                "planned_surface_count": 4,
                "succeeded_surface_count": 1,
                "failed_surface_count": 3,
                "row_count": 0,
                "empty_output_count": 1,
                "last_error": "Scout product surface scrape returned no markdown",
                "summary_path": "/tmp/cios-product-market/algolia/product-surface-execution-summary.json",
            }
        },
    )

    assert len(items) == 1
    item = items[0]
    assert item.work_item_id == "product-muscle:competitor:3:no-feature-evidence"
    assert item.company_name == "Coveo"
    assert item.severity == "limits_confidence"
    assert item.title == "Coveo has product surfaces but no feature evidence"
    assert item.blocks == ["feature confidence", "competitor product read", "quiet-day trust"]
    assert item.observed_state["active_product_surface_count"] == 1
    assert item.observed_state["known_capability_cell_count"] == 0
    assert item.observed_state["latest_surface_export_planned_count"] == 4
    assert item.observed_state["latest_surface_export_succeeded_count"] == 1
    assert item.observed_state["latest_surface_export_failed_count"] == 3
    assert item.observed_state["latest_surface_export_row_count"] == 0
    assert item.observed_state["latest_surface_export_empty_output_count"] == 1
    assert item.observed_state["latest_surface_export_last_error"] == (
        "Scout product surface scrape returned no markdown"
    )
    assert item.observed_state["latest_surface_export_failure_category"] == "no_markdown"
    assert item.observed_state["latest_surface_export_repair_action"].startswith(
        "Replace or fix the product surface URL"
    )
    assert item.next_step.startswith("Replace or fix the product surface URL")
    assert item.primary_action_label == "Run repair retry"
    assert item.primary_action_method == "post"
    assert item.primary_action_href == (
        "/admin/algolia/argus/product-surface-repair?company_name=Coveo&category=no_markdown"
    )
    assert item.secondary_action_label == "Open product surfaces"
    assert item.secondary_action_href == "/admin?tenant=algolia#add-product-surface"


def test_product_muscle_queue_targets_argus_planned_unknown_capabilities() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=3,
                competitor_name="Coveo",
                domain="coveo.com",
                category="commerce search",
                priority=2,
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=30,
                        company_name="Coveo",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.coveo.com/",
                        status="active",
                    )
                ],
            )
        ],
    )
    comparison = build_feature_comparison_state(
        registry=registry,
        feature_matrix=[
            FeatureMatrixAdminRecord(
                capability_text="semantic ranking",
                company_name="Coveo",
                company_role="competitor",
                position_status="proven",
                evidence_refs=[{"source_url": "https://docs.coveo.com/ranking"}],
            )
        ],
        planned_capabilities=["Channel Assistant"],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=comparison,
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
                    "evidence_refs": [{"source_url": "https://docs.coveo.com/ranking"}],
                }
            ],
        ),
    )

    targeted = [
        item
        for item in items
        if item.work_item_id == "product-muscle:competitor:3:capability:channel-assistant"
    ]
    assert len(targeted) == 1
    item = targeted[0]
    assert item.title == "Coveo has no product proof for Channel Assistant"
    assert item.severity == "limits_confidence"
    assert item.blocks == ["capability comparison", "feature gap scoring", "demand-backed recommendations"]
    assert item.observed_state["capability_text"] == "Channel Assistant"
    assert item.observed_state["matrix_cell_status"] == "unknown"
    assert item.primary_action_label == "Run surface extraction"
    assert item.primary_action_href == (
        "/admin/algolia/argus/product-surface-extraction?"
        "company_name=Coveo&focus_capability=Channel+Assistant"
    )
    assert item.secondary_action_label == "Refresh Argus from evidence ledger"


def test_product_muscle_queue_classifies_timeout_surface_failures() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=35,
                competitor_name="Meilisearch",
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=146,
                        company_name="Meilisearch",
                        company_role="competitor",
                        surface_family="changelog",
                        url="https://github.com/meilisearch/meilisearch/releases",
                        status="active",
                    )
                ],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        product_surface_execution_trace={
            ("meilisearch", "competitor"): {
                "planned_surface_count": 1,
                "succeeded_surface_count": 0,
                "failed_surface_count": 1,
                "row_count": 0,
                "empty_output_count": 0,
                "last_error": "subprocess.TimeoutExpired: scout_http_shim scrape timed out after 120 seconds",
            }
        },
    )

    item = items[0]
    assert item.observed_state["latest_surface_export_failure_category"] == "timeout"
    assert item.observed_state["latest_surface_export_repair_action"].startswith(
        "Retry the surface with JavaScript enabled"
    )
    assert item.next_step.startswith("Retry the surface with JavaScript enabled")
    assert item.primary_action_label == "Run repair retry"
    assert item.primary_action_href == (
        "/admin/algolia/argus/product-surface-repair?company_name=Meilisearch&category=timeout"
    )


def test_product_muscle_queue_classifies_empty_successful_exports() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=40,
                competitor_name="Typesense",
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=150,
                        company_name="Typesense",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://typesense.org/docs/",
                        status="active",
                    )
                ],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        product_surface_execution_trace={
            ("typesense", "competitor"): {
                "planned_surface_count": 1,
                "succeeded_surface_count": 1,
                "failed_surface_count": 0,
                "row_count": 0,
                "empty_output_count": 1,
            }
        },
    )

    item = items[0]
    assert item.observed_state["latest_surface_export_failure_category"] == "empty_extraction"
    assert item.observed_state["latest_surface_export_repair_action"].startswith(
        "Review the product-surface extraction prompt"
    )
    assert item.next_step.startswith("Review the product-surface extraction prompt")


def test_product_muscle_queue_promotes_candidate_surface_before_retrying_empty_export() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=9,
                competitor_name="Klevu",
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=150,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.klevu.com/",
                        status="active",
                    ),
                    ProductSurfaceAdminRecord(
                        surface_id=151,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="changelog",
                        url="https://www.klevu.com/changelog/",
                        status="candidate",
                    ),
                ],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        product_surface_execution_trace={
            ("klevu", "competitor"): {
                "planned_surface_count": 1,
                "succeeded_surface_count": 1,
                "failed_surface_count": 0,
                "row_count": 0,
                "empty_output_count": 1,
            }
        },
    )

    item = items[0]
    assert item.observed_state["candidate_product_surface_count"] == 1
    assert item.observed_state["latest_surface_export_failure_category"] == "empty_extraction"
    assert item.next_step.startswith("Promote validated candidate product surfaces for Klevu")
    assert item.primary_action_label == "Promote candidate surface"
    assert item.primary_action_href == (
        "/admin/algolia/argus/product-surface-candidates/promote?company_name=Klevu&limit=1"
    )
    assert item.primary_action_method == "post"
    assert item.secondary_action_label == "Run repair retry"
    assert item.secondary_action_href == (
        "/admin/algolia/argus/product-surface-repair?company_name=Klevu&category=empty_extraction"
    )


def test_product_muscle_queue_promotes_candidate_surface_before_retrying_failed_export() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=9,
                competitor_name="Klevu",
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=150,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.klevu.com/",
                        status="active",
                    ),
                    ProductSurfaceAdminRecord(
                        surface_id=151,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="pricing",
                        url="https://klevu.com/pricing",
                        status="candidate",
                    ),
                    ProductSurfaceAdminRecord(
                        surface_id=152,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="integration",
                        url="https://klevu.com/integrations",
                        status="candidate",
                    ),
                ],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        product_surface_execution_trace={
            ("klevu", "competitor"): {
                "planned_surface_count": 1,
                "succeeded_surface_count": 0,
                "failed_surface_count": 1,
                "row_count": 0,
                "empty_output_count": 0,
                "last_error": "Scout returned exit code 2",
            }
        },
    )

    item = items[0]
    assert item.observed_state["candidate_product_surface_count"] == 2
    assert item.observed_state["latest_surface_export_failure_category"] == "scout_failure"
    assert item.next_step.startswith("Promote validated candidate product surfaces for Klevu")
    assert item.primary_action_label == "Promote candidate surface"
    assert item.primary_action_href == (
        "/admin/algolia/argus/product-surface-candidates/promote?company_name=Klevu&limit=1"
    )
    assert item.primary_action_method == "post"
    assert item.secondary_action_label == "Run repair retry"
    assert item.secondary_action_href == (
        "/admin/algolia/argus/product-surface-repair?company_name=Klevu&category=scout_failure"
    )


def test_product_muscle_queue_extracts_newly_promoted_active_surfaces_before_retrying_old_failure() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=9,
                competitor_name="Klevu",
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=150,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="docs",
                        url="https://docs.klevu.com/",
                        status="active",
                    ),
                    ProductSurfaceAdminRecord(
                        surface_id=151,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="pricing",
                        url="https://klevu.com/pricing",
                        status="active",
                    ),
                    ProductSurfaceAdminRecord(
                        surface_id=152,
                        company_name="Klevu",
                        company_role="competitor",
                        surface_family="integration",
                        url="https://klevu.com/integrations",
                        status="active",
                    ),
                ],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=build_feature_comparison_state(registry=registry, feature_matrix=[]),
        evidence_ledger=EvidenceLedgerState(tenant_slug="algolia", tenant_id=1),
        product_surface_execution_trace={
            ("klevu", "competitor"): {
                "planned_surface_count": 1,
                "succeeded_surface_count": 0,
                "failed_surface_count": 1,
                "row_count": 0,
                "empty_output_count": 0,
                "last_error": "Scout returned exit code 2 for the old docs surface",
            }
        },
    )

    item = items[0]
    assert item.observed_state["active_product_surface_count"] == 3
    assert item.observed_state["candidate_product_surface_count"] == 0
    assert item.observed_state["latest_surface_export_planned_count"] == 1
    assert item.next_step.startswith("Run product-surface extraction for newly active Klevu surfaces")
    assert item.primary_action_label == "Run surface extraction"
    assert item.primary_action_href == "/admin/algolia/argus/product-surface-extraction?company_name=Klevu"
    assert item.primary_action_method == "post"
    assert item.secondary_action_label == "Run repair retry"
    assert item.secondary_action_href == (
        "/admin/algolia/argus/product-surface-repair?company_name=Klevu&category=scout_failure"
    )


def test_product_muscle_queue_ignores_retired_competitors_and_companies_with_evidence() -> None:
    registry = RegistryState(
        tenant_slug="algolia",
        tenant_id=1,
        competitors=[
            CompetitorAdminRecord(
                competitor_id=1,
                competitor_name="Constructor",
                status="active",
                product_surfaces=[
                    ProductSurfaceAdminRecord(
                        surface_id=30,
                        company_name="Constructor",
                        company_role="competitor",
                        surface_family="changelog",
                        url="https://constructor.com/changelog",
                        status="active",
                    )
                ],
            ),
            CompetitorAdminRecord(
                competitor_id=4,
                competitor_name="RetiredCo",
                status="retired",
                product_surfaces=[],
            ),
        ],
    )
    comparison = build_feature_comparison_state(
        registry=registry,
        feature_matrix=[
            FeatureMatrixAdminRecord(
                capability_text="agentic product discovery",
                company_name="Constructor",
                company_role="competitor",
                position_status="proven",
                evidence_refs=[{"source_url": "https://constructor.com/changelog"}],
            )
        ],
    )

    items = build_product_muscle_work_queue(
        tenant_slug="algolia",
        registry=registry,
        feature_comparison=comparison,
        evidence_ledger=EvidenceLedgerState(
            tenant_slug="algolia",
            tenant_id=1,
            product_events=[
                {
                    "product_event_id": 501,
                    "company_name": "Constructor",
                    "company_role": "competitor",
                    "capability_text": "agentic product discovery",
                    "change_type": "release",
                    "summary": "Constructor released agentic discovery updates.",
                    "evidence_refs": [{"source_url": "https://constructor.com/changelog"}],
                }
            ],
        ),
    )

    assert items == []
