#!/usr/bin/env python3
"""Provider availability preflight for production CI cron wrappers."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation


def money(value: object) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def check_gemini() -> int:
    api_key = (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or "").strip()
    if not api_key:
        print("CI RUN BLOCKED - Gemini API key is missing.")
        print("Effect: CI cannot run model-backed synthesis or deliver trusted intelligence.")
        print("Action: restore GEMINI_API_KEY or GOOGLE_API_KEY in the Hermes runtime environment, then rerun the job.")
        return 75

    model = os.environ.get("CI_GEMINI_PREFLIGHT_MODEL") or os.environ.get("COMPETITIVE_RESEARCH_MODEL") or "gemini-2.5-flash"
    payload = {
        "contents": [{"parts": [{"text": "Reply with OK."}]}],
        "generationConfig": {"temperature": 0, "maxOutputTokens": 8},
    }
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"CI RUN BLOCKED - Gemini preflight failed with HTTP {exc.code}.")
        print("Effect: CI cannot confirm model-provider availability.")
        print("Action: check Gemini API billing/key/model access and rerun the job.")
        return 75
    except Exception as exc:
        print("CI RUN BLOCKED - Gemini preflight failed.")
        print(f"Reason: {type(exc).__name__}: {str(exc)[:240]}")
        print("Effect: CI cannot confirm model-provider availability.")
        print("Action: check network/provider status and rerun the job.")
        return 75
    return 0


def check_openrouter() -> int:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print("CI RUN BLOCKED - OpenRouter API key is missing.")
        print("Effect: CI cannot run model-backed synthesis or deliver trusted intelligence.")
        print("Action: restore OPENROUTER_API_KEY in the Hermes runtime environment, then rerun the job.")
        return 75

    min_remaining = money(os.environ.get("CI_MIN_OPENROUTER_CREDITS", "1.00"))
    request = urllib.request.Request(
        "https://openrouter.ai/api/v1/credits",
        headers={"Authorization": "Bearer " + api_key},
    )

    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        print(f"CI RUN BLOCKED - OpenRouter credit check failed with HTTP {exc.code}.")
        print("Effect: CI cannot confirm model-provider availability.")
        print("Action: check OpenRouter billing/API status and rerun the job.")
        return 75
    except Exception as exc:
        print("CI RUN BLOCKED - OpenRouter credit check failed.")
        print(f"Reason: {type(exc).__name__}: {str(exc)[:240]}")
        print("Effect: CI cannot confirm model-provider availability.")
        print("Action: check network/provider status and rerun the job.")
        return 75

    data = payload.get("data") or payload
    total = money(data.get("total_credits"))
    used = money(data.get("total_usage"))
    remaining = total - used

    if remaining < min_remaining:
        print("CI RUN BLOCKED - OpenRouter credits are below the production floor.")
        print(f"Credits: total=${total:.4f}, used=${used:.4f}, remaining=${remaining:.4f}, required>=${min_remaining:.4f}")
        print("Effect: daily/weekly CI will not publish a trusted report or update the dashboard.")
        print("Action: add OpenRouter credits, then rerun the CI cron job.")
        return 75
    return 0


def main() -> int:
    if os.environ.get("CI_SKIP_PROVIDER_PREFLIGHT") == "1":
        print("CI provider preflight skipped by CI_SKIP_PROVIDER_PREFLIGHT=1.")
        return 0

    provider = os.environ.get("CI_MODEL_PROVIDER", "gemini").strip().lower()
    if provider in {"gemini", "google", "google-gemini", "google-ai-studio"}:
        return check_gemini()
    if provider == "openrouter":
        return check_openrouter()

    print(f"CI RUN BLOCKED - unsupported CI_MODEL_PROVIDER={provider or 'unknown'}.")
    print("Effect: CI cannot confirm model-provider availability.")
    print("Action: set CI_MODEL_PROVIDER to gemini or openrouter and rerun the job.")
    return 75


if __name__ == "__main__":
    sys.exit(main())
