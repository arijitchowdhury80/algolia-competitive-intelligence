from __future__ import annotations

import pytest
from pydantic import ValidationError

from cios.collateral.types import BrandTokens, CollateralAsset, CollateralKind, CollateralRequest, ReviewStatus

from .conftest import make_prescription


def test_brand_tokens_requires_company_name() -> None:
    with pytest.raises(ValidationError):
        BrandTokens(company_name="")


def test_collateral_request_rejects_tenant_mismatch() -> None:
    prescription = make_prescription(tenant_id=1)
    brand = BrandTokens(company_name="Acme Corp")
    with pytest.raises(ValidationError):
        CollateralRequest(tenant_id=2, kind=CollateralKind.LANDING_PAGE, prescription=prescription, brand=brand)


def test_collateral_asset_defaults_to_draft() -> None:
    asset = CollateralAsset(
        tenant_id=1,
        kind=CollateralKind.LANDING_PAGE,
        html="<html><body>ok</body></html>",
        sources=["https://rival.com/pricing"],
        prescription_title="Undercut rival pricing",
    )
    assert asset.review_status == ReviewStatus.DRAFT


def test_collateral_asset_requires_non_empty_html() -> None:
    with pytest.raises(ValidationError):
        CollateralAsset(
            tenant_id=1,
            kind=CollateralKind.LANDING_PAGE,
            html="   ",
            prescription_title="x",
        )
