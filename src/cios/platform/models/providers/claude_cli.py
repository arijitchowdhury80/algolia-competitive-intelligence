"""Claude provider adapter — talks to the localhost `claude -p` shim.

The shim itself (deploy/claude-shim/shim.py) is a separate deployable that
runs ON THE HOST at 127.0.0.1:8663 and wraps the `claude` CLI. This module
is the client side used by container code to call that shim over HTTP.

Env: CIOS_CLAUDE_SHIM_URL (default http://127.0.0.1:8663).
"""

from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Callable, Optional

import httpx

from ..provider import ModelProvider
from ..types import ModelRequest, ModelResponse, ProviderHealth, TokenUsage

DEFAULT_SHIM_URL = "http://127.0.0.1:8663"

SUPPORTED_CAPABILITIES = {
    "needs_json_mode",
    "needs_long_context",
    "needs_tool_use",
}

RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class ClaudeCliShimProvider(ModelProvider):
    name = "anthropic-cli"

    def __init__(
        self,
        model_alias: str = "sonnet",
        base_url: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
        timeout_s: float = 60.0,
        max_attempts: Optional[int] = None,
        backoff_base: float = 0.5,
        sleep_fn: Optional[Callable[[float], Any]] = None,
    ) -> None:
        self.model_alias = model_alias
        self.base_url = base_url or os.environ.get(
            "CIOS_CLAUDE_SHIM_URL", DEFAULT_SHIM_URL
        )
        self._client = client or httpx.AsyncClient(timeout=timeout_s)
        self.timeout_s = timeout_s
        self.max_attempts = max_attempts or int(os.environ.get("CIOS_CLAUDE_MAX_ATTEMPTS", MAX_ATTEMPTS))
        self.backoff_base = backoff_base
        self._sleep_fn = sleep_fn or asyncio.sleep

    @property
    def model_id(self) -> str:
        return self.model_alias

    async def _post_with_retry(self, path: str, payload: dict[str, Any]) -> httpx.Response:
        last_exc: Optional[Exception] = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                resp = await self._client.post(f"{self.base_url}{path}", json=payload)
            except httpx.HTTPError as exc:
                last_exc = exc
                resp = None

            if resp is not None and resp.status_code not in RETRYABLE_STATUS_CODES:
                return resp

            last_exc = last_exc or RuntimeError(
                f"retryable status {resp.status_code if resp is not None else '?'}"
            )
            if attempt < self.max_attempts:
                await self._sleep_fn(self.backoff_base * (2 ** (attempt - 1)))

        assert last_exc is not None
        raise last_exc

    async def generate(self, request: ModelRequest) -> ModelResponse:
        prompt = request.prompt
        if prompt is None and request.messages:
            prompt = "\n".join(f"{m.role}: {m.content}" for m in request.messages)

        payload = {
            "prompt": prompt,
            "model_alias": self.model_alias,
            "json_mode": request.json_schema is not None,
            "timeout_s": int(self.timeout_s),
        }

        start = time.perf_counter()
        resp = await self._post_with_retry("/generate", payload)
        resp.raise_for_status()
        latency_ms = (time.perf_counter() - start) * 1000
        data = resp.json()

        parsed_json = data.get("parsed_json")
        usage_data = data.get("usage", {}) or {}
        usage = TokenUsage(
            prompt_tokens=usage_data.get("prompt_tokens", 0),
            completion_tokens=usage_data.get("completion_tokens", 0),
            total_tokens=usage_data.get("total_tokens", 0),
        )

        return ModelResponse(
            text=data.get("text", ""),
            parsed_json=parsed_json,
            usage=usage,
            latency_ms=latency_ms,
            provider=self.name,
            provider_model_id=self.model_alias,
            raw=data,
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        response = await self.generate(request)
        yield response.text

    def supports(self, capability: str) -> bool:
        return capability in SUPPORTED_CAPABILITIES

    def estimate_cost(self, request: ModelRequest) -> float:
        # Claude runs under a shared Max subscription via the shim, not
        # metered per-token here; return 0.0 as a placeholder estimate.
        return 0.0

    async def health_check(self) -> ProviderHealth:
        start = time.perf_counter()
        try:
            resp = await self._client.get(f"{self.base_url}/health")
            latency_ms = (time.perf_counter() - start) * 1000
            data = resp.json() if resp.status_code == 200 else {}
            healthy = bool(data.get("healthy", False)) and resp.status_code == 200
            return ProviderHealth(
                healthy=healthy,
                provider=self.name,
                checked_at=datetime.now(timezone.utc),
                detail=data.get("detail"),
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
