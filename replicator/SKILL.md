---
name: replicator
description: Use when migrating, comparing, or documenting local AI agent provider configuration between Claude Code, OpenAI Codex, OpenClaw, Qwen Code, Kimi/Moonshot, and neutral ACC-style portability bundles. Produces safe inventories, Resonance Reports, and provider-specific drafts without copying credentials or overwriting live config.
---

# Replicator

Replicator helps move local agent configuration between providers without flattening provider-specific behavior.

Use it for:

- Claude Code -> Codex migration planning,
- Codex -> Claude migration planning,
- Claude/Codex/OpenClaw/Qwen/Kimi inventory,
- provider-neutral portability reports,
- safe draft generation for a receiving provider.

## Safety Rules

- Never copy credentials, tokens, API keys, OAuth files, or session secrets.
- Itemize skipped credentials in the report so the user knows what must be recreated manually.
- Never overwrite live provider config unless the user explicitly asks and a backup exists.
- Do not execute discovered scripts or hooks during inventory.
- Classify provider-specific behavior instead of pretending it is portable.

## Workflow

1. Identify source and target providers.
2. Run inventory with `scripts/replicator.py`.
3. Review the Resonance Report.
4. Generate target-provider drafts only for artifacts classified as safe or editable.
5. Treat `manual_review` and `not_portable` items as handoff tasks.

## Commands

Inventory all MVP providers:

```bash
python replicator/scripts/replicator.py inventory --providers claude,codex,openclaw,qwen,kimi --output .replicator-output
```

Inventory one source provider:

```bash
python replicator/scripts/replicator.py inventory --providers claude --output .replicator-output
```

## References

- Read `references/providers.md` when adding or modifying provider adapters.
- Read `references/artifact-schema.md` when changing report or bundle shape.
- Read `references/safety-policy.md` before adding any write/sync behavior.
- Read `references/migration-variants.md` when planning A->B, B->A, A->C, or neutral-bundle flows.
