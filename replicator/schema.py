"""Resonance Bundle v1 schema helpers."""

from __future__ import annotations

import hashlib
import os
import platform
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Protocol


SCHEMA_ID = "replicator.resonance_bundle.v1"


class ArtifactLike(Protocol):
    provider: str
    path: str
    artifact_type: str
    classification: str
    reason: str
    target_notes: str
    contains_secret_reference: bool


@dataclass(frozen=True)
class SourceMetadata:
    provider_count: int
    providers: list[str]
    root_override: str | None
    max_depth: int | None
    include_hidden: bool
    ignore_cache: bool
    platform: str


@dataclass(frozen=True)
class BundleArtifact:
    artifact_id: str
    provider: str
    path: str
    artifact_type: str
    classification: str
    reason: str
    target_notes: str
    contains_secret_reference: bool
    checksum_sha256: str | None
    checksum_status: str


@dataclass(frozen=True)
class SkippedSecret:
    artifact_id: str
    provider: str
    path: str
    reason: str
    target_notes: str


def stable_artifact_id(provider: str, path: str, artifact_type: str) -> str:
    payload = f"{provider}\0{path}\0{artifact_type}".encode("utf-8", errors="surrogateescape")
    return f"artifact_{hashlib.sha256(payload).hexdigest()[:16]}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def checksum_for_artifact(artifact: ArtifactLike) -> tuple[str | None, str]:
    if artifact.contains_secret_reference:
        return None, "skipped_secret"
    path = Path(artifact.path)
    if not path.exists():
        return None, "missing"
    if not path.is_file():
        return None, "not_file"
    try:
        return file_sha256(path), "ok"
    except OSError:
        return None, "unreadable"


def bundle_artifact(artifact: ArtifactLike) -> BundleArtifact:
    checksum, checksum_status = checksum_for_artifact(artifact)
    return BundleArtifact(
        artifact_id=stable_artifact_id(artifact.provider, artifact.path, artifact.artifact_type),
        provider=artifact.provider,
        path=artifact.path,
        artifact_type=artifact.artifact_type,
        classification=artifact.classification,
        reason=artifact.reason,
        target_notes=artifact.target_notes,
        contains_secret_reference=artifact.contains_secret_reference,
        checksum_sha256=checksum,
        checksum_status=checksum_status,
    )


def skipped_secret_from_artifact(artifact: BundleArtifact) -> SkippedSecret:
    return SkippedSecret(
        artifact_id=artifact.artifact_id,
        provider=artifact.provider,
        path=artifact.path,
        reason=artifact.reason,
        target_notes=artifact.target_notes,
    )


def source_metadata(
    artifacts: Iterable[ArtifactLike],
    *,
    root_override: Path | None,
    max_depth: int | None,
    include_hidden: bool,
    ignore_cache: bool,
) -> SourceMetadata:
    providers = sorted({artifact.provider for artifact in artifacts})
    return SourceMetadata(
        provider_count=len(providers),
        providers=providers,
        root_override=str(root_override) if root_override is not None else None,
        max_depth=max_depth,
        include_hidden=include_hidden,
        ignore_cache=ignore_cache,
        platform=f"{platform.system()} {platform.release()}".strip(),
    )


def build_bundle_payload(
    *,
    version: str,
    artifacts: list[ArtifactLike],
    summary: dict[str, object],
    root_override: Path | None,
    max_depth: int | None,
    include_hidden: bool,
    ignore_cache: bool,
) -> dict[str, object]:
    bundle_artifacts = [bundle_artifact(artifact) for artifact in artifacts]
    skipped_secrets = [
        skipped_secret_from_artifact(artifact)
        for artifact in bundle_artifacts
        if artifact.contains_secret_reference
    ]
    return {
        "schema": SCHEMA_ID,
        "schema_version": "1.0.0",
        "replicator_version": version,
        "source_metadata": asdict(
            source_metadata(
                artifacts,
                root_override=root_override,
                max_depth=max_depth,
                include_hidden=include_hidden,
                ignore_cache=ignore_cache,
            )
        ),
        "artifact_count": len(bundle_artifacts),
        "summary": summary,
        "skipped_secrets": [asdict(secret) for secret in skipped_secrets],
        "artifacts": [asdict(artifact) for artifact in bundle_artifacts],
    }


def validate_bundle_payload(payload: dict[str, object]) -> None:
    required = {
        "schema",
        "schema_version",
        "replicator_version",
        "source_metadata",
        "artifact_count",
        "summary",
        "skipped_secrets",
        "artifacts",
    }
    missing = sorted(required - set(payload))
    if missing:
        raise ValueError(f"bundle missing required field(s): {', '.join(missing)}")
    if payload["schema"] != SCHEMA_ID:
        raise ValueError(f"unexpected schema: {payload['schema']}")
    if not isinstance(payload["artifacts"], list):
        raise ValueError("bundle artifacts must be a list")
    if not isinstance(payload["skipped_secrets"], list):
        raise ValueError("bundle skipped_secrets must be a list")

