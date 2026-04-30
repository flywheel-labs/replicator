"""Provider adapters and conservative artifact classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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


def is_secret_path(path: Path) -> bool:
    lowered = str(path).lower()
    return any(marker in lowered for marker in SECRET_MARKERS)


def path_parts_lower(path: Path) -> tuple[str, ...]:
    return tuple(part.lower() for part in path.parts)


def is_under_marker(path: Path, markers: tuple[str, ...]) -> bool:
    parts = path_parts_lower(path)
    return any(marker in parts for marker in markers)


def is_explicit_mcp_config(path: Path, spec: ProviderSpec) -> bool:
    name = path.name.lower()
    parts = path_parts_lower(path)
    if name in {"mcp.json", "mcp.toml", "mcp.yaml", "mcp.yml"}:
        return True
    if "mcpservers" in name or "mcp-server" in name:
        return True
    return bool(
        spec.mcp_markers
        and any(marker in parts for marker in spec.mcp_markers)
        and path.suffix.lower() in {".json", ".toml", ".yaml", ".yml"}
    )


def infer_artifact_type(path: Path, spec: ProviderSpec) -> str:
    parts = path_parts_lower(path)
    name = path.name.lower()

    if is_secret_path(path):
        return "credential_reference"

    # A skill named "mcp-builder" is still a skill. Prefer containing provider
    # structure over name substrings, then recognize explicit MCP config files.
    if is_under_marker(path, spec.skill_markers):
        return "skill_or_prompt"
    if is_under_marker(path, spec.plugin_markers):
        return "plugin_or_extension"
    if is_explicit_mcp_config(path, spec):
        return "mcp_config"
    if any(marker == name for marker in spec.skill_markers):
        return "skill_or_prompt"
    if any(marker == name for marker in spec.plugin_markers):
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

