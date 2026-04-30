"""Read-only validation helpers for staged or installed provider roots."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from replicator.stage import SUPPORTED_STAGE_TARGETS, discover_mcp_files, discover_skill_files


@dataclass(frozen=True)
class ValidationFinding:
    severity: str
    path: str
    message: str


def _read_json(path: Path, findings: list[ValidationFinding]) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(path),
                message=f"Manifest could not be read as JSON: {exc}",
            )
        )
        return None


def _non_empty_file(path: Path, findings: list[ValidationFinding], label: str) -> bool:
    if not path.is_file():
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(path),
                message=f"Missing {label}.",
            )
        )
        return False
    try:
        if not path.read_text(encoding="utf-8").strip():
            findings.append(
                ValidationFinding(
                    severity="error",
                    path=str(path),
                    message=f"{label} is empty.",
                )
            )
            return False
    except OSError as exc:
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(path),
                message=f"{label} is unreadable: {exc}",
            )
        )
        return False
    return True


def _validate_stage_manifest(
    provider_root: Path,
    manifest: dict[str, Any] | None,
    findings: list[ValidationFinding],
) -> dict[str, Any] | None:
    if manifest is None:
        return None
    staged_files = manifest.get("staged_files", [])
    missing = []
    for item in staged_files:
        staged_path = Path(str(item.get("staged_path", "")))
        if not staged_path.is_file():
            missing.append(str(staged_path))
    if missing:
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(provider_root / "stage-manifest.json"),
                message=f"Stage manifest references missing staged files: {len(missing)}.",
            )
        )
    if manifest.get("staged_count") != len(staged_files):
        findings.append(
            ValidationFinding(
                severity="warning",
                path=str(provider_root / "stage-manifest.json"),
                message="Stage manifest staged_count does not match staged_files length.",
            )
        )
    return {
        "path": str(provider_root / "stage-manifest.json"),
        "schema": manifest.get("schema"),
        "declared_count": manifest.get("staged_count"),
        "referenced_count": len(staged_files),
        "missing_referenced_count": len(missing),
    }


def _validate_install_manifest(
    provider_root: Path,
    manifest: dict[str, Any] | None,
    findings: list[ValidationFinding],
) -> dict[str, Any] | None:
    if manifest is None:
        return None
    installed = manifest.get("installed", [])
    missing = []
    for item in installed:
        target_path = Path(str(item.get("target_path", "")))
        if not target_path.is_file():
            missing.append(str(target_path))
    if missing:
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(provider_root / "replicator-install-manifest.json"),
                message=f"Install manifest references missing installed files: {len(missing)}.",
            )
        )
    if manifest.get("installed_count") != len(installed):
        findings.append(
            ValidationFinding(
                severity="warning",
                path=str(provider_root / "replicator-install-manifest.json"),
                message="Install manifest installed_count does not match installed list length.",
            )
        )
    return {
        "path": str(provider_root / "replicator-install-manifest.json"),
        "schema": manifest.get("schema"),
        "declared_count": manifest.get("installed_count"),
        "referenced_count": len(installed),
        "missing_referenced_count": len(missing),
    }


def _validate_restore_manifest(
    provider_root: Path,
    manifest: dict[str, Any] | None,
    findings: list[ValidationFinding],
) -> dict[str, Any] | None:
    if manifest is None:
        return None
    restored = manifest.get("restored", [])
    missing = []
    for item in restored:
        target_path = Path(str(item.get("target_path", "")))
        if not target_path.is_file():
            missing.append(str(target_path))
    if missing:
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(provider_root / "replicator-restore-manifest.json"),
                message=f"Restore manifest references missing restored files: {len(missing)}.",
            )
        )
    return {
        "path": str(provider_root / "replicator-restore-manifest.json"),
        "schema": manifest.get("schema"),
        "declared_count": manifest.get("restored_count"),
        "referenced_count": len(restored),
        "missing_referenced_count": len(missing),
    }


def validate_root(provider_root: Path, target_provider: str) -> dict[str, Any]:
    if target_provider not in SUPPORTED_STAGE_TARGETS:
        raise ValueError(f"unsupported validation target: {target_provider}")

    findings: list[ValidationFinding] = []
    provider_root = provider_root.expanduser()
    if not provider_root.exists():
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(provider_root),
                message="Provider root does not exist.",
            )
        )
    elif not provider_root.is_dir():
        findings.append(
            ValidationFinding(
                severity="error",
                path=str(provider_root),
                message="Provider root is not a directory.",
            )
        )

    skill_paths = discover_skill_files(provider_root)
    skills = []
    for skill_path in skill_paths:
        valid = _non_empty_file(skill_path, findings, "SKILL.md")
        notes_path = skill_path.parent / "MIGRATION_NOTES.md"
        skills.append(
            {
                "name": skill_path.parent.name,
                "path": str(skill_path),
                "valid": valid,
                "migration_notes_present": notes_path.is_file(),
            }
        )

    skills_root = provider_root / "skills"
    if skills_root.is_dir():
        for child in sorted(path for path in skills_root.iterdir() if path.is_dir()):
            if not (child / "SKILL.md").is_file():
                findings.append(
                    ValidationFinding(
                        severity="error",
                        path=str(child),
                        message="Skill directory is missing SKILL.md.",
                    )
                )

    mcp_paths = discover_mcp_files(provider_root)
    mcp = []
    for mcp_path in mcp_paths:
        valid = _non_empty_file(mcp_path, findings, "MCP config file")
        notes_path = mcp_path.parent / "MIGRATION_NOTES.md"
        mcp.append(
            {
                "name": mcp_path.parent.name,
                "path": str(mcp_path),
                "valid": valid,
                "migration_notes_present": notes_path.is_file(),
            }
        )

    stage_manifest = _read_json(provider_root / "stage-manifest.json", findings)
    install_manifest = _read_json(provider_root / "replicator-install-manifest.json", findings)
    restore_manifest = _read_json(provider_root / "replicator-restore-manifest.json", findings)
    manifests = {
        "stage": _validate_stage_manifest(provider_root, stage_manifest, findings),
        "install": _validate_install_manifest(provider_root, install_manifest, findings),
        "restore": _validate_restore_manifest(provider_root, restore_manifest, findings),
    }

    error_count = sum(1 for finding in findings if finding.severity == "error")
    warning_count = sum(1 for finding in findings if finding.severity == "warning")
    return {
        "schema": "replicator.validation.v1",
        "ok": error_count == 0,
        "target_provider": target_provider,
        "provider_root": str(provider_root),
        "summary": {
            "skill_count": len(skills),
            "mcp_count": len(mcp),
            "error_count": error_count,
            "warning_count": warning_count,
        },
        "skills": skills,
        "mcp": mcp,
        "manifests": manifests,
        "findings": [asdict(finding) for finding in findings],
        "safety": {
            "read_only": True,
            "credentials_copied": False,
            "scripts_executed": False,
            "live_provider_config_written": False,
        },
    }


def render_validation_report(payload: dict[str, Any]) -> str:
    summary = payload["summary"]
    lines = [
        "# Replicator Validation Report",
        "",
        f"- Schema: `{payload['schema']}`",
        f"- Target provider: `{payload['target_provider']}`",
        f"- Provider root: `{payload['provider_root']}`",
        f"- OK: `{str(payload['ok']).lower()}`",
        f"- Skills: `{summary['skill_count']}`",
        f"- MCP configs: `{summary['mcp_count']}`",
        f"- Errors: `{summary['error_count']}`",
        f"- Warnings: `{summary['warning_count']}`",
        "",
        "## Safety",
        "",
        "- Read-only validation only.",
        "- No credentials copied.",
        "- No scripts or MCP servers executed.",
        "- No live provider config written.",
        "",
        "## Skills",
        "",
    ]
    if payload["skills"]:
        for skill in payload["skills"]:
            lines.append(f"- `{skill['name']}`: `{skill['path']}`")
    else:
        lines.append("- None discovered.")
    lines.extend(["", "## MCP", ""])
    if payload["mcp"]:
        for item in payload["mcp"]:
            lines.append(f"- `{item['name']}`: `{item['path']}`")
    else:
        lines.append("- None discovered.")
    lines.extend(["", "## Findings", ""])
    if payload["findings"]:
        for finding in payload["findings"]:
            lines.append(f"- `{finding['severity']}` `{finding['path']}`: {finding['message']}")
    else:
        lines.append("- No validation findings.")
    lines.append("")
    return "\n".join(lines)
