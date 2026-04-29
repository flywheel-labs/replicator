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

