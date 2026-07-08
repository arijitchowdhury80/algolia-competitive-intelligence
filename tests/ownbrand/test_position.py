"""Position compiler tests: evidence rule, theme-needs-observation guard,
adapter output shape. Fake BrainModel only -- no network."""

from __future__ import annotations

import json

import pytest

from cios.ownbrand.position import BrandPositionCompiler, MalformedPositionOutput
from cios.ownbrand.types import BrandObservation, OwnBrandSource
from cios.platform.models.types import ModelRequest, ModelResponse


def _observation(url: str = "https://example.com/blog/a") -> BrandObservation:
    return BrandObservation(
        tenant_id=1,
        source_type=OwnBrandSource.OWN_BLOG,
        source_url=url,
        quote="We are doubling down on AI-native search this year.",
    )


class FakeModel:
    def __init__(self, payload: dict) -> None:
        self._payload = payload
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        return ModelResponse(
            text=json.dumps(self._payload),
            parsed_json=self._payload,
            latency_ms=1.0,
            provider="fake",
            provider_model_id="fake-model",
        )


class MalformedModel:
    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text="not json at all",
            latency_ms=1.0,
            provider="fake",
            provider_model_id="fake-model",
        )


@pytest.mark.asyncio
async def test_no_observations_returns_empty_read_without_calling_model() -> None:
    model = FakeModel({"themes": [], "gaps_vs_competitors": []})
    compiler = BrandPositionCompiler(model)

    result = await compiler.compile(1, "Acme", [])

    assert result.themes == []
    assert result.observations_considered == 0
    assert model.calls == []


@pytest.mark.asyncio
async def test_theme_with_valid_observation_url_is_kept() -> None:
    obs = _observation()
    model = FakeModel(
        {
            "themes": [
                {
                    "label": "AI-native",
                    "summary": "Acme is pushing AI-native search.",
                    "observation_urls": [obs.source_url],
                }
            ],
            "gaps_vs_competitors": [],
        }
    )
    compiler = BrandPositionCompiler(model)

    result = await compiler.compile(1, "Acme", [obs])

    assert len(result.themes) == 1
    assert result.themes[0].observation_urls == [obs.source_url]


@pytest.mark.asyncio
async def test_theme_with_unlisted_url_is_dropped() -> None:
    obs = _observation()
    model = FakeModel(
        {
            "themes": [
                {
                    "label": "Fabricated theme",
                    "summary": "Not actually grounded.",
                    "observation_urls": ["https://not-a-real-observation.example.com"],
                }
            ],
            "gaps_vs_competitors": [],
        }
    )
    compiler = BrandPositionCompiler(model)

    result = await compiler.compile(1, "Acme", [obs])

    assert result.themes == []


@pytest.mark.asyncio
async def test_theme_with_no_urls_is_dropped() -> None:
    obs = _observation()
    model = FakeModel(
        {
            "themes": [{"label": "No evidence", "summary": "...", "observation_urls": []}],
            "gaps_vs_competitors": [],
        }
    )
    compiler = BrandPositionCompiler(model)

    result = await compiler.compile(1, "Acme", [obs])

    assert result.themes == []


@pytest.mark.asyncio
async def test_malformed_output_raises_after_retry() -> None:
    obs = _observation()
    compiler = BrandPositionCompiler(MalformedModel())

    with pytest.raises(MalformedPositionOutput):
        await compiler.compile(1, "Acme", [obs])


@pytest.mark.asyncio
async def test_to_own_position_facts_adapter_output() -> None:
    obs = _observation()
    model = FakeModel(
        {
            "themes": [
                {
                    "label": "AI-native",
                    "summary": "Acme is pushing AI-native search.",
                    "observation_urls": [obs.source_url],
                }
            ],
            "gaps_vs_competitors": ["Acme has no public benchmark page, unlike its rivals."],
        }
    )
    compiler = BrandPositionCompiler(model)

    result = await compiler.compile(1, "Acme", [obs])
    facts = result.to_own_position_facts()

    assert len(facts) == 2
    assert facts[0].endswith(f"(source: {obs.source_url})")
    assert facts[1] == "Acme has no public benchmark page, unlike its rivals."
