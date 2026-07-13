from __future__ import annotations

import importlib
import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

SHIM_DIR = Path(__file__).resolve().parents[2] / "deploy" / "claude-shim"
sys.path.insert(0, str(SHIM_DIR))

import shim as shim_module  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_health_cache():
    shim_module._health_cache["result"] = None
    shim_module._health_cache["checked_at"] = 0.0
    yield
    shim_module._health_cache["result"] = None
    shim_module._health_cache["checked_at"] = 0.0


async def _client():
    transport = ASGITransport(app=shim_module.app)
    return AsyncClient(transport=transport, base_url="http://test")


def _mock_proc(stdout: bytes, stderr: bytes, returncode: int = 0):
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    proc.pid = None
    proc.kill = MagicMock()
    proc.wait = AsyncMock(return_value=None)
    return proc


@pytest.mark.asyncio
async def test_generate_happy_path():
    proc = _mock_proc(b'{"result": "hello from claude"}', b"", 0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        async with await _client() as client:
            resp = await client.post(
                "/generate",
                json={"prompt": "hi", "model_alias": "sonnet", "json_mode": False},
            )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == "hello from claude"


@pytest.mark.asyncio
async def test_generate_strips_embedded_nulls_before_launching_claude():
    proc = _mock_proc(b'{"result": "clean"}', b"", 0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        async with await _client() as client:
            resp = await client.post(
                "/generate",
                json={"prompt": "bad\x00prompt", "model_alias": "sonnet", "json_mode": False},
            )

    assert resp.status_code == 200
    args = mock_exec.call_args.args
    assert "badprompt" in args
    assert all("\x00" not in str(arg) for arg in args)


@pytest.mark.asyncio
async def test_generate_not_logged_in_returns_503():
    proc = _mock_proc(b"", b"Error: not logged in. Run `claude login`.", 1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        async with await _client() as client:
            resp = await client.post(
                "/generate",
                json={"prompt": "hi", "model_alias": "sonnet"},
            )
    assert resp.status_code == 503
    assert "not logged in" in resp.json()["detail"].lower() or "authenticated" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_timeout_kills_claude_process():
    proc = _mock_proc(b"", b"", 0)
    proc.communicate = AsyncMock(side_effect=asyncio.TimeoutError)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        async with await _client() as client:
            resp = await client.post(
                "/generate",
                json={"prompt": "hi", "model_alias": "sonnet", "timeout_s": 1},
            )

    assert resp.status_code == 504
    proc.kill.assert_called_once()
    assert proc.wait.await_count == 1


@pytest.mark.asyncio
async def test_cancelled_generate_kills_claude_process():
    proc = _mock_proc(b"", b"", 0)

    async def never_finishes():
        await asyncio.sleep(999)
        return b"", b""

    proc.communicate = AsyncMock(side_effect=never_finishes)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        task = asyncio.create_task(shim_module._run_claude("hi", "sonnet", timeout_s=60))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    proc.kill.assert_called_once()
    assert proc.wait.await_count == 1


@pytest.mark.asyncio
async def test_health_returns_healthy_true():
    proc = _mock_proc(b'{"result": "pong"}', b"", 0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        async with await _client() as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["healthy"] is True
        assert mock_exec.call_count == 1


@pytest.mark.asyncio
async def test_health_returns_healthy_false_on_failure():
    proc = _mock_proc(b"", b"not logged in", 1)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        async with await _client() as client:
            resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["healthy"] is False


@pytest.mark.asyncio
async def test_health_caches_result_within_5_minutes():
    proc = _mock_proc(b'{"result": "pong"}', b"", 0)
    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=proc)) as mock_exec:
        async with await _client() as client:
            resp1 = await client.get("/health")
            resp2 = await client.get("/health")
        assert resp1.json() == resp2.json()
        assert mock_exec.call_count == 1
