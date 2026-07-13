"""cios-claude-shim — standalone FastAPI wrapper around the `claude` CLI.

This is a SEPARATE deployable. It is not imported by src/cios router code;
container code talks to it over localhost HTTP
(CIOS_CLAUDE_SHIM_URL, see src/cios/platform/models/providers/claude_cli.py).

Runs ON THE VPS HOST at 127.0.0.1:8663 only — never bind 0.0.0.0/public.
See README.md in this directory for systemd install instructions.
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import time
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="cios-claude-shim")

MODEL_ALIASES = {
    "haiku": "claude-haiku-4-5",
    "sonnet": "claude-sonnet-4-5",
    "opus": "claude-opus-4-5",
}

AUTH_FAILURE_SUBSTRINGS = (
    "not logged in",
    "authentication",
    "auth failed",
    "unauthorized",
)

_HEALTH_CACHE_TTL_S = 5 * 60
_health_cache: dict[str, Any] = {"checked_at": 0.0, "result": None}


class GenerateRequest(BaseModel):
    prompt: str
    model_alias: str = "sonnet"
    json_mode: bool = False
    timeout_s: int = 60


def _is_auth_failure(text: str) -> bool:
    lowered = text.lower()
    return any(sub in lowered for sub in AUTH_FAILURE_SUBSTRINGS)


async def _run_claude(prompt: str, model_alias: str, timeout_s: int) -> tuple[int, str, str]:
    prompt = prompt.replace("\x00", "")
    model_id = MODEL_ALIASES.get(model_alias)
    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model_id:
        cmd += ["--model", model_id]

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        stdout_b, stderr_b = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        await _kill_process_group(proc)
        raise HTTPException(status_code=504, detail="claude CLI timed out")
    except asyncio.CancelledError:
        await _kill_process_group(proc)
        raise

    return proc.returncode or 0, stdout_b.decode(errors="replace"), stderr_b.decode(errors="replace")


async def _kill_process_group(proc: asyncio.subprocess.Process) -> None:
    pid = getattr(proc, "pid", None)
    if pid:
        try:
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            proc.kill()
    else:
        proc.kill()

    try:
        await asyncio.wait_for(proc.wait(), timeout=5)
        return
    except asyncio.TimeoutError:
        pass

    if pid:
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            return
        except Exception:
            proc.kill()
    else:
        proc.kill()
    await proc.wait()


@app.post("/generate")
async def generate(req: GenerateRequest) -> dict[str, Any]:
    returncode, stdout, stderr = await _run_claude(req.prompt, req.model_alias, req.timeout_s)

    combined = f"{stdout}\n{stderr}"
    if _is_auth_failure(combined):
        raise HTTPException(
            status_code=503,
            detail="claude CLI is not authenticated (session expired or CLAUDE_CODE_OAUTH_TOKEN missing/invalid)",
        )

    if returncode != 0:
        raise HTTPException(status_code=502, detail=f"claude CLI failed: {stderr.strip()[:500]}")

    text = stdout
    parsed_json: Optional[dict[str, Any]] = None
    try:
        envelope = json.loads(stdout)
        parsed_json = envelope
        text = envelope.get("result") or envelope.get("text") or stdout
    except ValueError:
        pass

    return {
        "text": text,
        "parsed_json": parsed_json if req.json_mode else None,
        "usage": {},
        "model_alias": req.model_alias,
    }


@app.get("/health")
async def health() -> dict[str, Any]:
    now = time.time()
    cached = _health_cache["result"]
    if cached is not None and (now - _health_cache["checked_at"]) < _HEALTH_CACHE_TTL_S:
        return cached

    try:
        returncode, stdout, stderr = await _run_claude("ping", "haiku", timeout_s=20)
        combined = f"{stdout}\n{stderr}"
        if _is_auth_failure(combined):
            result = {"healthy": False, "checked_at": now, "detail": "not logged in"}
        elif returncode != 0:
            result = {"healthy": False, "checked_at": now, "detail": stderr.strip()[:300]}
        else:
            result = {"healthy": True, "checked_at": now, "detail": None}
    except HTTPException as exc:
        result = {"healthy": False, "checked_at": now, "detail": str(exc.detail)}

    _health_cache["result"] = result
    _health_cache["checked_at"] = now
    return result
