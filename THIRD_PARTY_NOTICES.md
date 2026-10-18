# Third-party notices

Aham Brahmasmi keeps external projects separate from the framework whenever practical. The projects listed here are integrations or optional sources, not works created by Aham Brahmasmi.

The current public framework repository does not contain copied source trees from the projects below. When an optional source is fetched for a user, it comes from its original upstream source and keeps its own license and copyright notices.

## MemPalace

- Project: MemPalace
- Original source: https://github.com/MemPalace/mempalace
- Reviewed source: `f8b9ed1507888cab47c7c7e1d90755f89e0353c4`
- License: MIT
- Copyright notice at the reviewed source: Copyright 2026 MemPalace Contributors
- Role here: optional semantic-memory provider

MemPalace is independently installed and operated. Aham Brahmasmi connects to an already available MemPalace CLI through an optional adapter and continues to work when MemPalace is absent.

## Superpowers

- Project: Superpowers
- Original source: https://github.com/obra/superpowers
- Reviewed source: `b36e0829c6d0140e93cfef2ca599b1b07d4a7797`
- License: MIT
- Copyright notice at the reviewed source: Copyright 2025 Jesse Vincent
- Role here: optional external skill collection

Aham Brahmasmi does not store the Superpowers skill tree in this repository. When the reviewed installer is requested, it fetches the exact reviewed source from the original upstream into the user's private workspace, quarantines and scans it, and retains its upstream provenance and license information.

## Optional native command hooks

Only independently written protocol adapters are included. These integrations do
not install or redistribute a runtime, source tree, documentation or binary.
The exact verified public formats and limits are in
[Command guard sources](docs/COMMAND_GUARD_SOURCES.md).

| Project | Original source | Reviewed source | License and attribution |
| --- | --- | --- | --- |
| Claude Code hooks | https://github.com/anthropics/claude-code | `dd6bee38458cc3e6dc5f2b16eca1f0f364619ad8` | Proprietary: Anthropic Commercial Terms of Service. Independent Anthropic product. |
| Codex hooks | https://github.com/openai/codex | `8c076942cb70fba8e5c4732c23f1faabc4aed484` | Apache-2.0. OpenAI and contributors. |
| Gemini CLI hooks | https://github.com/google-gemini/gemini-cli | `ed96faedfd5571f055c44f2c9509d62321d1138d` | Apache-2.0. Google and contributors. |

## Release rule

If a future version begins bundling, vendoring [copying into this project], modifying, or redistributing third-party material, this file and the release licensing review must be updated before that version can be released.

Aham Brahmasmi's Apache License 2.0 does not replace the license of any independent third-party project.
