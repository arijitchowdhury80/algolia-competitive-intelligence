"""Tests for the Phase 0 release-record helper."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "build_phase0_release_record.py"


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=True,
    )
    return completed.stdout.strip()


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "ci-os@example.test")
    _git(repo, "config", "user.name", "CI OS")
    _git(repo, "remote", "add", "origin", "https://github.com/example/cios.git")
    (repo / "src").mkdir()
    (repo / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (repo / "README.md").write_text("# CI-OS\n", encoding="utf-8")
    (repo / ".DS_Store").write_text("ignored local metadata\n", encoding="utf-8")
    (repo / "out").mkdir()
    (repo / "out" / "runtime.json").write_text("{}\n", encoding="utf-8")
    _git(repo, "add", "src/app.py", "README.md")
    _git(repo, "commit", "-m", "initial")
    _git(repo, "tag", "ci-os-phase0-test")
    return repo


def test_generate_writes_tracked_source_release_record(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    output = tmp_path / "release-record.json"

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "generate",
            "--source-root",
            str(repo),
            "--app-dir",
            str(repo),
            "--tag",
            "ci-os-phase0-test",
            "--output",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["kind"] == "cios.phase0.release_record"
    assert payload["source"]["repo_url"] == "https://github.com/example/cios.git"
    assert payload["source"]["branch"] in {"main", "master"}
    assert payload["source"]["tag"] == "ci-os-phase0-test"
    assert payload["source"]["tracked_file_count"] == 2
    assert len(payload["source"]["commit"]) == 40
    assert len(payload["source"]["archive_sha256"]) == 64
    assert len(payload["source"]["tracked_file_manifest_sha256"]) == 64
    assert [item["path"] for item in payload["files"]] == ["README.md", "src/app.py"]
    assert ".DS_Store" not in json.dumps(payload)
    assert "out/runtime.json" not in json.dumps(payload)


def test_verify_accepts_matching_app_directory(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    output = tmp_path / "release-record.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "generate",
            "--source-root",
            str(repo),
            "--app-dir",
            str(repo),
            "--output",
            str(output),
        ],
        check=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "verify",
            "--app-dir",
            str(repo),
            "--manifest",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "PASS: app directory matches CI-OS Phase 0 release record" in result.stdout


def test_verify_rejects_missing_or_changed_files(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    output = tmp_path / "release-record.json"
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "generate",
            "--source-root",
            str(repo),
            "--app-dir",
            str(repo),
            "--output",
            str(output),
        ],
        check=True,
    )
    (repo / "src" / "app.py").write_text("print('changed')\n", encoding="utf-8")
    (repo / "README.md").unlink()

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "verify",
            "--app-dir",
            str(repo),
            "--manifest",
            str(output),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 2
    assert "missing file: README.md" in result.stderr
    assert "checksum mismatch: src/app.py" in result.stderr
