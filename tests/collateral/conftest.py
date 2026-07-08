"""Shared fixtures for collateral tests: a fake BrainModel (mirrors
tests/brain/conftest.py's FakeModel) and factory helpers for a grounded
Prescription + BrandTokens."""

from __future__ import annotations

import json
from typing import Any

from cios.platform.models.types import ModelRequest, ModelResponse
from cios.prescribe.types import Effort, Grounding, Prescription, Team, UrgencyWindow


class FakeModel:
    """Returns queued responses in order. Each queued item is either a dict
    (emitted as parsed_json + serialized text) or a raw string (emitted as
    text only, to simulate malformed output)."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        item = self._responses.pop(0) if self._responses else {}
        if isinstance(item, dict):
            return ModelResponse(
                text=json.dumps(item),
                parsed_json=item,
                latency_ms=1.0,
                provider="fake",
                provider_model_id="fake-opus",
            )
        return ModelResponse(
            text=str(item),
            parsed_json=None,
            latency_ms=1.0,
            provider="fake",
            provider_model_id="fake-opus",
        )


def make_prescription(
    *,
    tenant_id: int = 1,
    evidence_urls: list[str] | None = None,
    title: str = "Undercut rival's entry-tier pricing push",
) -> Prescription:
    urls = evidence_urls if evidence_urls is not None else ["https://rival.com/pricing"]
    return Prescription(
        tenant_id=tenant_id,
        title=title,
        play=[
            "Publish a comparison landing page targeting the pricing gap.",
            "Brief the field on the new positioning.",
        ],
        team=Team.MARKETING,
        urgency_window=UrgencyWindow.THIS_WEEK,
        grounding=Grounding(
            signal_evidence_urls=urls,
            evidence_urls=urls,
        ),
        expected_effect="Recover deals lost to the perception of being overpriced.",
        effort=Effort.M,
        materiality_score=0.8,
    )


def landing_content_payload(
    *,
    proof_points: list[dict[str, Any]] | None = None,
    hero_headline: str = "Priced fairly. Built to outlast the discount wars.",
) -> dict[str, Any]:
    return {
        "hero_headline": hero_headline,
        "hero_subheadline": "See why teams switch when the discount period ends.",
        "proof_points": proof_points
        if proof_points is not None
        else [
            {
                "claim": "Rival cut its entry tier by 20% this quarter.",
                "evidence_url": "https://rival.com/pricing",
            },
            {
                "claim": "Our platform holds steady pricing with no lock-in.",
                "evidence_url": "",
            },
        ],
        "cta_label": "See the comparison",
        "cta_subtext": "No credit card required.",
    }
