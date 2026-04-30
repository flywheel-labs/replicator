# Replicator Artifact Schema

The neutral portability output is called a **Resonance Bundle**.

Current schema:

- `schema`: `replicator.resonance_bundle.v1`
- `schema_version`: `1.0.0`
- `replicator_version`
- `source_metadata`
- `artifact_count`
- `summary`
- `skipped_secrets`
- `artifacts`

Each artifact has:

- `artifact_id`
- `provider`
- `path`
- `artifact_type`
- `classification`
- `reason`
- `target_notes`
- `contains_secret_reference`
- `checksum_sha256`
- `checksum_status`

Checksum statuses:

- `ok`
- `skipped_secret`
- `missing`
- `not_file`
- `unreadable`

Classifications:

- `portable`
- `portable_with_edits`
- `manual_review`
- `not_portable`

The human-readable markdown output is called a **Resonance Report**.

Secret-like artifacts must appear in `skipped_secrets` and must not receive content checksums.

## Draft Outputs

Draft generation consumes a Resonance Bundle and writes provider-specific output under a caller-selected draft directory.

Current draft target:

- `claude`
- `codex`

Current generated files:

- `codex/manifest.json`
- `codex/skills/<skill-name>/SKILL.md`
- `codex/skills/<skill-name>/MIGRATION_NOTES.md`
- `codex/mcp/<config-name>/<config-file>`
- `codex/mcp/<config-name>/MIGRATION_NOTES.md`
- `claude/manifest.json`
- `claude/skills/<skill-name>/SKILL.md`
- `claude/skills/<skill-name>/MIGRATION_NOTES.md`
- `claude/mcp/<config-name>/<config-file>`
- `claude/mcp/<config-name>/MIGRATION_NOTES.md`

Draft generation must not write to live provider config directories by default.

Draft generation must not copy credentials, session files, API keys, OAuth files, hooks, executable scripts, or provider cache data.

Draft generation sources:

- Claude/Codex `SKILL.md` artifacts are copied into draft skill directories.
- Qwen command markdown, Kimi prompt markdown, and OpenClaw agent markdown are wrapped into target-provider `SKILL.md` drafts with source metadata.
- MCP config files are copied to target-provider MCP draft directories with migration notes.
- The `--from-provider` option selects the source provider; the target provider is still selected with `--to`.

## Comparison Outputs

Bundle comparison writes:

- `reports/comparison-report.md`
- `bundles/comparison.json`

Comparison schema:

- `schema`: `replicator.comparison.v1`
- `left_bundle`
- `right_bundle`
- `summary`
- `items`

Comparison item statuses:

- `overlap`
- `left_only`
- `right_only`
- `manual_only_left`
- `manual_only_right`

## CLI Status Output

Commands can emit machine-readable status with `--json`.

Status schema:

- `schema`: `replicator.cli_status.v1`
- `status`: `ok` or `error`
- `code`: stable machine-readable code
- `message`
- `command`
- `data`

Current stable codes:

- `REP_OK`
- `REP_ERROR`

## Stage Manifest

Draft staging writes:

- `<staging-root>/<provider>/stage-manifest.json`
- `<staging-root>/<provider>/skills/<skill-name>/SKILL.md`
- `<staging-root>/<provider>/skills/<skill-name>/MIGRATION_NOTES.md` when notes exist

Stage manifest schema:

- `schema`: `replicator.stage_manifest.v1`
- `target_provider`
- `draft_root`
- `staging_root`
- `staged_provider_root`
- `staged_count`
- `skipped_count`
- `discovery`
- `safety`
- `staged_files`
- `skipped`

Staging must not write live provider config directories unless a future explicit install command adds backup/restore safeguards.

## Install Manifest

Guarded install writes:

- `<live-root>/replicator-install-manifest.json`
- `<live-root>/skills/<skill-name>/SKILL.md`
- `<live-root>/skills/<skill-name>/MIGRATION_NOTES.md` when notes exist
- `<live-root>/replicator-backups/<timestamp>/...` for replaced files when `--force` is used

Install manifest schema:

- `schema`: `replicator.install_manifest.v1`
- `target_provider`
- `draft_root`
- `live_root`
- `backup_root`
- `force`
- `installed_count`
- `skipped_count`
- `discovery`
- `safety`
- `installed`
- `skipped`

Install requires an explicit live root. Replicator must not infer `~/.codex`, `~/.claude`, or any other live provider path by default.
