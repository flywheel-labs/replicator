"""Stage generated drafts into isolated provider-like directories."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


SUPPORTED_STAGE_TARGETS = {"claude", "codex"}


@dataclass(frozen=True)
class StagedFile:
    source_path: str
    staged_path: str
    status: str
    reason: str


def provider_draft_root(draft_root: Path, provider: str) -> Path:
    if (draft_root / provider).is_dir():
        return draft_root / provider
    return draft_root


def discover_skill_files(provider_root: Path) -> list[Path]:
    skills_root = provider_root / "skills"
    if not skills_root.is_dir():
        return []
    return sorted(skills_root.glob("*/SKILL.md"))


def discover_mcp_files(provider_root: Path) -> list[Path]:
    mcp_root = provider_root / "mcp"
    if not mcp_root.is_dir():
        return []
    return sorted(
        path
        for path in mcp_root.glob("*/*")
        if path.is_file() and path.name != "MIGRATION_NOTES.md"
    )


def stage_draft(draft_root: Path, staging_root: Path, target_provider: str) -> dict[str, object]:
    if target_provider not in SUPPORTED_STAGE_TARGETS:
        raise ValueError(f"unsupported stage target: {target_provider}")

    source_provider_root = provider_draft_root(draft_root, target_provider)
    staged_provider_root = staging_root / target_provider
    staged_files: list[StagedFile] = []
    skipped: list[StagedFile] = []

    skill_files = discover_skill_files(source_provider_root)
    for source_path in skill_files:
        relative_path = source_path.relative_to(source_provider_root)
        staged_path = staged_provider_root / relative_path
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, staged_path)
        staged_files.append(
            StagedFile(
                source_path=str(source_path),
                staged_path=str(staged_path),
                status="staged",
                reason="Copied draft skill into isolated staging root.",
            )
        )

        notes_path = source_path.parent / "MIGRATION_NOTES.md"
        if notes_path.is_file():
            staged_notes_path = staged_path.parent / "MIGRATION_NOTES.md"
            shutil.copyfile(notes_path, staged_notes_path)
            staged_files.append(
                StagedFile(
                    source_path=str(notes_path),
                    staged_path=str(staged_notes_path),
                    status="staged",
                    reason="Copied draft migration notes into isolated staging root.",
                )
            )

    if not skill_files:
        skipped.append(
            StagedFile(
                source_path=str(source_provider_root / "skills"),
                staged_path="",
                status="skipped",
                reason="No draft skills were found to stage.",
            )
        )

    mcp_files = discover_mcp_files(source_provider_root)
    for source_path in mcp_files:
        relative_path = source_path.relative_to(source_provider_root)
        staged_path = staged_provider_root / relative_path
        staged_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, staged_path)
        staged_files.append(
            StagedFile(
                source_path=str(source_path),
                staged_path=str(staged_path),
                status="staged",
                reason="Copied draft MCP config into isolated staging root for manual review.",
            )
        )

        notes_path = source_path.parent / "MIGRATION_NOTES.md"
        if notes_path.is_file():
            staged_notes_path = staged_path.parent / "MIGRATION_NOTES.md"
            shutil.copyfile(notes_path, staged_notes_path)
            staged_files.append(
                StagedFile(
                    source_path=str(notes_path),
                    staged_path=str(staged_notes_path),
                    status="staged",
                    reason="Copied draft MCP migration notes into isolated staging root.",
                )
            )

    discovered_skills = [path.parent.name for path in discover_skill_files(staged_provider_root)]
    discovered_mcp = [path.parent.name for path in discover_mcp_files(staged_provider_root)]
    manifest = {
        "schema": "replicator.stage_manifest.v1",
        "target_provider": target_provider,
        "draft_root": str(draft_root),
        "staging_root": str(staging_root),
        "staged_provider_root": str(staged_provider_root),
        "staged_count": len(staged_files),
        "skipped_count": len(skipped),
        "discovery": {
            "passed": bool(discovered_skills or discovered_mcp),
            "skill_count": len(discovered_skills),
            "skills": discovered_skills,
            "mcp_count": len(discovered_mcp),
            "mcp": discovered_mcp,
        },
        "safety": {
            "live_provider_config_written": False,
            "credentials_copied": False,
            "scripts_executed": False,
        },
        "staged_files": [asdict(item) for item in staged_files],
        "skipped": [asdict(item) for item in skipped],
    }
    manifest_path = staged_provider_root / "stage-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest
