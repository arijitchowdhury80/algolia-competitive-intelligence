"""ModelProvider abstract base class.

Provider-agnostic contract implemented by every concrete adapter
(providers/google.py, providers/claude_cli.py, ...). Skills and the router
depend only on this interface — never a concrete provider class.
"""

from __future__ import annotations

import abc
from typing import AsyncIterator

from .types import ModelRequest, ModelResponse, ProviderHealth


class ModelProvider(abc.ABC):
    """Abstract base for all model providers."""

    name: str

    @abc.abstractmethod
    async def generate(self, request: ModelRequest) -> ModelResponse:
        """Generate a full response for the given request."""
        raise NotImplementedError

    @abc.abstractmethod
    async def stream(self, request: ModelRequest) -> AsyncIterator[str]:
        """Stream response text chunks for the given request."""
        raise NotImplementedError
        yield ""  # pragma: no cover - makes this an async generator signature

    @abc.abstractmethod
    def supports(self, capability: str) -> bool:
        """Whether this provider supports the given capability need."""
        raise NotImplementedError

    @abc.abstractmethod
    def estimate_cost(self, request: ModelRequest) -> float:
        """Estimate the cost of servicing this request, in cents."""
        raise NotImplementedError

    @abc.abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Check whether the provider is currently healthy/reachable."""
        raise NotImplementedError
