from __future__ import annotations

from datetime import datetime, timezone
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from cios.platform.models.provider import ModelProvider
from cios.platform.models.providers.claude_cli import ClaudeCliShimProvider
from cios.platform.models.providers.google import GoogleGeminiProvider
from cios.platform.models.types import ChatMessage, ModelRequest, ModelResponse, ProviderHealth


# ---------------------------------------------------------------------------
# types.py
# ---------------------------------------------------------------------------


def test_model_request_accepts_prompt_only():
    req = ModelRequest(task_profile="synth", prompt="hello")
    assert req.prompt == "hello"
    assert req.messages is None
    assert req.capability_needs == []


def test_model_request_accepts_messages_only():
    req = ModelRequest(
        task_profile="synth",
        messages=[ChatMessage(role="user", content="hi")],
    )
    assert req.messages[0].content == "hi"


def test_model_request_requires_prompt_or_messages():
    with pytest.raises(ValueError):
        ModelRequest(task_profile="synth")


def test_model_response_defaults():
    resp = ModelResponse(
        text="hi",
        latency_ms=1.0,
        provider="google",
        provider_model_id="gemini-flash-lite",
    )
    assert resp.parsed_json is None
    assert resp.usage.total_tokens == 0
    assert resp.raw is None


def test_provider_health_construction():
    health = ProviderHealth(
        healthy=True, provider="google", checked_at=datetime.now(timezone.utc)
    )
    assert health.healthy is True


# ---------------------------------------------------------------------------
# provider.py ABC
# ---------------------------------------------------------------------------


def test_model_provider_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        ModelProvider()


class _MinimalProvider(ModelProvider):
    name = "minimal"

    async def generate(self, request: ModelRequest) -> ModelResponse:
        return ModelResponse(
            text="ok", latency_ms=0.0, provider=self.name, provider_model_id="m1"
        )

    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        yield "ok"

    def supports(self, capability: str) -> bool:
        return True

    def estimate_cost(self, request: ModelRequest) -> float:
        return 0.0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(healthy=True, provider=self.name, checked_at=datetime.now(timezone.utc))


@pytest.mark.asyncio
async def test_minimal_concrete_subclass_works():
    provider = _MinimalProvider()
    resp = await provider.generate(ModelRequest(task_profile="x", prompt="p"))
    assert resp.text == "ok"
    health = await provider.health_check()
    assert health.healthy is True


# ---------------------------------------------------------------------------
# providers/google.py
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_google_provider_builds_request_and_parses_response():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": "hello world"}]}}],
        "usageMetadata": {
            "promptTokenCount": 5,
            "candidatesTokenCount": 2,
            "totalTokenCount": 7,
        },
    }

    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    provider = GoogleGeminiProvider(
        model_id="gemini-flash-lite", api_key="test-key", client=mock_client
    )

    req = ModelRequest(task_profile="synth", prompt="say hi", max_tokens=100)
    resp = await provider.generate(req)

    call_args = mock_client.post.call_args
    url = call_args.args[0] if call_args.args else call_args.kwargs["url"]
    assert "gemini-flash-lite:generateContent" in url
    assert "generativelanguage.googleapis.com" in url

    payload = call_args.kwargs["json"]
    assert payload["contents"][0]["parts"][0]["text"] == "say hi"
    assert payload["generationConfig"]["maxOutputTokens"] == 100

    headers = call_args.kwargs["headers"]
    assert headers["x-goog-api-key"] == "test-key"

    assert resp.text == "hello world"
    assert resp.provider == "google"
    assert resp.provider_model_id == "gemini-flash-lite"
    assert resp.usage.total_tokens == 7


@pytest.mark.asyncio
async def test_google_provider_json_mode_sets_response_mime_type():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}],
        "usageMetadata": {},
    }
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=mock_response)

    provider = GoogleGeminiProvider(client=mock_client, api_key="k")
    req = ModelRequest(task_profile="synth", prompt="x", json_schema={"type": "object"})
    resp = await provider.generate(req)

    payload = mock_client.post.call_args.kwargs["json"]
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert resp.parsed_json == {"a": 1}


def test_google_provider_supports_capabilities():
    provider = GoogleGeminiProvider(api_key="k")
    assert provider.supports("needs_json_mode") is True
    assert provider.supports("needs_tool_use") is False


# ---------------------------------------------------------------------------
# providers/claude_cli.py
# ---------------------------------------------------------------------------


def _resp(status_code: int, json_body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "err", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status = MagicMock()
    return resp


@pytest.mark.asyncio
async def test_claude_cli_retries_on_429_then_succeeds():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    responses = [
        _resp(429, {}),
        _resp(200, {"text": "hello from claude", "usage": {"total_tokens": 3}}),
    ]
    mock_client.post = AsyncMock(side_effect=responses)

    sleep_calls = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    provider = ClaudeCliShimProvider(
        model_alias="sonnet", base_url="http://127.0.0.1:8663",
        client=mock_client, sleep_fn=fake_sleep,
    )

    req = ModelRequest(task_profile="synth", prompt="hi")
    resp = await provider.generate(req)

    assert mock_client.post.call_count == 2
    assert len(sleep_calls) == 1
    assert resp.text == "hello from claude"
    assert resp.provider == "anthropic-cli"


@pytest.mark.asyncio
async def test_claude_cli_exhausts_retries_and_raises():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=_resp(503, {}))

    async def fake_sleep(seconds: float) -> None:
        return None

    provider = ClaudeCliShimProvider(client=mock_client, sleep_fn=fake_sleep)
    req = ModelRequest(task_profile="synth", prompt="hi")

    with pytest.raises(Exception):
        await provider.generate(req)

    assert mock_client.post.call_count == 3


@pytest.mark.asyncio
async def test_claude_cli_can_disable_retries_for_cron_bounded_runs():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.post = AsyncMock(return_value=_resp(503, {}))

    async def fake_sleep(seconds: float) -> None:
        raise AssertionError("bounded runs must not back off and retry")

    provider = ClaudeCliShimProvider(client=mock_client, sleep_fn=fake_sleep, max_attempts=1)
    req = ModelRequest(task_profile="synth", prompt="hi")

    with pytest.raises(Exception):
        await provider.generate(req)

    assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_claude_cli_health_check_calls_health_endpoint():
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    health_resp = MagicMock()
    health_resp.status_code = 200
    health_resp.json.return_value = {"healthy": True, "detail": None}
    mock_client.get = AsyncMock(return_value=health_resp)

    provider = ClaudeCliShimProvider(client=mock_client)
    health = await provider.health_check()

    assert health.healthy is True
    assert health.provider == "anthropic-cli"
    mock_client.get.assert_called_once_with("http://127.0.0.1:8663/health")
