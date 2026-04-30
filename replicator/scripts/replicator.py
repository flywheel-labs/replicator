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
from replicator.drafts import SUPPORTED_TARGETS, generate_claude_drafts, generate_codex_drafts
from replicator.schema import build_bundle_payload, stable_artifact_id, validate_bundle_payload
from replicator.status import print_json_status, status_payload

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
    if target not in SUPPORTED_TARGETS:
        raise SystemExit(f"Unsupported target provider for draft generation: {args.to}")

    bundle_path = Path(args.from_bundle)
    output_dir = Path(args.output)
    if target == "codex":
        results = generate_codex_drafts(bundle_path, output_dir)
    elif target == "claude":
        results = generate_claude_drafts(bundle_path, output_dir)
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
                    "target_provider": target,
                    "manifest_path": str(manifest_path),
                    "generated_count": generated,
                    "skipped_count": skipped,
                },
            )
        )
        return 0
    print(f"Wrote {target} draft manifest: {manifest_path}")
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
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
