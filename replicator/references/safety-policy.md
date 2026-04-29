# Replicator Safety Policy

Replicator is a migration assistant, not an automatic sync engine.

It must not:

- copy API keys,
- copy OAuth/session tokens,
- copy credential stores,
- execute discovered hooks or scripts,
- overwrite provider config by default,
- silently broaden filesystem or tool permissions,
- hide skipped credential work from the user.

Credential-related artifacts should appear in reports with clear manual follow-up instructions.

