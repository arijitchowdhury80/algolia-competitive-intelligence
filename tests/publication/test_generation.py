from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cios.publication.generation import PublicationValidationError, build_generation
from cios.publication.types import (
    ArtifactSpec,
    PublicationKind,
    PublicationRequest,
    RunIdentity,
    SafetyPolicy,
)


def _request(artifacts: tuple[ArtifactSpec, ...]) -> PublicationRequest:
    return PublicationRequest(
        identity=RunIdentity(run_id="cios-20260714T090000Z-12345", tenant_slug="algolia"),
        kind=PublicationKind.DECISION,
        generated_at=datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc),
        artifacts=artifacts,
    )


def test_build_generation_copies_declared_files_and_writes_sorted_hash_manifest(
    tmp_path: Path,
) -> None:
    dashboard = tmp_path / "source" / "dashboard.json"
    index = tmp_path / "source" / "index.html"
    dashboard.parent.mkdir()
    dashboard.write_text('{"run_id":"cios-20260714T090000Z-12345"}\n', encoding="utf-8")
    index.write_text("<main>Argus</main>\n", encoding="utf-8")
    request = _request(
        (
            ArtifactSpec(
                source_path=dashboard,
                public_path="data/semantic-dashboard.json",
                media_type="application/json",
            ),
            ArtifactSpec(
                source_path=index,
                public_path="index.html",
                media_type="text/html",
            ),
        )
    )

    manifest = build_generation(request, tmp_path / "generation")

    assert [record.path for record in manifest.files] == [
        "data/semantic-dashboard.json",
        "index.html",
    ]
    assert manifest.files[0].sha256 == hashlib.sha256(dashboard.read_bytes()).hexdigest()
    assert manifest.files[0].bytes == dashboard.stat().st_size
    assert manifest.safety.public_safe is True
    assert (tmp_path / "generation" / "index.html").read_text(encoding="utf-8") == "<main>Argus</main>\n"
    assert (tmp_path / "generation" / "publication-manifest.json").is_file()


def test_build_generation_rejects_symlink_source(tmp_path: Path) -> None:
    source = tmp_path / "source.html"
    source.write_text("safe", encoding="utf-8")
    link = tmp_path / "link.html"
    link.symlink_to(source)
    request = _request(
        (
            ArtifactSpec(
                source_path=link,
                public_path="index.html",
                media_type="text/html",
            ),
        )
    )

    with pytest.raises(PublicationValidationError, match="regular file"):
        build_generation(request, tmp_path / "generation")


@pytest.mark.parametrize(
    "unsafe_text",
    (
        "<p>/root/.hermes/private/report.json</p>",
        "<p>/opt/cios/app/out/report.json</p>",
        "<p>/Users/arijit/private/report.json</p>",
        "<p>/tmp/private/report.json</p>",
        "<p>/private/var/folders/report.json</p>",
        "<p>/app/out/report.json</p>",
        r"<p>C:\Users\arijit\private\report.json</p>",
        "<a href='file:///tmp/report.json'>report</a>",
    ),
)
def test_build_generation_rejects_local_path_leaks(tmp_path: Path, unsafe_text: str) -> None:
    source = tmp_path / "index.html"
    source.write_text(unsafe_text, encoding="utf-8")
    request = _request(
        (
            ArtifactSpec(
                source_path=source,
                public_path="index.html",
                media_type="text/html",
            ),
        )
    )

    with pytest.raises(PublicationValidationError, match="local_path"):
        build_generation(request, tmp_path / "generation")

    assert not (tmp_path / "generation").exists()


def test_build_generation_rejects_secret_without_echoing_value(tmp_path: Path) -> None:
    secret = "live-secret-value-123456"
    source = tmp_path / "brief.html"
    source.write_text(f"<p>{secret}</p>", encoding="utf-8")
    request = _request(
        (
            ArtifactSpec(
                source_path=source,
                public_path="brief.html",
                media_type="text/html",
            ),
        )
    )

    with pytest.raises(PublicationValidationError) as captured:
        build_generation(
            request,
            tmp_path / "generation",
            SafetyPolicy(secret_values=(secret,)),
        )

    assert "configured_secret" in str(captured.value)
    assert secret not in str(captured.value)
    assert not (tmp_path / "generation").exists()


@pytest.mark.parametrize(
    "payload",
    (
        '{"api_key":"new-unregistered-secret"}',
        '{"nested":{"client_secret":"new-unregistered-secret"}}',
        '{"authorization":"Bearer new-unregistered-secret"}',
        '{"api_key":{"value":"new-unregistered-secret"}}',
        '{"refresh_token":["new-unregistered-secret"]}',
    ),
)
def test_build_generation_rejects_credential_shaped_json_fields(
    tmp_path: Path,
    payload: str,
) -> None:
    source = tmp_path / "dashboard.json"
    source.write_text(payload, encoding="utf-8")
    request = _request(
        (
            ArtifactSpec(
                source_path=source,
                public_path="data/semantic-dashboard.json",
                media_type="application/json",
            ),
        )
    )

    with pytest.raises(PublicationValidationError, match="credential_field"):
        build_generation(request, tmp_path / "generation")

    assert "new-unregistered-secret" not in str(request)
    assert not (tmp_path / "generation").exists()
