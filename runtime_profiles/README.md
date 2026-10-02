# Runtime profiles

Runtime profiles name the environment using Aham Brahmasmi without granting it capabilities.

A profile does not mean that the runtime can read files, write files, run commands, use Git, access the network, load skills, or connect to semantic memory. Those capabilities must be verified in the active session and reported explicitly to the startup executable.

The initial profiles are:

- `claude.json`
- `gemini.json`
- `codex.json`
- `local.json`
- `unknown.json`

All profiles keep native skill loading and semantic memory optional. The `unknown` profile is the safe fallback for a runtime that does not have a named profile yet.

These files are intentionally small. Vendor-specific commands, hooks, flags, or automatic configuration must not be added unless they are independently verified from a public upstream source and tested.
