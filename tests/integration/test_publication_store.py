from __future__ import annotations

import json
import os
import fcntl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cios.publication.generation import PublicationValidationError
from cios.publication.store import PublicationStore
from cios.publication.types import (
    ArtifactSpec,
    GenerationValidationPolicy,
    PublicationKind,
    PublicationRequest,
    RunIdentity,
)


GENERATED_AT = datetime(2026, 7, 14, 9, 0, tzinfo=timezone.utc)


def _store(root: Path) -> PublicationStore:
    return PublicationStore(
        root,
        validation_policy=GenerationValidationPolicy(
            now=GENERATED_AT + timedelta(minutes=5),
            max_age_seconds=600,
        ),
    )


class FailLatestStatusFileOps:
    def __init__(self) -> None:
        self.targets: list[str] = []

    def replace(self, source: Path, target: Path) -> None:
        self.targets.append(target.name)
        if target.name == "latest-status.json":
            raise OSError("injected status replace failure")
        os.replace(source, target)


def _write_artifact(
    path: Path,
    content: str,
    *,
    public_path: str | None = None,
    media_type: str = "text/html",
) -> ArtifactSpec:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return ArtifactSpec(
        source_path=path,
        public_path=public_path or path.name,
        media_type=media_type,
    )


def _status_artifact(source_dir: Path, run_id: str, publish_status: str) -> ArtifactSpec:
    status = {
        "schema_version": 2,
        "run_id": run_id,
        "tenant_slug": "algolia",
        "generated_at": GENERATED_AT.isoformat(),
        "publish_status": publish_status,
        "status": "published" if publish_status == "published" else "blocked_on_evidence",
        "public_dashboard_updated": publish_status == "published",
        "safety": {
            "version": 1,
            "artifact_paths_redacted": True,
            "secret_values_included": False,
            "public_safe": True,
        },
    }
    path = source_dir / "argus-latest-run-status.json"
    path.write_text(json.dumps(status), encoding="utf-8")
    return ArtifactSpec(
        source_path=path,
        public_path="data/argus-latest-run-status.json",
        media_type="application/json",
    )


def _request(
    source_dir: Path,
    run_id: str,
    kind: PublicationKind,
) -> PublicationRequest:
    publish_status = "published" if kind is PublicationKind.DECISION else "blocked"
    artifacts: tuple[ArtifactSpec, ...]
    if kind is PublicationKind.DECISION:
        current = json.dumps(
            {
                "generated_at": GENERATED_AT.isoformat(),
                "run_health": {"run_id": run_id},
                "product_market_run": {"run_id": run_id},
            }
        )
        artifacts = (
            _write_artifact(source_dir / "index.html", f"<main>{run_id}</main>"),
            _write_artifact(source_dir / "brief.html", f"<article>{run_id}</article>"),
            _write_artifact(
                source_dir / "dashboard.json",
                current,
                public_path="data/semantic-dashboard.json",
                media_type="application/json",
            ),
            _write_artifact(
                source_dir / "data-plane.json",
                json.dumps({"run_id": run_id, "generated_at": GENERATED_AT.isoformat()}),
                public_path="data/argus-data-plane-manifest.json",
                media_type="application/json",
            ),
            _write_artifact(
                source_dir / "demand-plan.csv",
                "Page title,Argus topic\nChannel Assistant,channel assistant\n",
                public_path="data/argus-demand-plan-template.csv",
                media_type="text/csv",
            ),
            _write_artifact(
                source_dir / "demand-guide.json",
                json.dumps({"generated_at": GENERATED_AT.isoformat(), "topic_count": 1}),
                public_path="data/argus-demand-work-order-guide.json",
                media_type="application/json",
            ),
            _write_artifact(
                source_dir / "competitor.html",
                f"<article>{run_id}</article>",
                public_path="briefs/algolia/constructor.html",
            ),
            _write_artifact(
                source_dir / "package-verdict.json",
                json.dumps(
                    {
                        "schema_version": 1,
                        "gate": "hermes_package_contract",
                        "run_id": run_id,
                        "generated_at": GENERATED_AT.isoformat(),
                        "status": "pass",
                        "exit_code": 0,
                        "checks": {"required_contract": True},
                    }
                ),
                public_path="verdicts/hermes-package-contract.json",
                media_type="application/json",
            ),
            _status_artifact(source_dir, run_id, publish_status),
        )
    else:
        artifacts = (
            _write_artifact(source_dir / "index.html", f"<main>{run_id}</main>"),
            _status_artifact(source_dir, run_id, publish_status),
        )
    return PublicationRequest(
        identity=RunIdentity(run_id=run_id, tenant_slug="algolia"),
        kind=kind,
        generated_at=GENERATED_AT,
        artifacts=artifacts,
    )


def test_store_publishes_decision_as_immutable_generation_and_shared_routes(tmp_path: Path) -> None:
    store = _store(tmp_path / "store")
    request = _request(
        tmp_path / "decision-source",
        "cios-20260714T090000Z-100",
        PublicationKind.DECISION,
    )

    result = store.publish(request)

    assert result.status == "published"
    assert (tmp_path / "store" / "current").readlink() == Path(
        "releases/cios-20260714T090000Z-100"
    )
    assert (tmp_path / "store" / "served" / "index.html").resolve().read_text(
        encoding="utf-8"
    ) == "<main>cios-20260714T090000Z-100</main>"
    root_status = tmp_path / "store" / "served" / "data" / "argus-latest-run-status.json"
    v2_status = tmp_path / "store" / "served" / "v2" / "data" / "argus-latest-run-status.json"
    assert root_status.resolve() == v2_status.resolve()
    assert json.loads(root_status.read_text(encoding="utf-8"))["run_id"] == request.identity.run_id
    for relative_path in (
        "index.html",
        "brief.html",
        "data/semantic-dashboard.json",
        "data/argus-data-plane-manifest.json",
        "data/argus-demand-plan-template.csv",
        "data/argus-demand-work-order-guide.json",
        "publication-manifest.json",
        "briefs/algolia/constructor.html",
    ):
        root_artifact = tmp_path / "store" / "served" / relative_path
        v2_artifact = tmp_path / "store" / "served" / "v2" / relative_path
        assert root_artifact.resolve() == v2_artifact.resolve()
        assert root_artifact.is_file()
    assert (tmp_path / "store" / "releases" / request.identity.run_id / "publication-manifest.json").is_file()


def test_store_rejects_preexisting_wrong_router_link(tmp_path: Path) -> None:
    root = tmp_path / "store"
    (root / "served").mkdir(parents=True)
    (root / "served" / "index.html").symlink_to("../../wrong/index.html")
    request = _request(
        tmp_path / "source",
        "cios-20260714T090000Z-router-tamper",
        PublicationKind.DECISION,
    )

    with pytest.raises(PublicationValidationError, match="router link mismatch"):
        _store(root).publish(request)

    assert not (root / "current").exists()


def test_store_rejects_symlinked_generation_bucket(tmp_path: Path) -> None:
    root = tmp_path / "store"
    outside = tmp_path / "outside"
    outside.mkdir()
    root.mkdir()
    (root / "releases").symlink_to(outside, target_is_directory=True)
    request = _request(
        tmp_path / "source",
        "cios-20260714T090000Z-bucket-tamper",
        PublicationKind.DECISION,
    )

    with pytest.raises(PublicationValidationError, match="store path must be a real directory"):
        _store(root).publish(request)

    assert list(outside.iterdir()) == []


def test_store_takes_exclusive_process_lock_for_publish(tmp_path: Path, monkeypatch) -> None:
    calls: list[int] = []
    real_flock = fcntl.flock

    def recording_flock(fd: int, operation: int) -> None:
        calls.append(operation)
        real_flock(fd, operation)

    monkeypatch.setattr("cios.publication.store.fcntl.flock", recording_flock)
    request = _request(
        tmp_path / "source",
        "cios-20260714T090000Z-lock",
        PublicationKind.DECISION,
    )

    _store(tmp_path / "store").publish(request)

    assert calls == [fcntl.LOCK_EX, fcntl.LOCK_UN]


def test_store_blocked_diagnostic_preserves_current_decision(tmp_path: Path) -> None:
    store = _store(tmp_path / "store")
    decision = _request(
        tmp_path / "decision-source",
        "cios-20260714T090000Z-100",
        PublicationKind.DECISION,
    )
    diagnostic = _request(
        tmp_path / "diagnostic-source",
        "cios-20260714T091500Z-200",
        PublicationKind.DIAGNOSTIC,
    )
    store.publish(decision)

    result = store.publish(diagnostic)

    assert result.status == "blocked"
    assert (tmp_path / "store" / "current").readlink() == Path(
        "releases/cios-20260714T090000Z-100"
    )
    assert (tmp_path / "store" / "latest-diagnostics").readlink() == Path(
        "diagnostics/cios-20260714T091500Z-200"
    )
    served = tmp_path / "store" / "served"
    assert served.joinpath("index.html").resolve().read_text(encoding="utf-8") == (
        "<main>cios-20260714T090000Z-100</main>"
    )
    assert json.loads(
        served.joinpath("data/argus-latest-run-status.json").read_text(encoding="utf-8")
    )["run_id"] == diagnostic.identity.run_id


def test_store_incomplete_decision_fails_before_install_or_pointer(tmp_path: Path) -> None:
    store = _store(tmp_path / "store")
    run_id = "cios-20260714T090000Z-incomplete"
    request = PublicationRequest(
        identity=RunIdentity(run_id=run_id, tenant_slug="algolia"),
        kind=PublicationKind.DECISION,
        generated_at=GENERATED_AT,
        artifacts=(
            _write_artifact(tmp_path / "source/index.html", "<main>partial</main>"),
            _status_artifact(tmp_path / "source", run_id, "published"),
        ),
    )

    with pytest.raises(PublicationValidationError, match="missing required artifact"):
        store.publish(request)

    assert not (tmp_path / "store" / "current").exists()
    assert not (tmp_path / "store" / "latest-status.json").exists()
    assert not (tmp_path / "store" / "releases" / run_id).exists()


def test_store_status_replace_failure_restores_prior_decision_and_status(tmp_path: Path) -> None:
    root = tmp_path / "store"
    first = _request(
        tmp_path / "first-source",
        "cios-20260714T090000Z-first",
        PublicationKind.DECISION,
    )
    second = _request(
        tmp_path / "second-source",
        "cios-20260714T090500Z-second",
        PublicationKind.DECISION,
    )
    _store(root).publish(first)
    prior_status = (root / "latest-status.json").read_bytes()
    file_ops = FailLatestStatusFileOps()
    failing_store = PublicationStore(
        root,
        validation_policy=GenerationValidationPolicy(
            now=GENERATED_AT + timedelta(minutes=5),
            max_age_seconds=600,
        ),
        file_ops=file_ops,
    )

    with pytest.raises(OSError, match="injected status replace failure"):
        failing_store.publish(second)

    assert file_ops.targets.index("current") < file_ops.targets.index("latest-status.json")
    assert (root / "current").readlink() == Path("releases/cios-20260714T090000Z-first")
    assert (root / "latest-status.json").read_bytes() == prior_status
    assert not (root / "releases" / second.identity.run_id).exists()


def test_store_replaces_caller_safety_claim_with_scanner_verdict(tmp_path: Path) -> None:
    root = tmp_path / "store"
    request = _request(
        tmp_path / "source",
        "cios-20260714T090000Z-derived-safety",
        PublicationKind.DECISION,
    )
    status_source = tmp_path / "source" / "argus-latest-run-status.json"
    status = json.loads(status_source.read_text(encoding="utf-8"))
    status["safety"] = {
        "version": 1,
        "artifact_paths_redacted": False,
        "secret_values_included": True,
        "public_safe": False,
    }
    status_source.write_text(json.dumps(status), encoding="utf-8")

    _store(root).publish(request)

    published = json.loads((root / "latest-status.json").read_text(encoding="utf-8"))
    assert published["safety"] == {
        "version": 1,
        "artifact_paths_redacted": True,
        "secret_values_included": False,
        "public_safe": True,
    }
