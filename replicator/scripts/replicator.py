#!/usr/bin/env python3
"""Replicator: safe provider configuration inventory and Resonance Reports."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

VERSION = "0.2.0"

DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".replicator-output",
    ".replicator-output-smoke",
    ".replicator-output-v010",
    "__pycache__",
    "cache",
    "caches",
    "dist",
    "node_modules",
    "target",
}

SECRET_MARKERS = (
    "api_key",
    "apikey",
    "auth",
    "credential",
    "credentials",
    "keychain",
    "oauth",
    "refresh_token",
    "secret",
    "session",
    "token",
)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    display_name: str
    paths: tuple[str, ...]
    skill_markers: tuple[str, ...] = ()
    plugin_markers: tuple[str, ...] = ()
    mcp_markers: tuple[str, ...] = ()


@dataclass(frozen=True)
class Artifact:
    provider: str
    path: str
    artifact_type: str
    classification: str
    reason: str
    target_notes: str
    contains_secret_reference: bool


@dataclass(frozen=True)
class ScanOptions:
    root_override: Path | None = None
    max_depth: int | None = None
    include_hidden: bool = True
    ignore_cache: bool = True


PROVIDERS: dict[str, ProviderSpec] = {
    "claude": ProviderSpec(
        name="claude",
        display_name="Claude Code",
        paths=("~/.claude", "~/.claude.json"),
        skill_markers=("skills", "skill"),
        plugin_markers=("plugins", "plugin"),
        mcp_markers=("mcp",),
    ),
    "codex": ProviderSpec(
        name="codex",
        display_name="OpenAI Codex",
        paths=("~/.codex",),
        skill_markers=("skills", "skill"),
        plugin_markers=("plugins", "plugin"),
        mcp_markers=("mcp",),
    ),
    "openclaw": ProviderSpec(
        name="openclaw",
        display_name="OpenClaw",
        paths=("~/.openclaw",),
        skill_markers=("skills", "skill", "agents"),
        plugin_markers=("plugins", "plugin"),
        mcp_markers=("mcp",),
    ),
    "qwen": ProviderSpec(
        name="qwen",
        display_name="Qwen Code",
        paths=("~/.qwen", "~/.qwen-code", "~/.config/qwen"),
        skill_markers=("commands", "skills", "agents"),
        plugin_markers=("extensions", "plugins"),
        mcp_markers=("mcp",),
    ),
    "kimi": ProviderSpec(
        name="kimi",
        display_name="Kimi / Moonshot",
        paths=("~/.kimi", "~/.moonshot", "~/.config/kimi", "~/.config/moonshot"),
        skill_markers=("prompts", "skills", "agents"),
        plugin_markers=("plugins", "extensions"),
        mcp_markers=("mcp",),
    ),
}


def expand_path(raw: str, root_override: Path | None = None) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if root_override is not None and raw.startswith("~/"):
        return root_override / raw[2:]
    return expanded


def is_secret_path(path: Path) -> bool:
    lowered = str(path).lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def infer_artifact_type(path: Path, spec: ProviderSpec) -> str:
    lowered_parts = tuple(part.lower() for part in path.parts)
    name = path.name.lower()

    if is_secret_path(path):
        return "credential_reference"
    if any(marker in lowered_parts or marker in name for marker in spec.mcp_markers):
        return "mcp_config"
    if any(marker in lowered_parts or marker in name for marker in spec.skill_markers):
        return "skill_or_prompt"
    if any(marker in lowered_parts or marker in name for marker in spec.plugin_markers):
        return "plugin_or_extension"
    if name in {"settings.json", "config.json", "config.toml", "settings.toml"}:
        return "provider_settings"
    if path.suffix.lower() in {".md", ".txt"}:
        return "instruction_or_memory"
    if path.suffix.lower() in {".json", ".toml", ".yaml", ".yml"}:
        return "structured_config"
    if path.is_dir():
        return "config_directory"
    return "unknown"


def classify(path: Path, artifact_type: str) -> tuple[str, str, str, bool]:
    contains_secret = is_secret_path(path)

    if contains_secret:
        return (
            "not_portable",
            "Path appears to contain credentials, auth, session, token, or secret material.",
            "Recreate this credential manually in the receiving provider.",
            True,
        )
    if artifact_type == "mcp_config":
        return (
            "portable_with_edits",
            "MCP definitions are often portable, but command paths, env names, and permission models need review.",
            "Generate a draft and verify paths, env vars, and tool trust boundaries.",
            False,
        )
    if artifact_type == "skill_or_prompt":
        return (
            "portable_with_edits",
            "Skill/prompt instructions can usually be translated, but trigger semantics and bundled resources differ.",
            "Convert into the receiving provider's skill format and review instructions.",
            False,
        )
    if artifact_type == "plugin_or_extension":
        return (
            "manual_review",
            "Executable/plugin behavior is provider-specific and may have a different security model.",
            "Inspect manually before creating a receiving-provider draft.",
            False,
        )
    if artifact_type in {"instruction_or_memory", "structured_config", "provider_settings"}:
        return (
            "manual_review",
            "Configuration may be useful, but provider semantics differ.",
            "Review and copy only provider-agnostic instructions.",
            False,
        )
    if artifact_type == "config_directory":
        return (
            "manual_review",
            "Directory is a discovery root or nested config folder.",
            "Review child artifacts instead of copying the directory wholesale.",
            False,
        )
    return (
        "manual_review",
        "Unknown artifact type.",
        "Review manually before migration.",
        False,
    )


def should_skip_dir(path: Path, options: ScanOptions) -> bool:
    name = path.name
    lowered = name.lower()
    if options.ignore_cache and lowered in DEFAULT_EXCLUDED_DIRS:
        return True
    if options.ignore_cache and ("cache" in lowered or lowered in {"logs", "tmp", "temp"}):
        return True
    if not options.include_hidden and name.startswith("."):
        return True
    return False


def depth_from_root(root: Path, path: Path) -> int:
    try:
        relative = path.relative_to(root)
    except ValueError:
        return 0
    if str(relative) == ".":
        return 0
    return len(relative.parts)


def iter_artifact_paths(root: Path, options: ScanOptions | None = None) -> Iterable[Path]:
    options = options or ScanOptions()
    if not root.exists():
        return
    yield root
    if root.is_file():
        return
    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        current_depth = depth_from_root(root, current_path)
        if options.max_depth is not None and current_depth >= options.max_depth:
            dirs[:] = []
        else:
            dirs[:] = [
                d
                for d in dirs
                if not should_skip_dir(current_path / d, options)
                and (
                    options.max_depth is None
                    or depth_from_root(root, current_path / d) <= options.max_depth
                )
            ]
        for dirname in dirs:
            yield current_path / dirname
        for filename in files:
            if not options.include_hidden and filename.startswith("."):
                continue
            yield current_path / filename


def inventory_provider(spec: ProviderSpec, options: ScanOptions | None = None) -> list[Artifact]:
    options = options or ScanOptions()
    artifacts: list[Artifact] = []
    seen: set[Path] = set()
    for raw_root in spec.paths:
        root = expand_path(raw_root, options.root_override)
        for path in iter_artifact_paths(root, options) or ():
            resolved = path.resolve() if path.exists() else path
            if resolved in seen:
                continue
            seen.add(resolved)
            artifact_type = infer_artifact_type(path, spec)
            classification, reason, target_notes, contains_secret = classify(path, artifact_type)
            artifacts.append(
                Artifact(
                    provider=spec.name,
                    path=str(path),
                    artifact_type=artifact_type,
                    classification=classification,
                    reason=reason,
                    target_notes=target_notes,
                    contains_secret_reference=contains_secret,
                )
            )
    return artifacts


def count_by(items: Iterable[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items()))


def summarize_artifacts(artifacts: list[Artifact]) -> dict[str, object]:
    return {
        "artifact_count": len(artifacts),
        "credential_reference_count": sum(1 for artifact in artifacts if artifact.contains_secret_reference),
        "by_provider": count_by(artifact.provider for artifact in artifacts),
        "by_classification": count_by(artifact.classification for artifact in artifacts),
        "by_artifact_type": count_by(artifact.artifact_type for artifact in artifacts),
    }


def write_bundle(output_dir: Path, artifacts: list[Artifact]) -> Path:
    bundle_dir = output_dir / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / "resonance-bundle.json"
    payload = {
        "schema": "replicator.resonance_bundle.v1",
        "replicator_version": VERSION,
        "artifact_count": len(artifacts),
        "summary": summarize_artifacts(artifacts),
        "artifacts": [asdict(artifact) for artifact in artifacts],
    }
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return bundle_path


def write_report(output_dir: Path, artifacts: list[Artifact]) -> Path:
    report_dir = output_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_path = report_dir / "resonance-report.md"

    by_provider: dict[str, list[Artifact]] = {}
    for artifact in artifacts:
        by_provider.setdefault(artifact.provider, []).append(artifact)

    lines = [
        "# Replicator Resonance Report",
        "",
        f"Replicator version: `{VERSION}`",
        "",
        "Replicator inventories provider configuration and classifies migration safety.",
        "",
        "No credentials, tokens, session files, or API keys were copied.",
        "",
        "## Summary",
        "",
        f"- Artifacts found: {len(artifacts)}",
        f"- Credential/manual auth items not moved: {sum(1 for a in artifacts if a.contains_secret_reference)}",
        "",
        "### By Provider",
        "",
        *[f"- `{key}`: {value}" for key, value in summarize_artifacts(artifacts)["by_provider"].items()],
        "",
        "### By Classification",
        "",
        *[f"- `{key}`: {value}" for key, value in summarize_artifacts(artifacts)["by_classification"].items()],
        "",
        "### By Artifact Type",
        "",
        *[f"- `{key}`: {value}" for key, value in summarize_artifacts(artifacts)["by_artifact_type"].items()],
        "",
    ]

    for provider, provider_artifacts in sorted(by_provider.items()):
        display = PROVIDERS.get(provider, ProviderSpec(provider, provider, ())).display_name
        lines.extend([f"## {display}", ""])
        for artifact in provider_artifacts:
            lines.extend(
                [
                    f"### `{artifact.path}`",
                    "",
                    f"- Type: `{artifact.artifact_type}`",
                    f"- Classification: `{artifact.classification}`",
                    f"- Credential reference: `{str(artifact.contains_secret_reference).lower()}`",
                    f"- Reason: {artifact.reason}",
                    f"- Target notes: {artifact.target_notes}",
                    "",
                ]
            )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def parse_providers(value: str) -> list[ProviderSpec]:
    names = [item.strip().lower() for item in value.split(",") if item.strip()]
    unknown = [name for name in names if name not in PROVIDERS]
    if unknown:
        raise SystemExit(f"Unknown provider(s): {', '.join(unknown)}")
    return [PROVIDERS[name] for name in names]


def command_inventory(args: argparse.Namespace) -> int:
    specs = parse_providers(args.providers)
    output_dir = Path(args.output)
    options = ScanOptions(
        root_override=Path(args.root).expanduser() if args.root else None,
        max_depth=args.max_depth,
        include_hidden=args.include_hidden,
        ignore_cache=not args.include_cache,
    )
    artifacts: list[Artifact] = []
    for spec in specs:
        artifacts.extend(inventory_provider(spec, options))
    bundle_path = write_bundle(output_dir, artifacts)
    report_path = write_report(output_dir, artifacts)
    print(f"Wrote Resonance Report: {report_path}")
    print(f"Wrote Resonance Bundle: {bundle_path}")
    print(f"Artifacts: {len(artifacts)}")
    print(f"Credential/manual auth items not moved: {sum(1 for a in artifacts if a.contains_secret_reference)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="replicator")
    parser.add_argument("--version", action="version", version=f"replicator {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inventory = subparsers.add_parser("inventory", help="Inventory provider config safely.")
    inventory.add_argument(
        "--providers",
        default="claude,codex,openclaw,qwen,kimi",
        help="Comma-separated provider list.",
    )
    inventory.add_argument("--output", default=".replicator-output", help="Output directory.")
    inventory.add_argument(
        "--root",
        default=None,
        help="Optional home/root override for fixtures or offline inventories. Applies to ~/ provider paths.",
    )
    inventory.add_argument(
        "--max-depth",
        type=int,
        default=None,
        help="Maximum directory depth to scan below each provider root.",
    )
    inventory.add_argument(
        "--include-cache",
        action="store_true",
        help="Include cache/log/temp/build directories that are skipped by default.",
    )
    inventory.add_argument(
        "--include-hidden",
        action="store_true",
        default=True,
        help="Include hidden files and directories. This is the default for provider config discovery.",
    )
    inventory.add_argument(
        "--exclude-hidden",
        action="store_false",
        dest="include_hidden",
        help="Exclude hidden files and directories below provider roots.",
    )
    inventory.set_defaults(func=command_inventory)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
