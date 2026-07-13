"""Command boundary for Scout product-market exports.

CI-OS treats Scout as an external acquisition package. This adapter executes a
configured Scout command, requires a declared export artifact, and parses that
artifact into rows consumed by the product-market payload builder.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .importers import load_export_records


class ScoutExecutionError(RuntimeError):
    """Raised when a Scout export command cannot produce a usable artifact."""


class ScoutCommandSpec(BaseModel):
    """A bounded Scout command and the artifact CI-OS expects it to produce."""

    command: list[str] = Field(min_length=1)
    output_path: Path
    timeout_seconds: float = Field(gt=0)
    cwd: Path | None = None

    @model_validator(mode="after")
    def _require_output_path(self) -> "ScoutCommandSpec":
        if not str(self.output_path).strip():
            raise ValueError("ScoutCommandSpec requires output_path")
        return self


def run_scout_export(spec: ScoutCommandSpec) -> list[dict[str, Any]]:
    """Run Scout and return parsed export records.

    The command is intentionally generic so CI-OS can call either local Scout,
    a wrapper script, or a future Hermes-owned command without importing Scout
    internals.
    """

    try:
        completed = subprocess.run(
            spec.command,
            cwd=spec.cwd,
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ScoutExecutionError(
            f"Scout command timed out after {spec.timeout_seconds:g}s"
        ) from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        suffix = f": {stderr}" if stderr else ""
        raise ScoutExecutionError(
            f"Scout command failed with exit code {completed.returncode}{suffix}"
        )

    if not spec.output_path.exists():
        raise ScoutExecutionError(
            f"Scout command did not create expected output: {spec.output_path}"
        )

    return load_export_records(spec.output_path)


__all__ = ["ScoutCommandSpec", "ScoutExecutionError", "run_scout_export"]
