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

Inventory synthetic fixtures:

```bash
python replicator/scripts/replicator.py inventory --providers claude,codex,openclaw,qwen,kimi --root tests/fixtures/home --output .replicator-output-fixture
```

Use `--max-depth` for bounded scans. Cache/log/temp/build directories are skipped by default; use `--include-cache` only when explicitly needed.

Generate Codex drafts from a Resonance Bundle:

```bash
python replicator/scripts/replicator.py generate --from-bundle .replicator-output/bundles/resonance-bundle.json --to codex --output .replicator-drafts
```

Generate Claude drafts from a Resonance Bundle:

```bash
python replicator/scripts/replicator.py generate --from-bundle .replicator-output/bundles/resonance-bundle.json --to claude --output .replicator-drafts
```

Compare two Resonance Bundles:

```bash
python replicator/scripts/replicator.py compare --left .replicator-output-claude/bundles/resonance-bundle.json --right .replicator-output-codex/bundles/resonance-bundle.json --output .replicator-compare
```

Use `--json` on `inventory`, `generate`, and `compare` when an app needs machine-readable status. Use `--compact-report` on `inventory` and `compare` when an app needs lower-volume markdown.

Stage generated drafts into an isolated provider-like root:

```bash
python replicator/scripts/replicator.py stage --draft .replicator-drafts --to codex --staging-root .replicator-stage --json
```

Install generated drafts into an explicit live root with backup safeguards:

```bash
python replicator/scripts/replicator.py install --draft .replicator-drafts --to codex --live-root ~/.codex --json
```

Use `--force` only when replacing existing files. Replicator does not infer live roots; callers must pass `--live-root` explicitly.

Current baseline: v0.10.0. Provider specs and conservative artifact classification live in `replicator/adapters.py`; use that module when changing provider behavior. Resonance Bundle v1 helpers live in `replicator/schema.py`. Draft generation lives in `replicator/drafts.py` and writes output-only drafts, not live provider config. Bundle comparison lives in `replicator/compare.py`. CLI status helpers live in `replicator/status.py`. Isolated staging lives in `replicator/stage.py`. Guarded install lives in `replicator/install.py`.

## References

- Read `references/providers.md` when adding or modifying provider adapters.
- Read `references/artifact-schema.md` when changing report or bundle shape.
- Read `references/safety-policy.md` before adding any write/sync behavior.
- Read `references/migration-variants.md` when planning A->B, B->A, A->C, or neutral-bundle flows.
