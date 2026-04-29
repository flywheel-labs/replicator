# Replicator

Replicator is a provider-configuration portability skill for local AI agent ecosystems.

Current release: `v0.1.0` safe inventory baseline.

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

## v0.1.0 Scope

Replicator v0.1.0 is intentionally read-only.

It can:

- inventory known local provider config locations,
- classify discovered artifacts,
- produce a Resonance Report,
- produce a Resonance Bundle,
- itemize credentials/session/auth artifacts as not moved.

It does not:

- copy credentials,
- write live provider config,
- generate target-provider drafts,
- sync providers,
- execute discovered scripts or hooks.

## Migration Shapes

- `A -> B`: source provider to receiving provider.
- `B -> A`: reverse translation, evaluated independently.
- `A -> C`: source provider to a third ecosystem.
- `A -> Resonance -> B`: preferred long-term neutral-bundle flow.

## License

Apache License 2.0. See [LICENSE](LICENSE).
