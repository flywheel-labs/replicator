"""Compare Resonance Bundles for migration planning."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from replicator.drafts import load_bundle, slugify_skill_name


@dataclass(frozen=True)
class CompareItem:
    key: str
    artifact_type: str
    left_artifact_id: str | None
    left_provider: str | None
    left_path: str | None
    right_artifact_id: str | None
    right_provider: str | None
    right_path: str | None
    status: str
    migration_note: str


def comparison_key(artifact: dict[str, Any]) -> str:
    artifact_type = str(artifact.get("artifact_type", "unknown"))
    path = str(artifact.get("path", "")).replace("\\", "/")
    if artifact_type == "skill_or_prompt":
        if path.endswith("/SKILL.md"):
            return f"{artifact_type}:{slugify_skill_name(Path(path).parent.name)}"
        return f"{artifact_type}:{slugify_skill_name(Path(path).stem)}"
    if artifact_type == "mcp_config":
        return f"{artifact_type}:{Path(path).name.lower()}"
    return f"{artifact_type}:{Path(path).name.lower()}"


def index_artifacts(bundle: dict[str, Any]) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for artifact in bundle["artifacts"]:
        key = comparison_key(artifact)
        existing = indexed.get(key)
        if existing is None or str(artifact.get("path", "")) < str(existing.get("path", "")):
            indexed[key] = artifact
    return indexed


def item_from_artifacts(
    key: str,
    left: dict[str, Any] | None,
    right: dict[str, Any] | None,
) -> CompareItem:
    artifact_type = str((left or right or {}).get("artifact_type", "unknown"))
    if left and right:
        status = "overlap"
        migration_note = "Comparable artifact exists in both bundles; review provider-specific differences."
    elif left:
        if left.get("contains_secret_reference"):
            status = "manual_only_left"
            migration_note = "Left-only artifact references credentials or session data and must be recreated manually."
        else:
            status = "left_only"
            migration_note = "Left-only artifact may need a target-provider draft or manual migration."
    else:
        if right and right.get("contains_secret_reference"):
            status = "manual_only_right"
            migration_note = "Right-only artifact references credentials or session data and must be recreated manually."
        else:
            status = "right_only"
            migration_note = "Right-only artifact exists only in the target/reference bundle."

    return CompareItem(
        key=key,
        artifact_type=artifact_type,
        left_artifact_id=str(left.get("artifact_id")) if left else None,
        left_provider=str(left.get("provider")) if left else None,
        left_path=str(left.get("path")) if left else None,
        right_artifact_id=str(right.get("artifact_id")) if right else None,
        right_provider=str(right.get("provider")) if right else None,
        right_path=str(right.get("path")) if right else None,
        status=status,
        migration_note=migration_note,
    )


def compare_bundles(left_path: Path, right_path: Path) -> dict[str, Any]:
    left_bundle = load_bundle(left_path)
    right_bundle = load_bundle(right_path)
    left_index = index_artifacts(left_bundle)
    right_index = index_artifacts(right_bundle)
    keys = sorted(set(left_index) | set(right_index))
    items = [item_from_artifacts(key, left_index.get(key), right_index.get(key)) for key in keys]
    summary = {
        "item_count": len(items),
        "overlap_count": sum(1 for item in items if item.status == "overlap"),
        "left_only_count": sum(1 for item in items if item.status == "left_only"),
        "right_only_count": sum(1 for item in items if item.status == "right_only"),
        "manual_only_count": sum(1 for item in items if item.status.startswith("manual_only")),
        "by_status": count_by(item.status for item in items),
        "by_artifact_type": count_by(item.artifact_type for item in items),
    }
    return {
        "schema": "replicator.comparison.v1",
        "left_bundle": str(left_path),
        "right_bundle": str(right_path),
        "summary": summary,
        "items": [asdict(item) for item in items],
    }


def count_by(items: list[str] | Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items()))


def write_comparison(output_dir: Path, comparison: dict[str, Any]) -> tuple[Path, Path]:
    report_dir = output_dir / "reports"
    bundle_dir = output_dir / "bundles"
    report_dir.mkdir(parents=True, exist_ok=True)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    json_path = bundle_dir / "comparison.json"
    report_path = report_dir / "comparison-report.md"
    json_path.write_text(json.dumps(comparison, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(render_comparison_report(comparison), encoding="utf-8")
    return report_path, json_path


def render_comparison_report(comparison: dict[str, Any]) -> str:
    summary = comparison["summary"]
    lines = [
        "# Replicator Comparison Report",
        "",
        f"- Left bundle: `{comparison['left_bundle']}`",
        f"- Right bundle: `{comparison['right_bundle']}`",
        f"- Items compared: {summary['item_count']}",
        f"- Overlaps: {summary['overlap_count']}",
        f"- Left-only: {summary['left_only_count']}",
        f"- Right-only: {summary['right_only_count']}",
        f"- Manual-only: {summary['manual_only_count']}",
        "",
        "## By Status",
        "",
        *[f"- `{key}`: {value}" for key, value in summary["by_status"].items()],
        "",
        "## Items",
        "",
    ]
    for item in comparison["items"]:
        lines.extend(
            [
                f"### `{item['key']}`",
                "",
                f"- Status: `{item['status']}`",
                f"- Type: `{item['artifact_type']}`",
                f"- Left: `{item['left_path'] or 'missing'}`",
                f"- Right: `{item['right_path'] or 'missing'}`",
                f"- Note: {item['migration_note']}",
                "",
            ]
        )
    return "\n".join(lines)

