# Migration Variants

Replicator models provider portability as explicit directional translation.

## A -> B

Translate one source provider into one receiving provider.

Examples:

- Claude Code -> OpenAI Codex
- Codex -> Claude Code
- Claude Code -> Qwen Code

This creates receiving-provider drafts and a Resonance Report. It does not overwrite live config.

## B -> A

Reverse-direction migration is a new translation, not an undo operation.

Provider concepts are not symmetric. A Codex skill may not have a direct Claude equivalent, and a Claude plugin may not have a direct Codex equivalent.

## A -> C

Translate a source provider into a third ecosystem.

Examples:

- Claude Code -> OpenClaw
- Codex -> Kimi/Moonshot
- Claude Code -> ACC import profile

This uses source and target adapters with the neutral schema as the handoff boundary.

## A -> Resonance -> B

Preferred long-term architecture:

1. Source provider inventory.
2. Resonance Bundle.
3. Receiving-provider draft generation.

This avoids building pairwise migrations for every provider pair.

## Names

- **Resonance Report:** human-readable markdown report.
- **Resonance Bundle:** neutral JSON bundle.
- **Adapter:** provider-specific inventory/generation logic.
- **Draft:** generated target-provider artifact requiring review.

