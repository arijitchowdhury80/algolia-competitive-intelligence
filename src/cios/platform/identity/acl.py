"""Permission checks: user -> roles (direct + via groups) -> permissions.

Tenant-scoped throughout -- a role assignment or group membership recorded
under one tenant must never grant a permission when checked under another
tenant (tenant bleed). Every check emits exactly one audit event via an
injected sink, allow or deny, so the audit_events table (schema.sql) has a
complete ACL decision trail. Storage access is via injected repository
protocols only -- no direct DB access here (tests use in-memory fakes).
"""

from __future__ import annotations

from typing import Callable, Protocol

from cios.platform.identity.types import AclDecision, AuditEvent


class RoleAssignmentRepository(Protocol):
    def role_ids_for_user(self, tenant_id: int, user_id: int) -> list[int]: ...


class GroupMembershipRepository(Protocol):
    def group_ids_for_user(self, tenant_id: int, user_id: int) -> list[int]: ...


class GroupRoleMappingRepository(Protocol):
    def role_ids_for_group(self, tenant_id: int, group_id: int) -> list[int]: ...


class RolePermissionRepository(Protocol):
    def permission_keys_for_role(self, tenant_id: int, role_id: int) -> list[str]: ...


# Callable sink rather than a class protocol: callers may pass a plain
# function, a bound method, or list.append in tests.
AuditSink = Callable[[AuditEvent], None]


class AclChecker:
    """Resolves effective permissions for a user within a tenant."""

    def __init__(
        self,
        role_assignments: RoleAssignmentRepository,
        group_memberships: GroupMembershipRepository,
        group_role_mappings: GroupRoleMappingRepository,
        role_permissions: RolePermissionRepository,
        audit_sink: AuditSink,
    ) -> None:
        self._role_assignments = role_assignments
        self._group_memberships = group_memberships
        self._group_role_mappings = group_role_mappings
        self._role_permissions = role_permissions
        self._audit_sink = audit_sink

    def _effective_role_ids(self, tenant_id: int, user_id: int) -> set[int]:
        role_ids = set(self._role_assignments.role_ids_for_user(tenant_id, user_id))
        for group_id in self._group_memberships.group_ids_for_user(tenant_id, user_id):
            role_ids.update(self._group_role_mappings.role_ids_for_group(tenant_id, group_id))
        return role_ids

    def check(self, user_id: int, tenant_id: int, permission_key: str) -> AclDecision:
        role_ids = self._effective_role_ids(tenant_id, user_id)

        granted = any(
            permission_key in self._role_permissions.permission_keys_for_role(tenant_id, role_id)
            for role_id in role_ids
        )

        decision = AclDecision(
            allow=granted,
            reason="granted_via_role" if granted else "no_role_grants_permission",
            tenant_id=tenant_id,
            user_id=user_id,
            permission_key=permission_key,
        )

        self._audit_sink(
            AuditEvent(
                tenant_id=tenant_id,
                user_id=user_id,
                event_type="acl_check",
                resource_type="permission",
                resource_id=permission_key,
                metadata={"allow": decision.allow, "reason": decision.reason},
            )
        )

        return decision
