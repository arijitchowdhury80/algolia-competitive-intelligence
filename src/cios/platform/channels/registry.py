"""Adapter registry keyed by channel name.

Adapters register themselves (or get registered at app bootstrap) here so
callers can look one up by channel string without importing every adapter
module directly.
"""

from __future__ import annotations

from typing import Any


class UnknownChannelError(KeyError):
    """Raised by get_adapter() when no adapter is registered for a channel."""


_REGISTRY: dict[str, Any] = {}


def register_adapter(channel: str, adapter: Any) -> None:
    """Register an adapter instance under a channel name."""
    _REGISTRY[channel] = adapter


def get_adapter(channel: str) -> Any:
    """Look up a registered adapter by channel name.

    Raises UnknownChannelError with a clear message if nothing is registered.
    """
    try:
        return _REGISTRY[channel]
    except KeyError as exc:
        known = ", ".join(sorted(_REGISTRY)) or "(none registered)"
        raise UnknownChannelError(
            f"No adapter registered for channel {channel!r}. Known channels: {known}"
        ) from exc


def unregister_adapter(channel: str) -> None:
    """Remove a registered adapter, if present. Mainly useful for tests."""
    _REGISTRY.pop(channel, None)
