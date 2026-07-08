"""Identity resolution: raw channel identity -> canonical CI-OS user.

Per docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md,
this is steps 3+ of the identity resolution flow -- adapters only resolve as
far as a channel-level identity (see ChannelAdapter.map_identity); this module
resolves that further to the canonical `users` row (schema.sql), via the
`channel_identities` join table (a user's per-channel handle, e.g. a Telegram
user id).

An unknown or unlinked channel identity never resolves to a user: an
access_request row is created for operator review and the caller must deny.
Storage access is via injected repository protocols only -- no direct DB
access here (tests use in-memory fakes).
"""

from __future__ import annotations

from typing import Optional, Protocol

from cios.platform.channels.types import NormalizedInboundMessage
from cios.platform.identity.types import (
    AccessRequest,
    ChannelIdentity,
    ChannelIdentityStatus,
    IdentityResolution,
    User,
    UserStatus,
)


class ChannelIdentityRepository(Protocol):
    def get_by_channel_user_id(
        self, tenant_id: int, channel: str, channel_user_id: str
    ) -> Optional[ChannelIdentity]: ...


class UserRepository(Protocol):
    def get(self, tenant_id: int, user_id: int) -> Optional[User]: ...


class AccessRequestRepository(Protocol):
    def create(self, access_request: AccessRequest) -> AccessRequest: ...


class IdentityResolver:
    """Resolves a NormalizedInboundMessage to a canonical user, tenant-scoped."""

    def __init__(
        self,
        channel_identities: ChannelIdentityRepository,
        users: UserRepository,
        access_requests: AccessRequestRepository,
    ) -> None:
        self._channel_identities = channel_identities
        self._users = users
        self._access_requests = access_requests

    def resolve(self, tenant_id: int, message: NormalizedInboundMessage) -> IdentityResolution:
        identity = self._channel_identities.get_by_channel_user_id(
            tenant_id=tenant_id,
            channel=message.channel.value,
            channel_user_id=message.channel_user_id,
        )

        if (
            identity is None
            or identity.status != ChannelIdentityStatus.LINKED
            or identity.user_id is None
        ):
            return self._deny_unknown(tenant_id, message, reason="unknown_or_unlinked_channel_identity")

        user = self._users.get(tenant_id=tenant_id, user_id=identity.user_id)
        if user is None or user.status != UserStatus.ACTIVE:
            return self._deny_unknown(tenant_id, message, reason="user_not_active")

        return IdentityResolution(resolved=True, user=user)

    def _deny_unknown(
        self, tenant_id: int, message: NormalizedInboundMessage, reason: str
    ) -> IdentityResolution:
        access_request = self._access_requests.create(
            AccessRequest(
                tenant_id=tenant_id,
                channel=message.channel.value,
                requested_identity=message.channel_user_id,
            )
        )
        return IdentityResolution(resolved=False, reason=reason, access_request=access_request)
