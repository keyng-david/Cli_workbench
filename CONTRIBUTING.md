# Contributing

Keep changes small and document user-visible behavior. Run the commands in docs/testing.md. Add regression tests for meaningful lifecycle, backup and deletion failures. Never use real credentials in tests or publish private state/logs.

New cloud adapters must preserve resource identity and cleanup semantics. New agent installers must also implement native state persistence, credential handling and resume tests before advertising support.

Update .env.example, configuration docs and the verification ledger when behavior changes. Preserve upstream license notices. Use a PR for review; do not merge or release changes that have only mocked/live-incomplete validation without stating that limitation.
