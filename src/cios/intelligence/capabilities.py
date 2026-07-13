"""Capability normalization for Argus product-market intelligence.

Different evidence planes rarely use the same words. Scout may see
"AI Shopping Agent", market conversation may say "commerce AI agent", and
Looker may carry "agentic product discovery". This module defines the
deterministic vocabulary bridge before the synthesizer decides whether product,
conversation, and demand actually align.
"""

from __future__ import annotations

import re
from typing import Any


_VENDOR_PREFIXES = {
    "algolia",
    "constructor",
    "coveo",
    "elastic",
    "bloomreach",
    "doofinder",
}

_SUPPORT_SUFFIXES = {
    "support",
    "resources",
    "resource",
    "documentation",
    "docs",
}

_NON_FEATURE_KEYS = {
    "algolia academy",
    "academy",
    "content narrative",
    "customer proof",
    "new content narrative",
    "new customer proof",
    "product position",
    "product positioning",
}


def _basic_key(value: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", str(value or "").strip().lower())
    return re.sub(r"\s+", " ", text).strip()


def _strip_vendor_and_support_scaffolding(key: str) -> str:
    tokens = key.split()
    while tokens and tokens[0] in _VENDOR_PREFIXES:
        tokens.pop(0)
    while tokens and tokens[-1] in _SUPPORT_SUFFIXES:
        tokens.pop()
    if "ai" in tokens and len(tokens) > 1:
        tokens = [token for token in tokens if token != "ai"]
    if "mcp" in tokens and "model" in tokens and "context" in tokens and "protocol" in tokens:
        tokens = [token for token in tokens if token != "mcp"]
    return " ".join(tokens)


def capability_key(value: str) -> str:
    """Return the canonical comparison key for a product-market capability."""

    key = _strip_vendor_and_support_scaffolding(_basic_key(value))
    if not key:
        return ""
    if key in _NON_FEATURE_KEYS:
        return ""

    tokens = set(key.split())
    has_agent = bool(tokens & {"agent", "agents", "assistant", "assistants"})
    has_commerce_context = bool(tokens & {"commerce", "shopping", "shopper", "shoppers", "ecommerce"})
    has_product_discovery = {"product", "discovery"}.issubset(tokens)

    if (
        ("shopping" in tokens and has_agent)
        or ("commerce" in tokens and has_agent)
        or ("conversational" in tokens and has_commerce_context)
        or ("agentic" in tokens and has_product_discovery)
        or ("natural" in tokens and "language" in tokens and has_product_discovery)
    ):
        return "shopping agent"

    return key


def demand_capability_key(topic: Any, metadata: Any = None, plan_context: Any = None) -> str:
    """Return the capability key for a demand row.

    Demand imports can carry a human analytics topic that differs from the
    Argus collection-plan capability. The explicit plan key wins when present;
    otherwise the topic is normalized like any other capability label.
    """

    for context, key_name in (
        (metadata, "argus_capability_key"),
        (plan_context, "capability_key"),
    ):
        if isinstance(context, dict):
            explicit = str(context.get(key_name) or "").strip()
            if explicit:
                return capability_key(explicit)
    return capability_key(str(topic or ""))


__all__ = ["capability_key", "demand_capability_key"]
