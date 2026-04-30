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
