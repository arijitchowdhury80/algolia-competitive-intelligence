"""Tests for CompetitorResearcher: deterministic vetting + JSON parsing.

No network -- BrainModel is an in-memory fake.
"""

from __future__ import annotations

import json

import pytest

from cios.onboard.research import CompetitorResearcher
from cios.onboard.types import CompetitorCandidate, OnboardRequest
from cios.platform.models.types import ModelRequest, ModelResponse, TokenUsage


class FakeModel:
    def __init__(self, payload: dict):
        self._payload = payload
        self.last_request: ModelRequest | None = None

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.last_request = request
        return ModelResponse(
            text=json.dumps(self._payload),
            usage=TokenUsage(),
            latency_ms=1.0,
            provider="fake",
            provider_model_id="fake",
        )


def _candidates(*pairs: tuple[str, str]) -> list[CompetitorCandidate]:
    return [CompetitorCandidate(name=n, domain=d, why="competes for the same buyers") for n, d in pairs]


def test_vet_dedups_by_domain():
    researcher = CompetitorResearcher(model=FakeModel({}))
    raw = _candidates(("Acme", "acme.com"), ("Acme Inc", "acme.com"), ("Other", "other.com"))
    vetted = researcher.vet(raw, own_domain="tenant.com")
    assert [c.name for c in vetted] == ["Acme", "Other"]


def test_vet_excludes_own_domain():
    researcher = CompetitorResearcher(model=FakeModel({}))
    raw = _candidates(("Tenant Co", "tenant.com"), ("Other", "other.com"))
    vetted = researcher.vet(raw, own_domain="https://www.tenant.com/")
    assert [c.name for c in vetted] == ["Other"]


def test_vet_caps_the_set():
    researcher = CompetitorResearcher(model=FakeModel({}))
    raw = _candidates(*[(f"Co{i}", f"co{i}.com") for i in range(20)])
    vetted = researcher.vet(raw, own_domain="tenant.com", cap=8)
    assert len(vetted) == 8


def test_vet_dedups_by_lowercased_name_when_no_domain():
    researcher = CompetitorResearcher(model=FakeModel({}))
    raw = [
        CompetitorCandidate(name="Acme", domain=None, why="x"),
        CompetitorCandidate(name="ACME", domain=None, why="y"),
    ]
    vetted = researcher.vet(raw, own_domain="tenant.com")
    assert len(vetted) == 1


@pytest.mark.asyncio
async def test_research_parses_strict_json_and_vets():
    payload = {
        "competitors": [
            {"name": "Acme", "domain": "acme.com", "why": "same buyer, documented rivalry"},
            {"name": "Tenant Co", "domain": "tenant.com", "why": "self, must be excluded"},
        ]
    }
    model = FakeModel(payload)
    researcher = CompetitorResearcher(model=model)
    request = OnboardRequest(company_name="Tenant Co", domain="tenant.com")

    result = await researcher.research(request)

    assert [c.name for c in result] == ["Acme"]
    assert model.last_request is not None
    assert "Tenant Co" in model.last_request.prompt
    assert "tenant.com" in model.last_request.prompt


@pytest.mark.asyncio
async def test_research_returns_empty_on_malformed_json():
    model = FakeModel({})

    class BrokenModel:
        async def generate(self, request: ModelRequest) -> ModelResponse:
            return ModelResponse(
                text="not json at all",
                usage=TokenUsage(),
                latency_ms=1.0,
                provider="fake",
                provider_model_id="fake",
            )

    researcher = CompetitorResearcher(model=BrokenModel())
    request = OnboardRequest(company_name="Tenant Co", domain="tenant.com")

    result = await researcher.research(request)

    assert result == []


@pytest.mark.asyncio
async def test_no_vendor_literals_in_prompt():
    """Rule 1 (doctrine): prompts are domain-agnostic. The prompt must carry
    no fixed vendor/vertical vocabulary -- only the request's own data."""
    model = FakeModel({"competitors": []})
    researcher = CompetitorResearcher(model=model)
    request = OnboardRequest(company_name="Spryker", domain="spryker.com")

    await researcher.research(request)

    prompt = model.last_request.prompt.lower()
    banned = ["algolia", "elasticsearch", "shopify", "commercetools", "search engine"]
    for term in banned:
        assert term not in prompt
