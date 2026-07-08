from __future__ import annotations

import pytest

from cios.collateral.landing_page import LandingPageGenerator, MalformedLandingPageOutput
from cios.collateral.types import BrandTokens, CollateralKind, CollateralRequest, ReviewStatus

from .conftest import FakeModel, landing_content_payload, make_prescription


def _request(**kwargs) -> CollateralRequest:
    prescription = kwargs.pop("prescription", None) or make_prescription()
    brand = kwargs.pop("brand", None) or BrandTokens(
        company_name="Acme Corp", primary_color="#123456", logo_url="https://acme.example/logo.png"
    )
    return CollateralRequest(
        tenant_id=prescription.tenant_id,
        kind=CollateralKind.LANDING_PAGE,
        prescription=prescription,
        brand=brand,
    )


async def test_generates_self_contained_html_with_grounded_claims() -> None:
    model = FakeModel([landing_content_payload()])
    asset = await LandingPageGenerator(model).generate(_request())

    assert asset.review_status == ReviewStatus.DRAFT
    assert "<script" not in asset.html  # no external/injected JS
    assert "Acme Corp" in asset.html
    assert "Rival cut its entry tier" in asset.html
    assert asset.sources == ["https://rival.com/pricing"]


async def test_brand_tokens_applied_not_hardcoded() -> None:
    model = FakeModel([landing_content_payload()])
    brand = BrandTokens(company_name="Zylo Inc", primary_color="#ff00aa", accent_color="#00ffcc")
    asset = await LandingPageGenerator(model).generate(_request(brand=brand))

    assert "Zylo Inc" in asset.html
    assert "#ff00aa" in asset.html
    assert "#00ffcc" in asset.html
    # no vendor/company literal baked into the template beyond what came from `brand`
    assert "Acme" not in asset.html


async def test_unverifiable_named_claim_without_evidence_is_flagged() -> None:
    payload = landing_content_payload(
        proof_points=[
            {"claim": "Salesforce abandoned its own comparable pricing model last year.", "evidence_url": ""},
        ]
    )
    model = FakeModel([payload])
    asset = await LandingPageGenerator(model).generate(_request())

    assert asset.review_status == ReviewStatus.NEEDS_VERIFICATION


async def test_named_claim_with_matching_evidence_is_not_flagged() -> None:
    payload = landing_content_payload(
        proof_points=[
            {"claim": "Rival Corp cut its entry tier by 20% this quarter.", "evidence_url": "https://rival.com/pricing"},
        ]
    )
    model = FakeModel([payload])
    asset = await LandingPageGenerator(model).generate(_request())

    assert asset.review_status == ReviewStatus.DRAFT


async def test_fabricated_evidence_url_is_flagged() -> None:
    payload = landing_content_payload(
        proof_points=[
            {"claim": "We are the fastest platform on the market today.", "evidence_url": "https://not-supplied.example/fact"},
        ]
    )
    model = FakeModel([payload])
    asset = await LandingPageGenerator(model).generate(_request())

    assert asset.review_status == ReviewStatus.NEEDS_VERIFICATION


async def test_draft_never_published_by_default() -> None:
    model = FakeModel([landing_content_payload()])
    asset = await LandingPageGenerator(model).generate(_request())
    assert asset.review_status in (ReviewStatus.DRAFT, ReviewStatus.NEEDS_VERIFICATION)
    assert asset.review_status != ReviewStatus.APPROVED


async def test_script_injection_in_model_output_is_escaped() -> None:
    payload = landing_content_payload(
        hero_headline="<script>alert('xss')</script>",
        proof_points=[{"claim": "<img src=x onerror=alert(1)>", "evidence_url": ""}],
    )
    model = FakeModel([payload])
    asset = await LandingPageGenerator(model).generate(_request())

    assert "<script>" not in asset.html
    assert "<img src=x onerror=" not in asset.html
    assert "&lt;script&gt;" in asset.html


async def test_malformed_json_retried_then_raises() -> None:
    model = FakeModel(["not json", "still not json"])
    with pytest.raises(MalformedLandingPageOutput):
        await LandingPageGenerator(model).generate(_request())


async def test_malformed_json_recovers_on_retry() -> None:
    model = FakeModel(["not json", landing_content_payload()])
    asset = await LandingPageGenerator(model).generate(_request())
    assert asset.html


async def test_wrong_kind_rejected() -> None:
    model = FakeModel([landing_content_payload()])
    prescription = make_prescription()
    brand = BrandTokens(company_name="Acme Corp")
    bad_request = CollateralRequest(
        tenant_id=prescription.tenant_id,
        kind=CollateralKind.MARKETING_DASHBOARD,
        prescription=prescription,
        brand=brand,
    )
    with pytest.raises(ValueError):
        await LandingPageGenerator(model).generate(bad_request)


async def test_no_external_js_or_css_loaded() -> None:
    model = FakeModel([landing_content_payload()])
    asset = await LandingPageGenerator(model).generate(_request())
    assert "<script src=" not in asset.html
    assert '<link rel="stylesheet"' not in asset.html
