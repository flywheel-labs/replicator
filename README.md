# Replicator

Replicator is a provider-configuration portability skill for local AI agent ecosystems.

It inventories provider configuration, classifies what can be translated safely, and writes a **Resonance Report** plus a neutral bundle for review.

Initial providers:

- Claude Code
- OpenAI Codex
- OpenClaw
- Qwen Code
- Kimi / Moonshot

Replicator does not copy credentials, overwrite live config, or claim providers are equivalent.

## MVP

```bash
python replicator/scripts/replicator.py inventory --providers claude,codex,openclaw,qwen,kimi --output .replicator-output
```

Outputs:

- `.replicator-output/reports/resonance-report.md`
- `.replicator-output/bundles/resonance-bundle.json`

## Migration Shapes

- `A -> B`: source provider to receiving provider.
- `B -> A`: reverse translation, evaluated independently.
- `A -> C`: source provider to a third ecosystem.
- `A -> Resonance -> B`: preferred long-term neutral-bundle flow.

## License

Apache License 2.0. See [LICENSE](LICENSE).
