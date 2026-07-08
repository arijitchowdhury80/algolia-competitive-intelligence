"""Shared fakes for brain tests: an in-memory BrainModel that returns canned
responses in sequence (mimicking a router-backed provider without any network
or DB). Matches ModelProvider.generate's async shape."""

from __future__ import annotations

import json
from typing import Any, Optional

from cios.platform.models.types import ModelRequest, ModelResponse


class FakeModel:
    """Returns queued responses in order. Each queued item is either a dict
    (emitted as parsed_json + serialized text) or a raw string (emitted as
    text only, e.g. to simulate malformed output)."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[ModelRequest] = []

    async def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        item = self._responses.pop(0) if self._responses else {"signals": []}
        if isinstance(item, dict):
            return ModelResponse(
                text=json.dumps(item),
                parsed_json=item,
                latency_ms=1.0,
                provider="fake",
                provider_model_id="fake-opus",
            )
        # raw string: malformed / non-JSON path (no parsed_json).
        return ModelResponse(
            text=str(item),
            parsed_json=None,
            latency_ms=1.0,
            provider="fake",
            provider_model_id="fake-opus",
        )


def signal_payload(
    *,
    evidence_urls: Optional[list[str]] = None,
    materiality_score: float = 0.8,
    owner: str = "PMM",
    recommended_action: str = "Brief the field on the pricing shift.",
    signal_type: str = "pricing change",
    headline: str = "Competitor cuts entry price 20%",
) -> dict[str, Any]:
    return {
        "signal_type": signal_type,
        "headline": headline,
        "what_changed": "Entry tier dropped from 500 to 400.",
        "why_it_matters": "Undercuts our mid-market motion.",
        "implication": "Expect price objections in Q3 deals.",
        "recommended_action": recommended_action,
        "owner": owner,
        "materiality_score": materiality_score,
        "confidence": 0.7,
        "evidence_urls": evidence_urls if evidence_urls is not None else ["https://rival.com/pricing"],
    }
