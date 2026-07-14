from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy" / "cios-static.service"
HOST_PERMISSIONS = ROOT / "deploy" / "cios-host-permissions.sh"


def test_static_service_runs_as_cios_with_cgroup_and_sandbox_limits() -> None:
    text = SERVICE.read_text(encoding="utf-8")

    for contract in (
        "User=cios",
        "Group=cios",
        "WorkingDirectory=/opt/cios/public-store/served",
        "--bind 127.0.0.1 8662",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "PrivateDevices=true",
        "MemoryMax=128M",
        "CPUQuota=20%",
        "TasksMax=32",
        "CapabilityBoundingSet=",
    ):
        assert contract in text


def test_host_permissions_create_app_owned_immutable_public_store() -> None:
    text = HOST_PERMISSIONS.read_text(encoding="utf-8")

    assert 'PUBLIC_STORE="${CIOS_PUBLIC_STORE_DIR:-/opt/cios/public-store}"' in text
    assert 'install -d -o "$APP_USER" -g "$HERMES_GROUP" -m 2750 "$PUBLIC_STORE"' in text
    assert 'install -d -o "$APP_USER" -g "$HERMES_GROUP" -m 2750 "$PUBLIC_STORE/releases"' in text
    assert 'install -d -o "$APP_USER" -g "$HERMES_GROUP" -m 2750 "$PUBLIC_STORE/served"' in text
