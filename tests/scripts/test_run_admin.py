from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_admin.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("run_admin", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_run_admin_loads_explicit_env_file_before_starting_uvicorn(tmp_path, monkeypatch) -> None:
    module = _load_module()
    env_file = tmp_path / "cios-env"
    env_file.write_text(
        """
        # loaded by test
        CIOS_DATABASE_URL=postgresql://cios_app:test@127.0.0.1:5433/cios
        CIOS_ADMIN_TOKEN="local-admin"
        CIOS_GA4_EXPORT_ENABLED=1
        """,
        encoding="utf-8",
    )
    calls: list[dict[str, object]] = []

    def fake_run(app: str, **kwargs) -> None:
        calls.append({"app": app, **kwargs})

    monkeypatch.delenv("CIOS_DATABASE_URL", raising=False)
    monkeypatch.delenv("CIOS_ADMIN_TOKEN", raising=False)
    monkeypatch.setattr(module.uvicorn, "run", fake_run)

    try:
        module.main([
            "--env-file",
            str(env_file),
            "--host",
            "127.0.0.1",
            "--port",
            "9876",
        ])

        assert os.environ["CIOS_DATABASE_URL"] == "postgresql://cios_app:test@127.0.0.1:5433/cios"
        assert os.environ["CIOS_ADMIN_TOKEN"] == "local-admin"
        assert os.environ["CIOS_GA4_EXPORT_ENABLED"] == "1"
        assert calls == [
            {
                "app": "cios.admin.app:create_app",
                "factory": True,
                "host": "127.0.0.1",
                "port": 9876,
            }
        ]
    finally:
        os.environ.pop("CIOS_DATABASE_URL", None)
        os.environ.pop("CIOS_ADMIN_TOKEN", None)
        os.environ.pop("CIOS_GA4_EXPORT_ENABLED", None)


def test_run_admin_refuses_missing_explicit_env_file(tmp_path) -> None:
    module = _load_module()
    missing = tmp_path / "missing-env"

    try:
        module.main(["--env-file", str(missing)])
    except SystemExit as exc:
        assert str(exc) == f"missing CIOS env file: {missing}"
    else:
        raise AssertionError("expected SystemExit for missing explicit env file")
