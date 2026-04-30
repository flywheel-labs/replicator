# Provider Adapter Notes

Replicator starts with five provider ecosystems:

- `claude`
- `codex`
- `openclaw`
- `qwen`
- `kimi`

Adapters should define:

- discovery paths,
- artifact types,
- secret filename/key patterns,
- skill/plugin formats,
- MCP config formats,
- permission model notes,
- known non-portable behavior.

Provider adapters should inventory conservatively. If an artifact may contain secrets, record the path and classification but do not copy its content into generated drafts.

As of v0.3.0, provider specs and conservative classification rules live in `replicator/adapters.py`.

Classification precedence:

1. Secret/auth/session markers.
2. Provider structure, such as a `skills/` tree.
3. Plugin/extension structure.
4. Explicit MCP config files, such as `mcp.json`.
5. Generic config, instruction, and unknown fallback types.

This ordering prevents false positives such as a Claude skill named `mcp-builder` being treated as MCP config.
