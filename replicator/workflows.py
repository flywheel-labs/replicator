"""Safe workflow presets for app integrations."""

from __future__ import annotations

from pathlib import Path


WORKFLOWS: dict[str, dict[str, object]] = {
    "inventory-all": {
        "description": "Inventory all supported providers into a Resonance Bundle.",
        "writes_live_config": False,
        "steps": [
            {
                "command": "inventory",
                "providers": "claude,codex,openclaw,qwen,kimi",
                "output": ".replicator-output",
            }
        ],
    },
    "claude-to-codex-draft": {
        "description": "Inventory Claude config and generate Codex drafts.",
        "writes_live_config": False,
        "steps": [
            {
                "command": "inventory",
                "providers": "claude",
                "output": ".replicator-output-claude",
            },
            {
                "command": "generate",
                "from_bundle": ".replicator-output-claude/bundles/resonance-bundle.json",
                "from_provider": "claude",
                "to": "codex",
                "output": ".replicator-drafts-codex",
            },
        ],
    },
    "codex-to-claude-draft": {
        "description": "Inventory Codex config and generate Claude drafts.",
        "writes_live_config": False,
        "steps": [
            {
                "command": "inventory",
                "providers": "codex",
                "output": ".replicator-output-codex",
            },
            {
                "command": "generate",
                "from_bundle": ".replicator-output-codex/bundles/resonance-bundle.json",
                "from_provider": "codex",
                "to": "claude",
                "output": ".replicator-drafts-claude",
            },
        ],
    },
}


def workflow_payload(name: str | None = None) -> dict[str, object]:
    if name is None:
        return {
            "schema": "replicator.workflow.v1",
            "available": sorted(WORKFLOWS),
            "workflows": WORKFLOWS,
        }
    if name not in WORKFLOWS:
        raise ValueError(f"unknown workflow: {name}")
    return {
        "schema": "replicator.workflow.v1",
        "name": name,
        "workflow": WORKFLOWS[name],
    }


def render_workflow_report(payload: dict[str, object]) -> str:
    lines = ["# Replicator Workflows", ""]
    workflows = payload.get("workflows")
    if workflows is None:
        workflows = {payload["name"]: payload["workflow"]}
    for name, workflow in workflows.items():
        lines.extend(
            [
                f"## `{name}`",
                "",
                f"- Description: {workflow['description']}",
                f"- Writes live config: `{str(workflow['writes_live_config']).lower()}`",
                "",
                "### Steps",
                "",
            ]
        )
        for index, step in enumerate(workflow["steps"], start=1):
            args = ", ".join(f"{key}={value}" for key, value in step.items() if key != "command")
            lines.append(f"{index}. `{step['command']}` {args}".rstrip())
        lines.append("")
    return "\n".join(lines)


def write_contract(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "command-contract.md"
    path.write_text(
        "\n".join(
            [
                "# Replicator Command Contract",
                "",
                "All commands are explicit-path and output-directory oriented.",
                "",
                "## JSON Status",
                "",
                "- Schema: `replicator.cli_status.v1`",
                "- Success code: `REP_OK`",
                "- Error code namespace: `REP_ERROR`",
                "",
                "## Safe Defaults",
                "",
                "- `inventory`, `generate`, `compare`, `stage`, `doctor`, and `workflow` do not write live provider config.",
                "- `install` writes live provider config only when `--live-root` is explicitly supplied.",
                "- Credentials, sessions, tokens, hooks, scripts, and executable plugins are not copied.",
                "- MCP configs are copied only as manual-review drafts and are never executed.",
                "",
                "## Recommended ACC Flow",
                "",
                "1. Run `doctor --json`.",
                "2. Show a selected `workflow --name <preset> --json` to the user.",
                "3. Run `inventory` and `generate` with explicit output paths.",
                "4. Prefer `stage` before `install`.",
                "5. Only run `install` after showing `--live-root` and backup behavior to the user.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path

