"""Shared fakes for horizon tests: an in-memory BrainModel, matching the
convention in tests/brain/conftest.py exactly (no network/DB)."""

from __future__ import annotations

import json
from typing import Any

from cios.platform.models.types import ModelRequest, ModelResponse


class FakeModel:
    """Returns queued responses in order. Each queued item is either a dict
    (emitted as parsed_json + serialized text) or a raw string (malformed
    output path)."""

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
