from __future__ import annotations

import pytest

from cios.collateral.marketing_dashboard import MarketingDashboardGenerator
from cios.collateral.types import BrandTokens, CollateralKind, CollateralRequest, ReviewStatus

from .conftest import make_prescription


def _request(**kwargs) -> CollateralRequest:
    prescription = kwargs.pop("prescription", None) or make_prescription()
    brand = kwargs.pop("brand", None) or BrandTokens(company_name="Acme Corp", primary_color="#123456")
    return CollateralRequest(
        tenant_id=prescription.tenant_id,
        kind=CollateralKind.MARKETING_DASHBOARD,
        prescription=prescription,
        brand=brand,
    )


def test_renders_plays_as_tracked_initiatives() -> None:
    prescription = make_prescription()
    asset = MarketingDashboardGenerator().generate(_request(prescription=prescription))
    for step in prescription.play:
        assert step in asset.html


def test_shows_urgency_window() -> None:
    asset = MarketingDashboardGenerator().generate(_request())
    assert "This week" in asset.html


def test_shows_evidence_signals() -> None:
    prescription = make_prescription(evidence_urls=["https://rival.com/pricing", "https://rival.com/press"])
    asset = MarketingDashboardGenerator().generate(_request(prescription=prescription))
    assert "https://rival.com/pricing" in asset.html
    assert "https://rival.com/press" in asset.html
    assert asset.sources == ["https://rival.com/press", "https://rival.com/pricing"]


def test_brand_tokens_applied_not_hardcoded() -> None:
    brand = BrandTokens(company_name="Zylo Inc", primary_color="#ff00aa")
    asset = MarketingDashboardGenerator().generate(_request(brand=brand))
    assert "Zylo Inc" in asset.html
    assert "#ff00aa" in asset.html
    assert "Acme" not in asset.html


def test_draft_never_published_by_default() -> None:
    asset = MarketingDashboardGenerator().generate(_request())
    assert asset.review_status == ReviewStatus.DRAFT


def test_self_contained_no_external_js_or_css() -> None:
    asset = MarketingDashboardGenerator().generate(_request())
    assert "<script src=" not in asset.html
    assert '<link rel="stylesheet"' not in asset.html


def test_wrong_kind_rejected() -> None:
    prescription = make_prescription()
    brand = BrandTokens(company_name="Acme Corp")
    bad_request = CollateralRequest(
        tenant_id=prescription.tenant_id,
        kind=CollateralKind.LANDING_PAGE,
        prescription=prescription,
        brand=brand,
    )
    with pytest.raises(ValueError):
        MarketingDashboardGenerator().generate(bad_request)


def test_no_vendor_literal_in_template() -> None:
    """Template source must never bake in a fixed vendor/company name --
    every company reference in the rendered HTML must trace back to the
    injected BrandTokens or the prescription."""
    prescription = make_prescription()
    brand = BrandTokens(company_name="Totally Unique Co 12345")
    asset = MarketingDashboardGenerator().generate(_request(prescription=prescription, brand=brand))
    assert "Totally Unique Co 12345" in asset.html
    for vendor_word in ("Algolia", "Constructor.io", "Coveo", "Bloomreach"):
        assert vendor_word not in asset.html
