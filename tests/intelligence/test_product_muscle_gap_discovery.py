from __future__ import annotations

from cios.hunter.types import ValidationResult
from cios.intelligence.product_muscle_gap_discovery import execute_product_muscle_gap_discovery


class FakeValidator:
    def __init__(self, results: dict[str, ValidationResult]) -> None:
        self.results = results
        self.calls: list[tuple[int, str]] = []

    def validate(self, tenant_id: int, url: str) -> ValidationResult:
        self.calls.append((tenant_id, url))
        return self.results.get(
            url,
            ValidationResult(
                accepted=False,
                reason="not_stubbed",
                url=url,
                normalized_url=url,
            ),
        )


class FakeProductSurfaceRepository:
    def __init__(self) -> None:
        self.saved: list[tuple[object, ValidationResult, str]] = []

    def upsert_candidate_target(
        self,
        target,
        *,
        validation: ValidationResult,
        discovery_source: str,
    ) -> int:
        self.saved.append((target, validation, discovery_source))
        return len(self.saved)


def test_execute_product_muscle_gap_discovery_validates_and_stores_only_accepted_candidates() -> None:
    gap_plan = {
        "missing_companies": [
            {
                "competitor_id": 7,
                "company_name": "Athos Commerce",
                "candidate_surface_urls": [
                    {"surface_family": "docs", "url": "https://athoscommerce.com/docs"},
                    {"surface_family": "product_page", "url": "https://athoscommerce.com/product"},
                    {"surface_family": "pricing", "url": "https://athoscommerce.com/pricing"},
                ],
            },
            {
                "competitor_id": 15,
                "company_name": "AI Agent Ecosystem",
                "candidate_surface_urls": [],
            },
        ]
    }
    validator = FakeValidator(
        {
            "https://athoscommerce.com/docs": ValidationResult(
                accepted=True,
                reason="validated",
                url="https://athoscommerce.com/docs",
                normalized_url="https://athoscommerce.com/docs",
                source_family="docs",
                http_status=200,
            ),
            "https://athoscommerce.com/product": ValidationResult(
                accepted=True,
                reason="validated",
                url="https://athoscommerce.com/product",
                normalized_url="https://athoscommerce.com/product",
                http_status=200,
            ),
            "https://athoscommerce.com/pricing": ValidationResult(
                accepted=False,
                reason="http_error",
                url="https://athoscommerce.com/pricing",
                normalized_url="https://athoscommerce.com/pricing",
                http_status=404,
            ),
        }
    )
    repo = FakeProductSurfaceRepository()

    summary = execute_product_muscle_gap_discovery(
        tenant_id=1,
        gap_plan=gap_plan,
        validator=validator,
        product_surfaces=repo,
    )

    assert summary == {
        "status": "completed",
        "candidate_url_count": 3,
        "heuristic_candidate_url_count": 0,
        "validated_count": 2,
        "rejected_count": 1,
        "duplicate_product_surface_count": 0,
        "duplicate_source_count": 0,
        "new_candidate_rejected_count": 1,
        "stored_candidate_count": 2,
        "stored_candidates": [
            {
                "surface_id": 1,
                "company_name": "Athos Commerce",
                "surface_family": "docs",
                "url": "https://athoscommerce.com/docs",
                "http_status": 200,
            },
            {
                "surface_id": 2,
                "company_name": "Athos Commerce",
                "surface_family": "product_page",
                "url": "https://athoscommerce.com/product",
                "http_status": 200,
            },
        ],
        "rejected_candidates": [
            {
                "company_name": "Athos Commerce",
                "surface_family": "pricing",
                "url": "https://athoscommerce.com/pricing",
                "reason": "http_error",
                "http_status": 404,
            }
        ],
    }
    assert validator.calls == [
        (1, "https://athoscommerce.com/docs"),
        (1, "https://athoscommerce.com/product"),
        (1, "https://athoscommerce.com/pricing"),
    ]
    assert [saved[0].surface_family for saved in repo.saved] == ["docs", "product_page"]
    assert [saved[0].company_id for saved in repo.saved] == [7, 7]
    assert [saved[2] for saved in repo.saved] == ["product_muscle_gap_plan", "product_muscle_gap_plan"]


def test_execute_product_muscle_gap_discovery_validates_prioritized_unknown_feature_targets() -> None:
    gap_plan = {
        "missing_companies": [],
        "feature_unknown_collection_targets": [
            {
                "competitor_id": 9,
                "company_name": "Bloomreach",
                "capability_text": "AI Shopping Agent",
                "priority_score": 110,
                "candidate_surface_urls": [
                    {"surface_family": "docs", "url": "https://bloomreach.com/docs"},
                ],
            }
        ],
    }
    validator = FakeValidator(
        {
            "https://bloomreach.com/docs": ValidationResult(
                accepted=True,
                reason="validated",
                url="https://bloomreach.com/docs",
                normalized_url="https://bloomreach.com/docs",
                source_family="docs",
                http_status=200,
            )
        }
    )
    repo = FakeProductSurfaceRepository()

    summary = execute_product_muscle_gap_discovery(
        tenant_id=1,
        gap_plan=gap_plan,
        validator=validator,
        product_surfaces=repo,
    )

    assert summary["candidate_url_count"] == 1
    assert summary["validated_count"] == 1
    assert summary["stored_candidates"] == [
        {
            "surface_id": 1,
            "company_name": "Bloomreach",
            "surface_family": "docs",
            "url": "https://bloomreach.com/docs",
            "http_status": 200,
            "capability_text": "AI Shopping Agent",
            "priority_score": 110,
        }
    ]
    assert validator.calls == [(1, "https://bloomreach.com/docs")]
    assert [saved[0].company_id for saved in repo.saved] == [9]


def test_execute_product_muscle_gap_discovery_separates_duplicates_from_new_candidate_failures() -> None:
    gap_plan = {
        "feature_unknown_collection_targets": [
            {
                "competitor_id": 11,
                "company_name": "Coveo",
                "capability_text": "Conversational Shopping Agent",
                "candidate_surface_urls": [
                    {
                        "surface_family": "product_page",
                        "url": "https://www.coveo.com/en/platform",
                    },
                    {
                        "surface_family": "docs",
                        "url": "https://www.coveo.com/en/docs",
                    },
                ],
            }
        ],
    }
    validator = FakeValidator(
        {
            "https://www.coveo.com/en/platform": ValidationResult(
                accepted=False,
                reason="duplicate_normalized_url",
                url="https://www.coveo.com/en/platform",
                normalized_url="https://www.coveo.com/en/platform",
            ),
            "https://www.coveo.com/en/docs": ValidationResult(
                accepted=False,
                reason="http_error",
                url="https://www.coveo.com/en/docs",
                normalized_url="https://www.coveo.com/en/docs",
                http_status=404,
            ),
        }
    )
    repo = FakeProductSurfaceRepository()

    summary = execute_product_muscle_gap_discovery(
        tenant_id=1,
        gap_plan=gap_plan,
        validator=validator,
        product_surfaces=repo,
    )

    assert summary["candidate_url_count"] == 2
    assert summary["stored_candidate_count"] == 0
    assert summary["rejected_count"] == 2
    assert summary["duplicate_product_surface_count"] == 1
    assert summary["duplicate_source_count"] == 1
    assert summary["new_candidate_rejected_count"] == 1
    assert summary["rejected_candidates"][0]["reason"] == "duplicate_normalized_url"
    assert summary["rejected_candidates"][1]["reason"] == "http_error"
    assert repo.saved == []


def test_execute_product_muscle_gap_discovery_validates_heuristic_surface_probes() -> None:
    gap_plan = {
        "missing_companies": [
            {
                "competitor_id": 21,
                "company_name": "Algonomy",
                "domain": "algonomy.com",
                "candidate_surface_urls": [],
                "heuristic_surface_probes": [
                    {
                        "surface_family": "docs",
                        "url": "https://algonomy.com/docs",
                        "discovery_reason": "domain_heuristic",
                        "requires_validation": True,
                    },
                    {
                        "surface_family": "pricing",
                        "url": "https://algonomy.com/pricing",
                        "discovery_reason": "domain_heuristic",
                        "requires_validation": True,
                    },
                ],
            }
        ]
    }
    validator = FakeValidator(
        {
            "https://algonomy.com/docs": ValidationResult(
                accepted=True,
                reason="validated",
                url="https://algonomy.com/docs",
                normalized_url="https://algonomy.com/docs",
                source_family="docs",
                http_status=200,
            ),
            "https://algonomy.com/pricing": ValidationResult(
                accepted=False,
                reason="http_error",
                url="https://algonomy.com/pricing",
                normalized_url="https://algonomy.com/pricing",
                http_status=404,
            ),
        }
    )
    repo = FakeProductSurfaceRepository()

    summary = execute_product_muscle_gap_discovery(
        tenant_id=1,
        gap_plan=gap_plan,
        validator=validator,
        product_surfaces=repo,
    )

    assert summary["candidate_url_count"] == 2
    assert summary["heuristic_candidate_url_count"] == 2
    assert summary["validated_count"] == 1
    assert summary["stored_candidates"] == [
        {
            "surface_id": 1,
            "company_name": "Algonomy",
            "surface_family": "docs",
            "url": "https://algonomy.com/docs",
            "http_status": 200,
            "candidate_source": "heuristic_surface_probes",
            "discovery_reason": "domain_heuristic",
        }
    ]
    assert summary["rejected_candidates"] == [
        {
            "company_name": "Algonomy",
            "surface_family": "pricing",
            "url": "https://algonomy.com/pricing",
            "reason": "http_error",
            "http_status": 404,
            "candidate_source": "heuristic_surface_probes",
            "discovery_reason": "domain_heuristic",
        }
    ]
    assert validator.calls == [
        (1, "https://algonomy.com/docs"),
        (1, "https://algonomy.com/pricing"),
    ]
    assert [saved[0].surface_family for saved in repo.saved] == ["docs"]


def test_execute_product_muscle_gap_discovery_validates_empty_surface_targets() -> None:
    gap_plan = {
        "missing_companies": [],
        "empty_surface_targets": [
            {
                "competitor_id": 9,
                "company_name": "Klevu",
                "failed_surface_family": "docs",
                "candidate_surface_urls": [],
                "heuristic_surface_probes": [
                    {
                        "surface_family": "changelog",
                        "url": "https://klevu.com/changelog",
                        "discovery_reason": "domain_heuristic",
                        "requires_validation": True,
                    }
                ],
            }
        ],
    }
    validator = FakeValidator(
        {
            "https://klevu.com/changelog": ValidationResult(
                accepted=True,
                reason="validated",
                url="https://klevu.com/changelog",
                normalized_url="https://klevu.com/changelog",
                source_family="changelog",
                http_status=200,
            )
        }
    )
    repo = FakeProductSurfaceRepository()

    summary = execute_product_muscle_gap_discovery(
        tenant_id=1,
        gap_plan=gap_plan,
        validator=validator,
        product_surfaces=repo,
    )

    assert summary["candidate_url_count"] == 1
    assert summary["heuristic_candidate_url_count"] == 1
    assert summary["validated_count"] == 1
    assert summary["stored_candidates"] == [
        {
            "surface_id": 1,
            "company_name": "Klevu",
            "surface_family": "changelog",
            "url": "https://klevu.com/changelog",
            "http_status": 200,
            "candidate_source": "heuristic_surface_probes",
            "discovery_reason": "domain_heuristic",
            "failed_surface_family": "docs",
        }
    ]
    assert [saved[0].company_id for saved in repo.saved] == [9]
