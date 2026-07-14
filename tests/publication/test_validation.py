from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cios.publication.generation import PublicationValidationError, build_generation
from cios.publication.types import (
    ArtifactSpec,
    GenerationValidationPolicy,
    PublicationKind,
    PublicationRequest,
    RunIdentity,
)
from cios.publication.validation import validate_generation


RUN_ID = "cios-20260714T090000Z-12345"
GENERATED_AT = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)


def _artifact(source: Path, public_path: str, content: str, media_type: str) -> ArtifactSpec:
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(content, encoding="utf-8")
    return ArtifactSpec(
        source_path=source,
        public_path=public_path,
        media_type=media_type,
    )


def _build_complete_generation(tmp_path: Path) -> tuple[Path, RunIdentity]:
    identity = RunIdentity(run_id=RUN_ID, tenant_slug="algolia")
    status = {
        "schema_version": 2,
        "run_id": RUN_ID,
        "tenant_slug": "algolia",
        "generated_at": GENERATED_AT.isoformat(),
        "publish_status": "published",
        "status": "published",
        "public_dashboard_updated": True,
        "safety": {
            "version": 1,
            "artifact_paths_redacted": True,
            "secret_values_included": False,
            "public_safe": True,
        },
    }
    dashboard = {
        "generated_at": GENERATED_AT.isoformat(),
        "run_health": {"run_id": RUN_ID},
        "product_market_run": {"run_id": RUN_ID},
    }
    request = PublicationRequest(
        identity=identity,
        kind=PublicationKind.DECISION,
        generated_at=GENERATED_AT,
        artifacts=(
            _artifact(tmp_path / "src/index.html", "index.html", "<main>Argus</main>", "text/html"),
            _artifact(tmp_path / "src/brief.html", "brief.html", "<article>Read</article>", "text/html"),
            _artifact(
                tmp_path / "src/dashboard.json",
                "data/semantic-dashboard.json",
                json.dumps(dashboard),
                "application/json",
            ),
            _artifact(
                tmp_path / "src/manifest.json",
                "data/argus-data-plane-manifest.json",
                json.dumps({"run_id": RUN_ID, "generated_at": GENERATED_AT.isoformat()}),
                "application/json",
            ),
            _artifact(
                tmp_path / "src/status.json",
                "data/argus-latest-run-status.json",
                json.dumps(status),
                "application/json",
            ),
            _artifact(
                tmp_path / "src/constructor.html",
                "briefs/algolia/constructor.html",
                "<article>Constructor</article>",
                "text/html",
            ),
            _artifact(
                tmp_path / "src/package-verdict.json",
                "verdicts/hermes-package-contract.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "gate": "hermes_package_contract",
                        "run_id": RUN_ID,
                        "generated_at": GENERATED_AT.isoformat(),
                        "status": "pass",
                        "exit_code": 0,
                        "checks": {"required_contract": True},
                    }
                ),
                "application/json",
            ),
        ),
    )
    generation = tmp_path / "generation"
    build_generation(request, generation)
    return generation, identity


def _policy() -> GenerationValidationPolicy:
    return GenerationValidationPolicy(
        now=GENERATED_AT + timedelta(minutes=5),
        max_age_seconds=600,
    )


def _rewrite_manifest_record(generation: Path, artifact_path: str) -> None:
    artifact = generation / artifact_path
    manifest_path = generation / "publication-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    content = artifact.read_bytes()
    for record in manifest["files"]:
        if record["path"] == artifact_path:
            record["bytes"] = len(content)
            record["sha256"] = hashlib.sha256(content).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")


def test_validate_generation_complete_fresh_run_passes(tmp_path: Path) -> None:
    generation, identity = _build_complete_generation(tmp_path)

    manifest = validate_generation(generation, identity, _policy())

    assert manifest.run_id == RUN_ID
    assert manifest.kind is PublicationKind.DECISION


def test_validate_generation_tampered_file_fails(tmp_path: Path) -> None:
    generation, identity = _build_complete_generation(tmp_path)
    (generation / "index.html").write_text("tampered", encoding="utf-8")

    with pytest.raises(PublicationValidationError, match="hash mismatch"):
        validate_generation(generation, identity, _policy())


def test_validate_generation_extra_file_fails(tmp_path: Path) -> None:
    generation, identity = _build_complete_generation(tmp_path)
    (generation / "unmanifested.txt").write_text("extra", encoding="utf-8")

    with pytest.raises(PublicationValidationError, match="unexpected artifact"):
        validate_generation(generation, identity, _policy())


def test_validate_generation_stale_manifest_fails(tmp_path: Path) -> None:
    generation, identity = _build_complete_generation(tmp_path)
    stale_policy = GenerationValidationPolicy(
        now=GENERATED_AT + timedelta(hours=2),
        max_age_seconds=600,
    )

    with pytest.raises(PublicationValidationError, match="stale generation"):
        validate_generation(generation, identity, stale_policy)


def test_validate_generation_mismatched_dashboard_run_fails(tmp_path: Path) -> None:
    generation, identity = _build_complete_generation(tmp_path)
    dashboard = generation / "data/semantic-dashboard.json"
    payload = json.loads(dashboard.read_text(encoding="utf-8"))
    payload["product_market_run"]["run_id"] = "cios-20260714T090000Z-other"
    dashboard.write_text(json.dumps(payload), encoding="utf-8")
    _rewrite_manifest_record(generation, "data/semantic-dashboard.json")

    with pytest.raises(PublicationValidationError, match="run identity mismatch"):
        validate_generation(generation, identity, _policy())


@pytest.mark.parametrize(
    "artifact_path",
    (
        "data/semantic-dashboard.json",
        "data/argus-data-plane-manifest.json",
        "data/argus-latest-run-status.json",
    ),
)
def test_validate_generation_rejects_stale_structured_artifact(
    tmp_path: Path,
    artifact_path: str,
) -> None:
    generation, identity = _build_complete_generation(tmp_path)
    artifact = generation / artifact_path
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["generated_at"] = (GENERATED_AT - timedelta(hours=2)).isoformat()
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    _rewrite_manifest_record(generation, artifact_path)

    with pytest.raises(PublicationValidationError, match="stale structured artifact"):
        validate_generation(generation, identity, _policy())


def test_validate_generation_rejects_nonzero_package_verdict_exit_code(tmp_path: Path) -> None:
    generation, identity = _build_complete_generation(tmp_path)
    artifact_path = "verdicts/hermes-package-contract.json"
    artifact = generation / artifact_path
    payload = json.loads(artifact.read_text(encoding="utf-8"))
    payload["exit_code"] = 2
    artifact.write_text(json.dumps(payload), encoding="utf-8")
    _rewrite_manifest_record(generation, artifact_path)

    with pytest.raises(PublicationValidationError, match="invalid structured verdict"):
        validate_generation(generation, identity, _policy())
