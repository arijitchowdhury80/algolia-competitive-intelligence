"""Validated data contracts for CI-OS publication."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator


IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"
TENANT_PATTERN = r"^[a-z0-9][a-z0-9-]{0,62}$"


class RunIdentity(BaseModel):
    """Identity shared by one CI-OS execution and its artifacts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    tenant_slug: str = Field(pattern=TENANT_PATTERN)


class PublicationKind(StrEnum):
    """Public generation behavior."""

    DECISION = "decision"
    DIAGNOSTIC = "diagnostic"


class ArtifactSpec(BaseModel):
    """One source file and its destination in a public generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    source_path: Path
    public_path: str = Field(min_length=1, max_length=240)
    media_type: str = Field(min_length=1, max_length=120)

    @field_validator("public_path")
    @classmethod
    def validate_public_path(cls, value: str) -> str:
        """Reject absolute, traversing, or noncanonical public paths."""
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or str(path) != value or value.startswith("."):
            raise ValueError("public_path must be a canonical relative path")
        return value


class PublicationRequest(BaseModel):
    """Validated request for one immutable public generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    identity: RunIdentity
    kind: PublicationKind
    generated_at: AwareDatetime
    artifacts: tuple[ArtifactSpec, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_duplicate_paths(self) -> "PublicationRequest":
        """Require one source for every public path."""
        paths = [artifact.public_path for artifact in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate public_path")
        return self


class ArtifactRecord(BaseModel):
    """Content binding for one file in an immutable generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    path: str
    media_type: str
    bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        """Require a canonical relative content-manifest path."""
        path = PurePosixPath(value)
        if path.is_absolute() or ".." in path.parts or str(path) != value or value.startswith("."):
            raise ValueError("path must be a canonical relative path")
        return value


class SafetyVerdict(BaseModel):
    """Derived public-artifact safety result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    artifact_paths_redacted: bool
    secret_values_included: bool
    public_safe: bool


class SafetyPolicy(BaseModel):
    """Sensitive values and bounds used by the artifact scanner."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    secret_values: tuple[SecretStr, ...] = ()


class GenerationValidationPolicy(BaseModel):
    """Freshness, required paths, and safety rules for final validation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = 1
    now: AwareDatetime
    max_age_seconds: int = Field(default=3600, gt=0, le=86400)
    max_future_skew_seconds: int = Field(default=60, ge=0, le=3600)
    safety: SafetyPolicy = Field(default_factory=SafetyPolicy)


class PublicationManifest(BaseModel):
    """Canonical content manifest for one public generation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    tenant_slug: str = Field(pattern=TENANT_PATTERN)
    kind: PublicationKind
    generated_at: AwareDatetime
    files: tuple[ArtifactRecord, ...] = Field(min_length=1)
    safety: SafetyVerdict


class PublicRunStatus(BaseModel):
    """Required public status fields validated before status-last promotion."""

    model_config = ConfigDict(extra="allow", frozen=True)

    schema_version: Literal[2]
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    tenant_slug: str = Field(pattern=TENANT_PATTERN)
    generated_at: AwareDatetime
    publish_status: Literal["blocked", "published"]
    status: str = Field(min_length=1, max_length=120)
    public_dashboard_updated: bool
    safety: SafetyVerdict

    @model_validator(mode="after")
    def validate_publish_semantics(self) -> "PublicRunStatus":
        """Keep the dashboard-updated flag bound to publication status."""
        expected = self.publish_status == "published"
        if self.public_dashboard_updated is not expected:
            raise ValueError("public_dashboard_updated contradicts publish_status")
        return self


class PublicationResult(BaseModel):
    """Structured result of one immutable publication attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    status: Literal["blocked", "published"]
    generation_path: Path
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
