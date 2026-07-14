#!/usr/bin/env python3
"""Publish one immutable, validated CI-OS public generation."""

from __future__ import annotations

import argparse
import json
import os
import sys
from tempfile import TemporaryDirectory
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

from pydantic import SecretStr

from cios.publication.store import PublicationStore
from cios.publication.generation import PublicationValidationError
from cios.publication.scanner import LOCAL_PATH_MARKERS
from cios.publication.types import (
    ArtifactSpec,
    GenerationValidationPolicy,
    PublicationKind,
    PublicationRequest,
    RunIdentity,
    SafetyPolicy,
)


SENSITIVE_ENV_MARKERS = ("KEY", "TOKEN", "SECRET", "PASSWORD", "DATABASE_URL", "DSN")


def _aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must include a timezone")
    return parsed


def _media_type(path: Path) -> str:
    return {
        ".csv": "text/csv",
        ".html": "text/html",
        ".json": "application/json",
        ".txt": "text/plain",
    }.get(path.suffix.lower(), "application/octet-stream")


_REDACTED = object()


def _contains_local_path(value: str) -> bool:
    return any(marker in value for marker in LOCAL_PATH_MARKERS)


def _redact_local_paths(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in cast(dict[object, object], value).items():
            if _contains_local_path(str(key)):
                continue
            public_item = _redact_local_paths(item)
            if public_item is not _REDACTED:
                redacted[str(key)] = public_item
        return redacted
    if isinstance(value, list):
        items: list[Any] = []
        for item in cast(list[object], value):
            public_item = _redact_local_paths(item)
            if public_item is not _REDACTED:
                items.append(public_item)
        return items
    if isinstance(value, str) and _contains_local_path(value):
        return _REDACTED
    return value


def _public_json_copy(source: Path, public_path: str, transform_root: Path) -> Path:
    if source.is_symlink() or not source.is_file():
        raise PublicationValidationError(f"artifact source is not a regular file: {source.name}")
    payload = json.loads(source.read_text(encoding="utf-8"))
    public_payload = _redact_local_paths(payload)
    if public_payload is _REDACTED:
        raise PublicationValidationError(f"artifact has no public payload: {source.name}")
    target = transform_root / public_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{json.dumps(public_payload, indent=2, sort_keys=True)}\n", encoding="utf-8")
    return target


def _artifact(
    source: Path | None,
    public_path: str,
    *,
    transform_root: Path | None = None,
) -> ArtifactSpec | None:
    if source is None:
        return None
    media_type = _media_type(source)
    public_source = (
        _public_json_copy(source, public_path, transform_root)
        if media_type == "application/json" and transform_root is not None
        else source
    )
    return ArtifactSpec(
        source_path=public_source,
        public_path=public_path,
        media_type=media_type,
    )


def _artifacts(
    args: argparse.Namespace,
    *,
    transform_root: Path | None = None,
) -> tuple[ArtifactSpec, ...]:
    artifacts: list[ArtifactSpec] = []
    candidates = [
        _artifact(args.status, "data/argus-latest-run-status.json", transform_root=transform_root),
        _artifact(args.demand_plan_template, "data/argus-demand-plan-template.csv"),
        _artifact(
            args.demand_work_order_guide,
            "data/argus-demand-work-order-guide.json",
            transform_root=transform_root,
        ),
        _artifact(
            args.package_verdict,
            "verdicts/hermes-package-contract.json",
            transform_root=transform_root,
        ),
    ]
    if args.kind == PublicationKind.DECISION.value:
        candidates.extend(
            [
                _artifact(args.dashboard_html, "index.html"),
                _artifact(args.brief, "brief.html"),
                _artifact(
                    args.dashboard_json,
                    "data/semantic-dashboard.json",
                    transform_root=transform_root,
                ),
                _artifact(
                    args.data_plane_manifest,
                    "data/argus-data-plane-manifest.json",
                    transform_root=transform_root,
                ),
            ]
        )
        if args.briefs_dir is not None:
            for source in sorted(args.briefs_dir.rglob("*")):
                if source.is_file() or source.is_symlink():
                    relative = source.relative_to(args.briefs_dir).as_posix()
                    candidates.append(_artifact(source, f"briefs/{relative}"))
    artifacts.extend(candidate for candidate in candidates if candidate is not None)
    return tuple(artifacts)


def _safety_policy(environ: dict[str, str]) -> SafetyPolicy:
    values = tuple(
        value
        for name, value in environ.items()
        if value
        and len(value) >= 8
        and any(marker in name.upper() for marker in SENSITIVE_ENV_MARKERS)
    )
    return SafetyPolicy(secret_values=tuple(SecretStr(value) for value in values))


def _write_verdict(
    output: Path,
    *,
    run_id: str,
    status: str,
    manifest_sha256: str | None = None,
) -> None:
    passed = status == "pass"
    payload: dict[str, Any] = {
        "schema_version": 1,
        "gate": "publication_integrity",
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": status,
        "exit_code": 0 if passed else 2,
        "checks": {
            "generation_validated": passed,
            "pointer_promoted": passed,
            "status_committed": passed,
        },
    }
    if manifest_sha256:
        payload["manifest_sha256"] = manifest_sha256
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"{json.dumps(payload, indent=2, sort_keys=True)}\n", encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a validated CI-OS generation.")
    parser.add_argument("--store-root", type=Path, required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--tenant", required=True)
    parser.add_argument("--kind", choices=("decision", "diagnostic"), required=True)
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--dashboard-html", type=Path)
    parser.add_argument("--brief", type=Path)
    parser.add_argument("--dashboard-json", type=Path)
    parser.add_argument("--data-plane-manifest", type=Path)
    parser.add_argument("--briefs-dir", type=Path)
    parser.add_argument("--demand-plan-template", type=Path)
    parser.add_argument("--demand-work-order-guide", type=Path)
    parser.add_argument("--package-verdict", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--now", help="Optional aware ISO timestamp for deterministic validation.")
    parser.add_argument("--max-age-seconds", type=int, default=3600)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        status_payload = json.loads(args.status.read_text(encoding="utf-8"))
        generated_at = _aware_datetime(str(status_payload["generated_at"]))
        now = _aware_datetime(args.now) if args.now else datetime.now(timezone.utc)
        with TemporaryDirectory(prefix="cios-publication-") as directory:
            request = PublicationRequest(
                identity=RunIdentity(run_id=args.run_id, tenant_slug=args.tenant),
                kind=PublicationKind(args.kind),
                generated_at=generated_at,
                artifacts=_artifacts(args, transform_root=Path(directory)),
            )
            result = PublicationStore(
                args.store_root,
                validation_policy=GenerationValidationPolicy(
                    now=now,
                    max_age_seconds=args.max_age_seconds,
                    safety=_safety_policy(dict(os.environ)),
                ),
            ).publish(request)
    except Exception as exc:  # noqa: BLE001 - always emit a terminal verdict.
        _write_verdict(args.output, run_id=args.run_id, status="fail")
        print(f"publication integrity failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    _write_verdict(
        args.output,
        run_id=args.run_id,
        status="pass",
        manifest_sha256=result.manifest_sha256,
    )
    print(args.output.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
