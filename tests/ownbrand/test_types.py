"""Evidence rule + deterministic guard tests for ownbrand types."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from cios.ownbrand.types import (
    BrandObservation,
    BrandPositionRead,
    BrandTheme,
    OwnBrandSource,
)


def test_brand_observation_rejects_missing_quote() -> None:
    with pytest.raises(ValidationError):
        BrandObservation(
            tenant_id=1,
            source_type=OwnBrandSource.OWN_BLOG,
            source_url="https://example.com/blog/a",
            quote="",
        )


def test_brand_observation_rejects_missing_source_url() -> None:
    with pytest.raises(ValidationError):
        BrandObservation(
            tenant_id=1,
            source_type=OwnBrandSource.OWN_BLOG,
            source_url="",
            quote="We are the fastest search on the market.",
        )


def test_brand_observation_accepts_quote_and_url() -> None:
    obs = BrandObservation(
        tenant_id=1,
        source_type=OwnBrandSource.NEWSROOM,
        source_url="https://example.com/newsroom/a",
        quote="We announced our AI-native search product today.",
    )
    assert obs.quote and obs.source_url


def test_brand_theme_requires_observation_url() -> None:
    with pytest.raises(ValidationError):
        BrandTheme(label="AI-native", summary="They push AI messaging.", observation_urls=[])


def test_brand_theme_accepts_with_observation() -> None:
    theme = BrandTheme(
        label="AI-native",
        summary="They push AI messaging.",
        observation_urls=["https://example.com/blog/a"],
    )
    assert theme.observation_urls == ["https://example.com/blog/a"]


def test_to_own_position_facts_shape() -> None:
    read = BrandPositionRead(
        tenant_id=1,
        tenant_company_name="Acme",
        themes=[
            BrandTheme(
                label="AI-native",
                summary="They push AI messaging.",
                observation_urls=["https://example.com/blog/a", "https://example.com/blog/b"],
            )
        ],
        gaps_vs_competitors=["No public pricing page compared to Acme's competitors."],
        observations_considered=2,
    )
    facts = read.to_own_position_facts()
    assert len(facts) == 2
    assert facts[0].startswith("AI-native: They push AI messaging.")
    assert "https://example.com/blog/a" in facts[0]
    assert "https://example.com/blog/b" in facts[0]
    assert facts[1] == "No public pricing page compared to Acme's competitors."


def test_to_own_position_facts_empty_when_no_themes() -> None:
    read = BrandPositionRead(tenant_id=1, tenant_company_name="Acme")
    assert read.to_own_position_facts() == []
