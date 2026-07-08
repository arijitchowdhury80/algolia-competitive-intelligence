"""Collateral generator (Gate 19): turns a decided Prescription into a
produced marketing asset -- a landing page or a marketing/campaign
dashboard -- per docs/planning/CI-OS-product-doctrine-2026-07-08.md
Addendum 2 point 4."""

from __future__ import annotations

from .landing_page import LandingPageGenerator, MalformedLandingPageOutput
from .marketing_dashboard import MarketingDashboardGenerator
from .types import (
    BrandTokens,
    CollateralAsset,
    CollateralKind,
    CollateralRequest,
    ReviewStatus,
)

__all__ = [
    "BrandTokens",
    "CollateralAsset",
    "CollateralKind",
    "CollateralRequest",
    "ReviewStatus",
    "LandingPageGenerator",
    "MalformedLandingPageOutput",
    "MarketingDashboardGenerator",
]
