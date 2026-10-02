# Runtime adapters

Aham Brahmasmi keeps one model-neutral lifecycle and uses small bridges to make that lifecycle visible to different runtimes.

The bridge does not grant tools, permissions, network access, semantic memory or a skill loader. Those capabilities still have to be verified in the current session.

## What gets installed

For a project outside the public Aham Brahmasmi repository, run:

```text
python3 scripts/runtime_bridge.py install \
  --runtime <claude|gemini|codex|local|unknown> \
  --workspace <private-brain-workspace> \
  --project <project-root>
```

Every runtime gets:

```text
.aham/runtime.md
.aham/runtime.json
.aham/.gitignore
```

`runtime.md` contains the portable lifecycle instructions. It deliberately contains no local framework path, private workspace path or project path.

`runtime.json` contains the local paths needed to execute the lifecycle commands on that machine. The installer adds `runtime.json` to `.aham/.gitignore` so those local paths do not need to enter project history.

The runtime reads the local configuration before invoking the framework's startup, recovery, checkpoint, semantic-memory or wrap-up scripts.

## Claude

Claude Code supports project instructions in `CLAUDE.md` and supports importing another file with `@path` syntax.

The bridge installer therefore adds one managed block to the project's `CLAUDE.md`:

```text
@.aham/runtime.md
```

Existing instructions are preserved. Re-running the installer refreshes only the Aham Brahmasmi managed block.

## Gemini

Gemini CLI uses `GEMINI.md` as its default project context file and supports `@file` imports.

The bridge installer adds the same managed import to the project's `GEMINI.md` while preserving unrelated instructions.

## Codex

Codex uses `AGENTS.md` for repository guidance. Aham Brahmasmi does not assume an unverified import syntax for that file.

The bridge installer adds a small managed directive to the project's `AGENTS.md` telling Codex to read and follow `.aham/runtime.md` before substantial work. Existing project instructions remain intact.

## Local and unknown runtimes

There is no universal project-instruction filename or automatic loading convention for local and future runtimes.

For `local` and `unknown`, the installer creates the `.aham` bridge files but does not create Claude, Gemini or Codex instruction files. It prints the manual instruction that should be given to the runtime:

```text
Read and follow .aham/runtime.md before substantial work in this repository.
```

This is deliberate. Aham Brahmasmi should not pretend a runtime automatically loads a file when that behavior has not been verified.

## Lifecycle behavior

The generated bridge tells a capable runtime to:

1. read the local runtime configuration rather than guessing paths;
2. verify the private workspace;
3. run the model-neutral startup report with only capabilities actually verified in that session;
4. recover an unfinished wrap-up before unrelated new work;
5. use semantic recall only when configured and available;
6. verify a relevant existing checkpoint before resuming;
7. create a checkpoint after a meaningful completed milestone;
8. route `wrap up` through the replay-safe wrap-up transaction;
9. never record intended work as completed work.

This is the portable checkpoint-invocation mechanism. It is instruction-driven rather than dependent on a vendor-specific hook, so the same lifecycle continues to work when a runtime has no native hook system.

## Inspect

```text
python3 scripts/runtime_bridge.py status --project <project-root>
```

Use `--json` for machine-readable status. Status also verifies that the local runtime configuration is covered by the `.aham/.gitignore` rule.

## Remove

```text
python3 scripts/runtime_bridge.py remove --project <project-root>
```

Removal deletes the generated `.aham/runtime.md` and `.aham/runtime.json` and removes only the marked Aham Brahmasmi block from a runtime instruction file. It does not delete unrelated `CLAUDE.md`, `GEMINI.md` or `AGENTS.md` content.

The `.aham/.gitignore` file is left in place because it may contain unrelated user entries. Aham Brahmasmi does not rewrite arbitrary ignore content during removal.

## Safety rules

The installer refuses to:

- install a project bridge inside the public framework repository;
- write through a symlinked `.aham` directory or runtime instruction file;
- overwrite an existing unmanaged `.aham/runtime.md`;
- edit malformed or duplicated Aham managed markers.

Runtime-native hooks may be added later as verified optimizations, but they are not required by the core lifecycle.
