#!/usr/bin/env python3
"""Replicator: safe provider configuration inventory and Resonance Reports."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from replicator import __version__ as VERSION
from replicator.adapters import PROVIDERS, ProviderSpec, classify, infer_artifact_type
from replicator.compare import compare_bundles, write_comparison
from replicator.doctor import doctor_payload, render_doctor_report
from replicator.drafts import SUPPORTED_SOURCES, SUPPORTED_TARGETS, generate_claude_drafts, generate_codex_drafts
from replicator.install import install_draft, restore_install
from replicator.schema import build_bundle_payload, stable_artifact_id, validate_bundle_payload
from replicator.stage import SUPPORTED_STAGE_TARGETS, stage_draft
from replicator.status import print_json_status, status_payload
from replicator.validate import render_validation_report, validate_root
from replicator.workflows import render_workflow_report, workflow_payload, write_contract

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


def expand_path(raw: str, root_override: Path | None = None) -> Path:
    expanded = Path(os.path.expandvars(os.path.expanduser(raw)))
    if root_override is not None and raw.startswith("~/"):
        return root_override / raw[2:]
    return expanded


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


def write_bundle(
    output_dir: Path,
    artifacts: list[Artifact],
    options: ScanOptions | None = None,
) -> Path:
    options = options or ScanOptions()
    bundle_dir = output_dir / "bundles"
    bundle_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = bundle_dir / "resonance-bundle.json"
    payload = build_bundle_payload(
        version=VERSION,
        artifacts=artifacts,
        summary=summarize_artifacts(artifacts),
        root_override=options.root_override,
        max_depth=options.max_depth,
        include_hidden=options.include_hidden,
        ignore_cache=options.ignore_cache,
    )
    validate_bundle_payload(payload)
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return bundle_path


def write_report(output_dir: Path, artifacts: list[Artifact], *, compact: bool = False) -> Path:
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
        "### Schema",
        "",
        "- Bundle schema: `replicator.resonance_bundle.v1`",
        "- Stable artifact IDs: enabled",
        "- Non-secret file checksums: enabled",
        "- Secret checksums: skipped",
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
    if compact:
        report_path.write_text("\n".join(lines), encoding="utf-8")
        return report_path

    for provider, provider_artifacts in sorted(by_provider.items()):
        display = PROVIDERS.get(provider, ProviderSpec(provider, provider, ())).display_name
        lines.extend([f"## {display}", ""])
        for artifact in provider_artifacts:
            lines.extend(
                [
                    f"### `{artifact.path}`",
                    "",
                    f"- Artifact ID: `{stable_artifact_id(artifact.provider, artifact.path, artifact.artifact_type)}`",
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
    bundle_path = write_bundle(output_dir, artifacts, options)
    report_path = write_report(output_dir, artifacts, compact=args.compact_report)
    data = {
        "report_path": str(report_path),
        "bundle_path": str(bundle_path),
        "artifact_count": len(artifacts),
        "credential_reference_count": sum(1 for a in artifacts if a.contains_secret_reference),
        "summary": summarize_artifacts(artifacts),
    }
    if args.json:
        print_json_status(
            status_payload(
                message="Inventory completed.",
                command="inventory",
                data=data,
            )
        )
        return 0
    print(f"Wrote Resonance Report: {report_path}")
    print(f"Wrote Resonance Bundle: {bundle_path}")
    print(f"Artifacts: {len(artifacts)}")
    print(f"Credential/manual auth items not moved: {sum(1 for a in artifacts if a.contains_secret_reference)}")
    return 0


def command_generate(args: argparse.Namespace) -> int:
    target = args.to.lower()
    source = args.from_provider.lower() if args.from_provider else ("claude" if target == "codex" else "codex")
    if target not in SUPPORTED_TARGETS:
        raise SystemExit(f"Unsupported target provider for draft generation: {args.to}")
    if source not in SUPPORTED_SOURCES:
        raise SystemExit(f"Unsupported source provider for draft generation: {source}")

    bundle_path = Path(args.from_bundle)
    output_dir = Path(args.output)
    if target == "codex":
        results = generate_codex_drafts(bundle_path, output_dir, source_provider=source)
    elif target == "claude":
        results = generate_claude_drafts(bundle_path, output_dir, source_provider=source)
    else:
        raise SystemExit(f"Unsupported target provider for draft generation: {args.to}")

    generated = sum(1 for result in results if result.status == "generated")
    skipped = sum(1 for result in results if result.status == "skipped")
    manifest_path = output_dir / target / "manifest.json"
    if args.json:
        print_json_status(
            status_payload(
                message="Draft generation completed.",
                command="generate",
                data={
                    "source_provider": source,
                    "target_provider": target,
                    "manifest_path": str(manifest_path),
                    "generated_count": generated,
                    "skipped_count": skipped,
                },
            )
        )
        return 0
    print(f"Wrote {target} draft manifest: {manifest_path}")
    print(f"Source provider: {source}")
    print(f"Generated drafts: {generated}")
    print(f"Skipped artifacts: {skipped}")
    return 0


def command_compare(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    comparison = compare_bundles(Path(args.left), Path(args.right))
    report_path, json_path = write_comparison(output_dir, comparison, compact=args.compact_report)
    if args.json:
        print_json_status(
            status_payload(
                message="Comparison completed.",
                command="compare",
                data={
                    "report_path": str(report_path),
                    "comparison_path": str(json_path),
                    "summary": comparison["summary"],
                },
            )
        )
        return 0
    print(f"Wrote Comparison Report: {report_path}")
    print(f"Wrote Comparison JSON: {json_path}")
    print(f"Items compared: {comparison['summary']['item_count']}")
    print(f"Overlaps: {comparison['summary']['overlap_count']}")
    print(f"Left-only: {comparison['summary']['left_only_count']}")
    print(f"Right-only: {comparison['summary']['right_only_count']}")
    print(f"Manual-only: {comparison['summary']['manual_only_count']}")
    return 0


def command_stage(args: argparse.Namespace) -> int:
    target = args.to.lower()
    manifest = stage_draft(Path(args.draft), Path(args.staging_root), target)
    data = {
        "target_provider": target,
        "manifest_path": manifest["manifest_path"],
        "staged_provider_root": manifest["staged_provider_root"],
        "staged_count": manifest["staged_count"],
        "skipped_count": manifest["skipped_count"],
        "discovery": manifest["discovery"],
        "safety": manifest["safety"],
    }
    if args.json:
        print_json_status(
            status_payload(
                message="Draft staging completed.",
                command="stage",
                data=data,
            )
        )
        return 0
    print(f"Wrote Stage Manifest: {manifest['manifest_path']}")
    print(f"Staged provider root: {manifest['staged_provider_root']}")
    print(f"Staged files: {manifest['staged_count']}")
    print(f"Skipped files: {manifest['skipped_count']}")
    print(f"Discovery passed: {str(manifest['discovery']['passed']).lower()}")
    return 0


def command_install(args: argparse.Namespace) -> int:
    target = args.to.lower()
    manifest = install_draft(Path(args.draft), Path(args.live_root), target, force=args.force)
    data = {
        "target_provider": target,
        "manifest_path": manifest["manifest_path"],
        "live_root": manifest["live_root"],
        "backup_root": manifest["backup_root"],
        "installed_count": manifest["installed_count"],
        "skipped_count": manifest["skipped_count"],
        "discovery": manifest["discovery"],
        "safety": manifest["safety"],
    }
    if args.json:
        print_json_status(
            status_payload(
                message="Draft install completed.",
                command="install",
                data=data,
            )
        )
        return 0
    print(f"Wrote Install Manifest: {manifest['manifest_path']}")
    print(f"Live root: {manifest['live_root']}")
    print(f"Backup root: {manifest['backup_root']}")
    print(f"Installed files: {manifest['installed_count']}")
    print(f"Skipped files: {manifest['skipped_count']}")
    print(f"Discovery passed: {str(manifest['discovery']['passed']).lower()}")
    return 0


def command_doctor(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = doctor_payload(output_dir, Path(args.fixture_root) if args.fixture_root else None)
    report_path = output_dir / "doctor-report.md"
    report_path.write_text(render_doctor_report(payload), encoding="utf-8")
    if args.json:
        print_json_status(
            status_payload(
                message="Doctor completed.",
                command="doctor",
                data={
                    "report_path": str(report_path),
                    "doctor": payload,
                },
            )
        )
        return 0
    print(f"Wrote Doctor Report: {report_path}")
    print(f"Overall OK: {str(payload['ok']).lower()}")
    return 0


def command_workflow(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = workflow_payload(args.name)
    report_path = output_dir / "workflow-report.md"
    report_path.write_text(render_workflow_report(payload), encoding="utf-8")
    if args.json:
        print_json_status(
            status_payload(
                message="Workflow plan generated.",
                command="workflow",
                data={
                    "report_path": str(report_path),
                    "workflow": payload,
                },
            )
        )
        return 0
    print(f"Wrote Workflow Report: {report_path}")
    if args.name:
        print(f"Workflow: {args.name}")
    else:
        print("Workflow: all")
    return 0


def command_contract(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    path = write_contract(output_dir)
    if args.json:
        print_json_status(
            status_payload(
                message="Command contract written.",
                command="contract",
                data={"contract_path": str(path)},
            )
        )
        return 0
    print(f"Wrote Command Contract: {path}")
    return 0


def command_restore(args: argparse.Namespace) -> int:
    manifest = restore_install(Path(args.manifest))
    data = {
        "manifest_path": manifest["manifest_path"],
        "install_manifest_path": manifest["install_manifest_path"],
        "target_provider": manifest["target_provider"],
        "live_root": manifest["live_root"],
        "restored_count": manifest["restored_count"],
        "skipped_count": manifest["skipped_count"],
        "safety": manifest["safety"],
    }
    if args.json:
        print_json_status(
            status_payload(
                message="Install restore completed.",
                command="restore",
                data=data,
            )
        )
        return 0
    print(f"Wrote Restore Manifest: {manifest['manifest_path']}")
    print(f"Restored files: {manifest['restored_count']}")
    print(f"Skipped files: {manifest['skipped_count']}")
    return 0


def command_validate(args: argparse.Namespace) -> int:
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)
    validation = validate_root(Path(args.root), args.to.lower())
    report_path = output_dir / "validation-report.md"
    report_path.write_text(render_validation_report(validation), encoding="utf-8")
    data = {
        "report_path": str(report_path),
        "validation": validation,
    }
    if args.json:
        print_json_status(
            status_payload(
                message="Validation completed.",
                command="validate",
                data=data,
            )
        )
        return 0
    print(f"Wrote Validation Report: {report_path}")
    print(f"Overall OK: {str(validation['ok']).lower()}")
    print(f"Errors: {validation['summary']['error_count']}")
    print(f"Warnings: {validation['summary']['warning_count']}")
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
    inventory.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    inventory.add_argument("--compact-report", action="store_true", help="Write summary-only markdown report.")
    inventory.set_defaults(func=command_inventory)

    generate = subparsers.add_parser("generate", help="Generate target-provider draft config from a Resonance Bundle.")
    generate.add_argument(
        "--from-bundle",
        required=True,
        help="Path to a resonance-bundle.json file.",
    )
    generate.add_argument(
        "--to",
        required=True,
        choices=sorted(SUPPORTED_TARGETS),
        help="Target provider for generated drafts.",
    )
    generate.add_argument(
        "--from-provider",
        choices=sorted(SUPPORTED_SOURCES),
        default=None,
        help="Source provider to generate from. Defaults to claude for codex targets and codex for claude targets.",
    )
    generate.add_argument("--output", default=".replicator-drafts", help="Draft output directory.")
    generate.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    generate.set_defaults(func=command_generate)

    compare = subparsers.add_parser("compare", help="Compare two Resonance Bundles.")
    compare.add_argument("--left", required=True, help="Left/source resonance-bundle.json.")
    compare.add_argument("--right", required=True, help="Right/target resonance-bundle.json.")
    compare.add_argument("--output", default=".replicator-compare", help="Comparison output directory.")
    compare.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    compare.add_argument("--compact-report", action="store_true", help="Write summary-only markdown report.")
    compare.set_defaults(func=command_compare)

    stage = subparsers.add_parser("stage", help="Stage generated drafts into an isolated provider-like root.")
    stage.add_argument("--draft", required=True, help="Draft root, such as .replicator-drafts/codex or .replicator-drafts.")
    stage.add_argument("--to", required=True, choices=sorted(SUPPORTED_STAGE_TARGETS), help="Target provider to stage.")
    stage.add_argument("--staging-root", required=True, help="Isolated staging root. Live provider config is never used by default.")
    stage.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    stage.set_defaults(func=command_stage)

    install = subparsers.add_parser("install", help="Install generated drafts into an explicit live root with backup safeguards.")
    install.add_argument("--draft", required=True, help="Draft root, such as .replicator-drafts/codex or .replicator-drafts.")
    install.add_argument("--to", required=True, choices=sorted(SUPPORTED_STAGE_TARGETS), help="Target provider to install.")
    install.add_argument("--live-root", required=True, help="Explicit provider config root to write. No default live root is inferred.")
    install.add_argument("--force", action="store_true", help="Replace existing files after backing them up.")
    install.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    install.set_defaults(func=command_install)

    restore = subparsers.add_parser("restore", help="Restore files from a Replicator install manifest backup.")
    restore.add_argument("--manifest", required=True, help="Path to replicator-install-manifest.json.")
    restore.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    restore.set_defaults(func=command_restore)

    validate = subparsers.add_parser("validate", help="Validate a staged or installed provider root without executing anything.")
    validate.add_argument("--root", required=True, help="Provider-like root to validate.")
    validate.add_argument("--to", required=True, choices=sorted(SUPPORTED_STAGE_TARGETS), help="Provider layout to validate.")
    validate.add_argument("--output", default=".replicator-validate", help="Validation output directory.")
    validate.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    validate.set_defaults(func=command_validate)

    doctor = subparsers.add_parser("doctor", help="Run local readiness checks for app integrations.")
    doctor.add_argument("--output", default=".replicator-doctor", help="Doctor output directory.")
    doctor.add_argument("--fixture-root", default=None, help="Optional fixture root to check.")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    doctor.set_defaults(func=command_doctor)

    workflow = subparsers.add_parser("workflow", help="Show safe workflow presets for app integrations.")
    workflow.add_argument("--name", default=None, help="Workflow preset name. Omit to list all presets.")
    workflow.add_argument("--output", default=".replicator-workflows", help="Workflow output directory.")
    workflow.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    workflow.set_defaults(func=command_workflow)

    contract = subparsers.add_parser("contract", help="Write machine-readable command contract documentation.")
    contract.add_argument("--output", default=".replicator-contract", help="Contract output directory.")
    contract.add_argument("--json", action="store_true", help="Emit machine-readable JSON status.")
    contract.set_defaults(func=command_contract)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
