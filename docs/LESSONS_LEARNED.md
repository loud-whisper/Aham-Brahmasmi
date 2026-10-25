# Engineering safeguards

- Diagnose the exact model, harness, permissions, context and verifier before attributing a failure to a model.
- Hold the task and model constant while changing one variable. Record unsuccessful results as well as successful ones.
- Verify durable output independently; a model's completion message is not a receipt.
- Preserve project identity, revision authority and recovery checkpoints across interruption.
- Use disposable synthetic workspaces for rehearsals. Keep real home directories, credentials and unrelated projects outside the sandbox.
- Keep runtime-serving access distinct from workspace-execution permissions.
- Bind evidence to the exact source tree and tested environment. A later source change needs appropriate fresh verification.
- Let a harness exit normally before diagnosing a stuck process. Do not use reflexive termination as a repair strategy.
- Preserve unknown evidence fields and report skips honestly.
- Review whole source changes and activation permissions. A source pin or valid license is not a whole-tree safety verdict.
- Use fixture homes and paths in tests so another user's environment can run them.
- Preserve safe rollback state before a consequential change. Never use an important project as a rehearsal fixture.
