"""CI-OS platform identity/ACL layer.

Resolves channel identities to canonical users (resolver.py) and checks
tenant-scoped permissions with a full audit trail (acl.py).
"""

from cios.platform.identity.acl import AclChecker
from cios.platform.identity.resolver import IdentityResolver
from cios.platform.identity.types import (
    AccessRequest,
    AccessRequestStatus,
    AclDecision,
    AuditEvent,
    ChannelIdentity,
    ChannelIdentityStatus,
    Group,
    IdentityResolution,
    Permission,
    Role,
    User,
    UserStatus,
)

__all__ = [
    "AclChecker",
    "IdentityResolver",
    "AccessRequest",
    "AccessRequestStatus",
    "AclDecision",
    "AuditEvent",
    "ChannelIdentity",
    "ChannelIdentityStatus",
    "Group",
    "IdentityResolution",
    "Permission",
    "Role",
    "User",
    "UserStatus",
]
