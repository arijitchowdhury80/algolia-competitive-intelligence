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


def test_host_permissions_initialize_managed_output_marker() -> None:
    text = HOST_PERMISSIONS.read_text(encoding="utf-8")

    assert 'touch "$APP/out/.cios-output-dir"' in text
    assert 'chown "$APP_USER:$HERMES_GROUP" "$APP/out/.cios-output-dir"' in text
    assert 'chmod 660 "$APP/out/.cios-output-dir"' in text


def test_host_permissions_initialize_managed_looker_data_root() -> None:
    text = HOST_PERMISSIONS.read_text(encoding="utf-8")

    assert 'install -d -o "$APP_USER" -g "$HERMES_GROUP" -m 2775 "$APP/data" "$APP/data/looker"' in text


def test_host_permissions_support_pre_mounted_release_without_rewriting_app_fstab() -> None:
    text = HOST_PERMISSIONS.read_text(encoding="utf-8")

    assert 'MANAGE_APP_BIND="${CIOS_MANAGE_APP_BIND:-1}"' in text
    assert 'if [ "$MANAGE_APP_BIND" = "1" ]; then' in text
    assert 'app_fstab="$SOURCE_APP $APP none bind 0 0"' in text


def test_host_permissions_preserve_hermes_enqueue_and_private_cios_state_boundary() -> None:
    text = HOST_PERMISSIONS.read_text(encoding="utf-8")

    assert 'chown "$APP_USER:$HERMES_GROUP" "$APP/run-queue"' in text
    assert 'chmod 3770 "$APP/run-queue"' in text
    assert 'chown "$APP_USER:$APP_USER" "$APP/run-queue/.state"' in text
    assert 'chmod 700 "$APP/run-queue/.state"' in text
