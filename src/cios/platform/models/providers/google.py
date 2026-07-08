"""Gemini provider adapter (generativelanguage.googleapis.com REST API).

Env: GEMINI_API_KEY. Model id is supplied by the caller/router — this module
declares only a documented fallback constant, never a hardcoded routing
default (routing config owns tier -> model_id mapping per
docs/planning/CI-OS-env-and-secrets-spec.md "one routing config file" rule).
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

import httpx

from ..provider import ModelProvider
from ..types import ModelRequest, ModelResponse, ProviderHealth, TokenUsage

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# Documented fallback only — routing config (config/model-routing.yaml)
# is the actual source of truth for which model id to use per tier.
FALLBACK_MODEL_ID = "gemini-flash-lite"

SUPPORTED_CAPABILITIES = {
    "needs_json_mode",
    "needs_long_context",
    "needs_vision",
}


class GoogleGeminiProvider(ModelProvider):
    name = "google"

    def __init__(
        self,
        model_id: str = FALLBACK_MODEL_ID,
        api_key: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 60.0,
    ) -> None:
        self.model_id = model_id
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    def _build_payload(self, request: ModelRequest) -> dict[str, Any]:
        contents: list[dict[str, Any]] = []
        if request.messages:
            for msg in request.messages:
                role = "model" if msg.role == "assistant" else "user"
                contents.append({"role": role, "parts": [{"text": msg.content}]})
        else:
            contents.append({"role": "user", "parts": [{"text": request.prompt}]})

        generation_config: dict[str, Any] = {}
        if request.max_tokens is not None:
            generation_config["maxOutputTokens"] = request.max_tokens
        if request.json_schema is not None:
            generation_config["responseMimeType"] = "application/json"
            generation_config["responseSchema"] = request.json_schema

        payload: dict[str, Any] = {"contents": contents}
        if generation_config:
            payload["generationConfig"] = generation_config
        return payload

    def _url(self, action: str = "generateContent") -> str:
        return f"{GEMINI_API_BASE}/models/{self.model_id}:{action}"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        payload = self._build_payload(request)
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self.api_key,
        }
        start = time.perf_counter()
        resp = await self._client.post(self._url(), json=payload, headers=headers)
        resp.raise_for_status()
        latency_ms = (time.perf_counter() - start) * 1000
        data = resp.json()

        text = ""
        parsed_json = None
        try:
            candidate = data["candidates"][0]
            parts = candidate["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts)
        except (KeyError, IndexError):
            text = ""

        if request.json_schema is not None and text:
            import json

            try:
                parsed_json = json.loads(text)
            except ValueError:
                parsed_json = None

        usage_meta = data.get("usageMetadata", {})
        usage = TokenUsage(
            prompt_tokens=usage_meta.get("promptTokenCount", 0),
            completion_tokens=usage_meta.get("candidatesTokenCount", 0),
            total_tokens=usage_meta.get("totalTokenCount", 0),
        )

        return ModelResponse(
            text=text,
            parsed_json=parsed_json,
            usage=usage,
            latency_ms=latency_ms,
            provider=self.name,
            provider_model_id=self.model_id,
            raw=data,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        response = await self.generate(request)
        yield response.text

    def supports(self, capability: str) -> bool:
        return capability in SUPPORTED_CAPABILITIES

    def estimate_cost(self, request: ModelRequest) -> float:
        # Rough placeholder estimate; real cost table lives in routing config
        # / a future pricing module. Charged in cents per ~1k chars of prompt.
        prompt_len = len(request.prompt or "") + sum(
            len(m.content) for m in (request.messages or [])
        )
        return max(0.01, prompt_len / 1000 * 0.01)

    async def health_check(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            headers = {"x-goog-api-key": self.api_key}
            resp = await self._client.get(
                f"{GEMINI_API_BASE}/models/{self.model_id}", headers=headers
            )
            latency_ms = (time.perf_counter() - start) * 1000
            healthy = resp.status_code == 200
            return ProviderHealth(
                healthy=healthy,
                provider=self.name,
                checked_at=datetime.now(timezone.utc),
                detail=None if healthy else f"status={resp.status_code}",
                latency_ms=latency_ms,
            )
        except httpx.HTTPError as exc:
            latency_ms = (time.perf_counter() - start) * 1000
            return ProviderHealth(
                healthy=False,
                provider=self.name,
                checked_at=datetime.now(timezone.utc),
                detail=str(exc),
                latency_ms=latency_ms,
            )
