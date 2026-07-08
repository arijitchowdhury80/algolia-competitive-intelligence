"""Tests for the CI-OS identity/ACL layer.

All storage is in-memory fakes implementing the repository protocols --
no Postgres, no mocking framework.
"""

from __future__ import annotations

from datetime import datetime, timezone

from cios.platform.channels.types import Channel, NormalizedInboundMessage
from cios.platform.identity.acl import AclChecker
from cios.platform.identity.resolver import IdentityResolver
from cios.platform.identity.types import (
    AccessRequest,
    ChannelIdentity,
    ChannelIdentityStatus,
    User,
    UserStatus,
)


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------


class FakeChannelIdentityRepository:
    def __init__(self, identities=None):
        self._identities = list(identities or [])

    def get_by_channel_user_id(self, tenant_id, channel, channel_user_id):
        for identity in self._identities:
            if (
                identity.tenant_id == tenant_id
                and identity.channel == channel
                and identity.channel_user_id == channel_user_id
            ):
                return identity
        return None


class FakeUserRepository:
    def __init__(self, users=None):
        self._users = list(users or [])

    def get(self, tenant_id, user_id):
        for user in self._users:
            if user.tenant_id == tenant_id and user.id == user_id:
                return user
        return None


class FakeAccessRequestRepository:
    def __init__(self):
        self.created: list[AccessRequest] = []

    def create(self, access_request):
        stored = access_request.model_copy(update={"id": len(self.created) + 1})
        self.created.append(stored)
        return stored


class FakeRoleAssignmentRepository:
    def __init__(self, assignments=None):
        # {(tenant_id, user_id): [role_id, ...]}
        self._assignments = dict(assignments or {})

    def role_ids_for_user(self, tenant_id, user_id):
        return list(self._assignments.get((tenant_id, user_id), []))


class FakeGroupMembershipRepository:
    def __init__(self, memberships=None):
        # {(tenant_id, user_id): [group_id, ...]}
        self._memberships = dict(memberships or {})

    def group_ids_for_user(self, tenant_id, user_id):
        return list(self._memberships.get((tenant_id, user_id), []))


class FakeGroupRoleMappingRepository:
    def __init__(self, mappings=None):
        # {(tenant_id, group_id): [role_id, ...]}
        self._mappings = dict(mappings or {})

    def role_ids_for_group(self, tenant_id, group_id):
        return list(self._mappings.get((tenant_id, group_id), []))


class FakeRolePermissionRepository:
    def __init__(self, grants=None):
        # {(tenant_id, role_id): [permission_key, ...]}
        self._grants = dict(grants or {})

    def permission_keys_for_role(self, tenant_id, role_id):
        return list(self._grants.get((tenant_id, role_id), []))


def _message(channel_user_id: str = "6789423537") -> NormalizedInboundMessage:
    return NormalizedInboundMessage(
        channel=Channel.TELEGRAM,
        channel_user_id=channel_user_id,
        message_id="1",
        text="hello",
        received_at=datetime.now(timezone.utc),
    )


# ---------------------------------------------------------------------------
# IdentityResolver
# ---------------------------------------------------------------------------


def test_resolver_resolves_linked_identity_to_active_user():
    user = User(id=1, tenant_id=100, email="arijit@example.com", status=UserStatus.ACTIVE)
    identity = ChannelIdentity(
        id=1,
        tenant_id=100,
        user_id=1,
        channel="telegram",
        channel_user_id="6789423537",
        status=ChannelIdentityStatus.LINKED,
    )
    resolver = IdentityResolver(
        channel_identities=FakeChannelIdentityRepository([identity]),
        users=FakeUserRepository([user]),
        access_requests=FakeAccessRequestRepository(),
    )

    resolution = resolver.resolve(tenant_id=100, message=_message())

    assert resolution.resolved is True
    assert resolution.user is not None
    assert resolution.user.id == 1
    assert resolution.access_request is None


def test_resolver_denies_and_creates_access_request_for_unknown_identity():
    access_requests = FakeAccessRequestRepository()
    resolver = IdentityResolver(
        channel_identities=FakeChannelIdentityRepository([]),
        users=FakeUserRepository([]),
        access_requests=access_requests,
    )

    resolution = resolver.resolve(tenant_id=100, message=_message("999999999"))

    assert resolution.resolved is False
    assert resolution.user is None
    assert resolution.reason == "unknown_or_unlinked_channel_identity"
    assert len(access_requests.created) == 1
    assert access_requests.created[0].tenant_id == 100
    assert access_requests.created[0].channel == "telegram"
    assert access_requests.created[0].requested_identity == "999999999"


def test_resolver_denies_pending_unlinked_identity():
    identity = ChannelIdentity(
        id=2,
        tenant_id=100,
        user_id=None,
        channel="telegram",
        channel_user_id="222",
        status=ChannelIdentityStatus.PENDING,
    )
    access_requests = FakeAccessRequestRepository()
    resolver = IdentityResolver(
        channel_identities=FakeChannelIdentityRepository([identity]),
        users=FakeUserRepository([]),
        access_requests=access_requests,
    )

    resolution = resolver.resolve(tenant_id=100, message=_message("222"))

    assert resolution.resolved is False
    assert len(access_requests.created) == 1


# ---------------------------------------------------------------------------
# AclChecker
# ---------------------------------------------------------------------------


def test_acl_allow_path_grants_via_direct_role():
    audited = []
    checker = AclChecker(
        role_assignments=FakeRoleAssignmentRepository({(100, 1): [10]}),
        group_memberships=FakeGroupMembershipRepository(),
        group_role_mappings=FakeGroupRoleMappingRepository(),
        role_permissions=FakeRolePermissionRepository({(100, 10): ["reports.read"]}),
        audit_sink=audited.append,
    )

    decision = checker.check(user_id=1, tenant_id=100, permission_key="reports.read")

    assert decision.allow is True
    assert decision.reason == "granted_via_role"
    assert len(audited) == 1
    assert audited[0].event_type == "acl_check"
    assert audited[0].tenant_id == 100
    assert audited[0].user_id == 1
    assert audited[0].metadata["allow"] is True


def test_acl_deny_path_no_role():
    audited = []
    checker = AclChecker(
        role_assignments=FakeRoleAssignmentRepository(),
        group_memberships=FakeGroupMembershipRepository(),
        group_role_mappings=FakeGroupRoleMappingRepository(),
        role_permissions=FakeRolePermissionRepository(),
        audit_sink=audited.append,
    )

    decision = checker.check(user_id=1, tenant_id=100, permission_key="reports.read")

    assert decision.allow is False
    assert decision.reason == "no_role_grants_permission"
    assert len(audited) == 1
    assert audited[0].metadata["allow"] is False


def test_acl_deny_path_wrong_tenant_no_bleed():
    # User 1 has a role granting reports.read under tenant 100 only.
    checker = AclChecker(
        role_assignments=FakeRoleAssignmentRepository({(100, 1): [10]}),
        group_memberships=FakeGroupMembershipRepository(),
        group_role_mappings=FakeGroupRoleMappingRepository(),
        role_permissions=FakeRolePermissionRepository({(100, 10): ["reports.read"]}),
        audit_sink=lambda event: None,
    )

    decision = checker.check(user_id=1, tenant_id=200, permission_key="reports.read")

    assert decision.allow is False
    assert decision.tenant_id == 200


def test_acl_group_inherited_role_grants_permission():
    audited = []
    checker = AclChecker(
        role_assignments=FakeRoleAssignmentRepository(),
        group_memberships=FakeGroupMembershipRepository({(100, 1): [50]}),
        group_role_mappings=FakeGroupRoleMappingRepository({(100, 50): [10]}),
        role_permissions=FakeRolePermissionRepository({(100, 10): ["reports.read"]}),
        audit_sink=audited.append,
    )

    decision = checker.check(user_id=1, tenant_id=100, permission_key="reports.read")

    assert decision.allow is True
    assert len(audited) == 1
