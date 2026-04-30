# Replicator

Replicator is a provider-configuration portability skill for local AI agent ecosystems.

Current release: `v0.13.0` ACC workflow contract baseline.

It inventories provider configuration, classifies what can be translated safely, and writes a **Resonance Report** plus a neutral bundle for review.

Initial providers:

- Claude Code
- OpenAI Codex
- OpenClaw
- Qwen Code
- Kimi / Moonshot

Replicator does not copy credentials, overwrite live config, or claim providers are equivalent.

## What's In The Name?

The name comes from the science-fiction cautionary pattern of systems that absorb every useful tool they encounter.

Replicator borrows the energy of that idea but rejects the bad version of it: this project is not meant to assimilate Claude, Codex, OpenClaw, Qwen, Kimi, or any other provider into a lowest-common-denominator blob.

The goal is translation with boundaries. Replicator inventories what exists, preserves provider-specific distinctiveness, identifies what can resonate across ecosystems, and reports what must stay manual.

## MVP

```bash
python replicator/scripts/replicator.py inventory --providers claude,codex,openclaw,qwen,kimi --output .replicator-output
```

Outputs:

- `.replicator-output/reports/resonance-report.md`
- `.replicator-output/bundles/resonance-bundle.json`

Generate Codex drafts from a Resonance Bundle:

```bash
python replicator/scripts/replicator.py generate \
  --from-bundle .replicator-output/bundles/resonance-bundle.json \
  --to codex \
  --output .replicator-drafts
```

Generate Codex drafts from another provider's command/prompt markdown:

```bash
python replicator/scripts/replicator.py generate \
  --from-bundle .replicator-output-qwen/bundles/resonance-bundle.json \
  --from-provider qwen \
  --to codex \
  --output .replicator-drafts
```

Draft outputs:

- `.replicator-drafts/codex/manifest.json`
- `.replicator-drafts/codex/skills/<skill-name>/SKILL.md`
- `.replicator-drafts/codex/skills/<skill-name>/MIGRATION_NOTES.md`
- `.replicator-drafts/codex/mcp/<config-name>/<config-file>`
- `.replicator-drafts/codex/mcp/<config-name>/MIGRATION_NOTES.md`

Generate Claude drafts from a Resonance Bundle:

```bash
python replicator/scripts/replicator.py generate \
  --from-bundle .replicator-output/bundles/resonance-bundle.json \
  --to claude \
  --output .replicator-drafts
```

Compare two Resonance Bundles:

```bash
python replicator/scripts/replicator.py compare \
  --left .replicator-output-claude/bundles/resonance-bundle.json \
  --right .replicator-output-codex/bundles/resonance-bundle.json \
  --output .replicator-compare
```

Emit machine-readable status for ACC or other callers:

```bash
python replicator/scripts/replicator.py inventory \
  --providers claude \
  --output .replicator-output \
  --compact-report \
  --json
```

Run readiness checks and write command contract docs:

```bash
python replicator/scripts/replicator.py doctor --json
python replicator/scripts/replicator.py workflow --name claude-to-codex-draft --json
python replicator/scripts/replicator.py contract --json
```

Stage generated drafts into an isolated provider-like root:

```bash
python replicator/scripts/replicator.py stage \
  --draft .replicator-drafts \
  --to codex \
  --staging-root .replicator-stage \
  --json
```

Install generated drafts into an explicit live root with backup safeguards:

```bash
python replicator/scripts/replicator.py install \
  --draft .replicator-drafts \
  --to codex \
  --live-root ~/.codex \
  --json
```

Use `--force` only when replacing existing files. Existing files are backed up under `<live-root>/replicator-backups/<timestamp>/` before replacement.

## Usage

Inventory your local provider config:

```bash
python3 replicator/scripts/replicator.py inventory \
  --providers claude,codex,openclaw,qwen,kimi \
  --output .replicator-output
```

Inventory synthetic fixtures:

```bash
python3 replicator/scripts/replicator.py inventory \
  --providers claude,codex,openclaw,qwen,kimi \
  --root tests/fixtures/home \
  --output .replicator-output-fixture
```

Limit scan depth:

```bash
python3 replicator/scripts/replicator.py inventory \
  --providers claude,codex \
  --max-depth 2 \
  --output .replicator-output
```

By default, Replicator skips cache/log/temp/build directories. Use `--include-cache` only when you need a complete filesystem inventory.

## v0.13.0 Scope

Replicator v0.13.0 remains conservative. Inventory is read-only, generation writes drafts only to an output directory, comparison writes reports only to an output directory, staging writes only to an explicit isolated staging root, install writes only to an explicit live root, and JSON status is opt-in.

It can:

- inventory known local provider config locations,
- classify discovered artifacts,
- produce a Resonance Report,
- produce a Resonance Bundle,
- itemize credentials/session/auth artifacts as not moved.
- summarize artifacts by provider, classification, and artifact type,
- scan synthetic fixture roots for public examples and tests,
- limit scan depth and skip cache/log/temp/build directories by default.
- classify through provider adapter rules instead of monolithic CLI logic,
- prefer skill context over path substrings, so a skill named `mcp-builder` is still classified as a skill.
- write formal `replicator.resonance_bundle.v1` payloads,
- assign stable artifact IDs,
- include source metadata,
- checksum non-secret files,
- skip secret checksums and itemize skipped-secret records.
- generate Codex skill drafts from portable Claude `SKILL.md` artifacts,
- generate Claude skill drafts from portable Codex `SKILL.md` artifacts,
- generate target skill drafts from portable Qwen command markdown, Kimi prompt markdown, and OpenClaw agent markdown,
- generate MCP config drafts with migration notes,
- select the generation source provider with `--from-provider`,
- write migration notes for each generated draft,
- write a draft manifest that records generated and skipped artifacts.
- compare two Resonance Bundles,
- report overlaps, left-only gaps, right-only gaps, and manual-only credential items.
- emit machine-readable CLI status with `--json`,
- use stable status schema `replicator.cli_status.v1`,
- use stable success code `REP_OK`,
- write compact summary-only markdown reports with `--compact-report`.
- stage generated skill drafts into an isolated provider-like directory,
- write `stage-manifest.json`,
- report staged file counts and simple staged-skill discovery results.
- install generated skill drafts into an explicit live provider root,
- refuse to replace existing files unless `--force` is used,
- back up replaced files before forced replacement,
- write `replicator-install-manifest.json`.
- run readiness checks with `doctor`,
- expose safe workflow presets with `workflow`,
- write app-facing command contract docs with `contract`.

It does not:

- copy credentials,
- write live provider config,
- sync providers,
- execute discovered scripts or hooks.
- infer or auto-select `~/.codex` or `~/.claude`.
- install credentials, sessions, MCP config, plugins, hooks, or scripts.
- execute, install, or validate MCP servers.
- translate plugins, hooks, or scripts.

## Migration Shapes

- `A -> B`: source provider to receiving provider.
- `B -> A`: reverse translation, evaluated independently.
- `A -> C`: source provider to a third ecosystem.
- `A -> Resonance -> B`: preferred long-term neutral-bundle flow.

## License

Apache License 2.0. See [LICENSE](LICENSE).
