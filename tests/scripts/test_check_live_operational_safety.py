from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_PATH = ROOT / "scripts" / "check_live_operational_safety.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_live_operational_safety", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _make_runtime(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    app = tmp_path / "app"
    public = tmp_path / "public"
    public_store = tmp_path / "public-store"
    release = public_store / "releases" / "cios-20260728T120000Z-123"

    (app / "out").mkdir(parents=True)
    (public / "data").mkdir(parents=True)
    (release / "data").mkdir(parents=True)
    (public_store / "served" / "data").mkdir(parents=True)

    (app / ".cios-package-commit").write_text("abc123\n", encoding="utf-8")
    (app / "out" / "argus-dashboard.json").write_text("{}", encoding="utf-8")
    (public / "index.html").write_text("dashboard", encoding="utf-8")
    (release / "index.html").write_text("dashboard", encoding="utf-8")
    (release / "publication-manifest.json").write_text(
        json.dumps({"schema_version": 1, "run_id": release.name}),
        encoding="utf-8",
    )
    (public_store / "served" / "index.html").write_text("dashboard", encoding="utf-8")
    (public_store / "served" / "publication-manifest.json").write_text(
        json.dumps({"schema_version": 1, "run_id": release.name}),
        encoding="utf-8",
    )
    (public_store / "current").symlink_to(f"releases/{release.name}")
    return app, public, public_store, release


def test_operational_safety_passes_for_clean_release(tmp_path) -> None:
    module = _load_module()
    app, public, public_store, release = _make_runtime(tmp_path)

    result = module.evaluate_operational_safety(
        app_dir=app,
        public_dir=public,
        public_store_dir=public_store,
        expected_package_commit="abc123",
        ps_text="USER PPID PID STAT CMD\n",
        generated_at="2026-07-28T12:00:00Z",
    )

    assert result["gate"] == "cios_live_operational_safety"
    assert result["status"] == "passed"
    assert result["operational_safe"] is True
    assert result["package_commit"] == "abc123"
    assert result["public_store_current"] == str(release.resolve())
    assert result["current_release_exists"] is True
    assert result["served_release_ready"] is True
    assert result["hidden_staging_dir_count"] == 0
    assert result["root_owned_artifact_count"] == 0
    assert result["orphan_process_count"] == 0
    assert result["findings"] == []


def test_operational_safety_fails_for_hidden_staging_root_owned_and_orphan_process(tmp_path, monkeypatch) -> None:
    module = _load_module()
    app, public, public_store, _release = _make_runtime(tmp_path)
    hidden = public_store / "served" / ".argus-publish.999"
    hidden.mkdir()
    root_owned = app / "out" / "root-owned.json"
    root_owned.write_text("{}", encoding="utf-8")

    def fake_owner_name(path: Path) -> str:
        return "root" if path == root_owned else "cios"

    monkeypatch.setattr(module, "_owner_name", fake_owner_name)
    ps_text = "cios 1 4242 S python scripts/daily_production_run.py\n"

    result = module.evaluate_operational_safety(
        app_dir=app,
        public_dir=public,
        public_store_dir=public_store,
        expected_package_commit="abc123",
        ps_text=ps_text,
    )

    assert result["status"] == "failed"
    assert result["operational_safe"] is False
    assert result["hidden_staging_dir_count"] == 1
    assert result["root_owned_artifact_count"] == 1
    assert result["orphan_process_count"] == 1
    requirements = {finding["requirement"] for finding in result["findings"]}
    assert "no_hidden_staging_dirs" in requirements
    assert "no_root_owned_artifacts" in requirements
    assert "no_orphan_cios_processes" in requirements


def test_operational_safety_cli_writes_payload_and_exit_code(tmp_path) -> None:
    module = _load_module()
    app, public, public_store, _release = _make_runtime(tmp_path)
    output = tmp_path / "live-operational-safety.json"

    code = module.main(
        [
            "--app-dir",
            str(app),
            "--public-dir",
            str(public),
            "--public-store-dir",
            str(public_store),
            "--expected-package-commit",
            "abc123",
            "--ps-text",
            "USER PPID PID STAT CMD\n",
            "--output",
            str(output),
        ]
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert code == 0
    assert payload["status"] == "passed"
    assert payload["operational_safe"] is True
