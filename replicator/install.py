"""Guarded live-root install helpers for generated drafts."""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from replicator.stage import SUPPORTED_STAGE_TARGETS, discover_skill_files, provider_draft_root


@dataclass(frozen=True)
class InstallRecord:
    source_path: str
    target_path: str
    backup_path: str | None
    status: str
    reason: str


def backup_root_for(live_root: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return live_root / "replicator-backups" / stamp


def install_draft(
    draft_root: Path,
    live_root: Path,
    target_provider: str,
    *,
    force: bool = False,
) -> dict[str, object]:
    if target_provider not in SUPPORTED_STAGE_TARGETS:
        raise ValueError(f"unsupported install target: {target_provider}")

    source_provider_root = provider_draft_root(draft_root, target_provider)
    skill_files = discover_skill_files(source_provider_root)
    backup_root = backup_root_for(live_root)
    installed: list[InstallRecord] = []
    skipped: list[InstallRecord] = []

    for source_path in skill_files:
        relative_path = source_path.relative_to(source_provider_root)
        target_path = live_root / relative_path
        if target_path.exists() and not force:
            skipped.append(
                InstallRecord(
                    source_path=str(source_path),
                    target_path=str(target_path),
                    backup_path=None,
                    status="skipped",
                    reason="Target exists; rerun with --force to replace after backup.",
                )
            )
            continue

        backup_path: Path | None = None
        if target_path.exists():
            backup_path = backup_root / relative_path
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(target_path, backup_path)

        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_path, target_path)
        installed.append(
            InstallRecord(
                source_path=str(source_path),
                target_path=str(target_path),
                backup_path=str(backup_path) if backup_path else None,
                status="installed",
                reason="Installed draft skill into explicit live root.",
            )
        )

        notes_path = source_path.parent / "MIGRATION_NOTES.md"
        if notes_path.is_file():
            notes_target_path = target_path.parent / "MIGRATION_NOTES.md"
            notes_backup_path: Path | None = None
            if notes_target_path.exists() and force:
                notes_backup_path = backup_root / notes_target_path.relative_to(live_root)
                notes_backup_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(notes_target_path, notes_backup_path)
            if not notes_target_path.exists() or force:
                shutil.copyfile(notes_path, notes_target_path)
                installed.append(
                    InstallRecord(
                        source_path=str(notes_path),
                        target_path=str(notes_target_path),
                        backup_path=str(notes_backup_path) if notes_backup_path else None,
                        status="installed",
                        reason="Installed draft migration notes into explicit live root.",
                    )
                )

    if not skill_files:
        skipped.append(
            InstallRecord(
                source_path=str(source_provider_root / "skills"),
                target_path="",
                backup_path=None,
                status="skipped",
                reason="No draft skills were found to install.",
            )
        )

    discovered_skills = [path.parent.name for path in discover_skill_files(live_root)]
    manifest = {
        "schema": "replicator.install_manifest.v1",
        "target_provider": target_provider,
        "draft_root": str(draft_root),
        "live_root": str(live_root),
        "backup_root": str(backup_root),
        "force": force,
        "installed_count": len(installed),
        "skipped_count": len(skipped),
        "discovery": {
            "passed": bool(discovered_skills),
            "skill_count": len(discovered_skills),
            "skills": discovered_skills,
        },
        "safety": {
            "explicit_live_root_required": True,
            "credentials_copied": False,
            "scripts_executed": False,
            "backup_created_for_replaced_files": any(item.backup_path for item in installed),
        },
        "installed": [asdict(item) for item in installed],
        "skipped": [asdict(item) for item in skipped],
    }
    manifest_path = live_root / "replicator-install-manifest.json"
    live_root.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest

