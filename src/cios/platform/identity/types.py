"""Shared data types for the CI-OS identity/ACL layer.

See docs/planning/CI-OS-channels-identity-acl-and-model-provider-architecture.md
for the source spec and src/cios/db/schema.sql (tenants, users, user_identities,
roles, permissions, role_permissions, user_role_assignments, groups,
group_role_mappings, audit_events, access_requests) for the tables these
types mirror.

Note: channel-to-user resolution uses the `channel_identities` table (a
user's per-channel handle, e.g. a Telegram user id), not `user_identities`
(SSO/OIDC/SAML subjects). `ChannelIdentity` below models the former.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class UserStatus(str, Enum):
    INVITED = "invited"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDED = "offboarded"


class ChannelIdentityStatus(str, Enum):
    PENDING = "pending"
    LINKED = "linked"
    BLOCKED = "blocked"
    UNLINKED = "unlinked"


class AccessRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class User(BaseModel):
    """Canonical CI-OS identity within a tenant (schema: users)."""

    id: int
    tenant_id: int
    email: str
    display_name: Optional[str] = None
    status: UserStatus = UserStatus.ACTIVE


class ChannelIdentity(BaseModel):
    """A user's per-channel handle (schema: channel_identities).

    `user_id` is None until an operator links the channel handle to a
    canonical user; `status` gates whether the link may be used.
    """

    id: Optional[int] = None
    tenant_id: int
    user_id: Optional[int] = None
    channel: str
    channel_user_id: str
    status: ChannelIdentityStatus = ChannelIdentityStatus.PENDING


class Role(BaseModel):
    """Tenant-scoped named bundle of permissions (schema: roles)."""

    id: int
    tenant_id: int
    name: str
    description: Optional[str] = None


class Permission(BaseModel):
    """Global capability catalog entry (schema: permissions)."""

    id: int
    key: str
    description: Optional[str] = None


class Group(BaseModel):
    """IdP-provisioned group that maps to roles (schema: groups)."""

    id: int
    tenant_id: int
    name: str


class AccessRequest(BaseModel):
    """Unlinked-channel access ask awaiting operator review (schema: access_requests)."""

    id: Optional[int] = None
    tenant_id: int
    channel: str
    requested_identity: Optional[str] = None
    requested_email: Optional[str] = None
    status: AccessRequestStatus = AccessRequestStatus.PENDING
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AuditEvent(BaseModel):
    """Structured operator/compliance trail entry (schema: audit_events)."""

    tenant_id: int
    user_id: Optional[int] = None
    event_type: str
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    channel: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityResolution(BaseModel):
    """Outcome of resolving a raw channel event to a canonical CI-OS user."""

    resolved: bool
    user: Optional[User] = None
    reason: Optional[str] = None
    access_request: Optional[AccessRequest] = None


class AclDecision(BaseModel):
    """Outcome of an AclChecker.check() call."""

    allow: bool
    reason: str
    tenant_id: int
    user_id: int
    permission_key: str
