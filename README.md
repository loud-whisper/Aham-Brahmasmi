# Aham Brahmasmi

Save useful context from your AI work in a private folder you own, then carry it
into another assistant, model or session.

**Change models. Change tools. Close the terminal. Come back tomorrow. Pick up where you left off.**

![Your assistants (Claude, Codex, Gemini, a local model or any other) pass a trust check before saving to your private Brain folder; skills are scanned and quarantined until you review them; the next assistant picks up where the last one stopped. Verified saves, locked-down skills, private by default, nothing to sign up for.](docs/assets/overview.png)

Works with Claude, Codex, Gemini, local models and other assistants that can read
files and run commands. Chat websites can use a copy-and-paste mode.

## Start in three steps

1. Check `docs/BEFORE_YOU_START.md` and choose an assistant with local file and command
   tools using `docs/GET_AN_ASSISTANT.md`.
2. Open this framework folder with that assistant and say:

   > Read `START_HERE.md` and set this up for me.

3. Choose where your private Brain will live, confirm whether the assistant may save
   changes, and let it run the checks before starting your first task.

You do not need to learn Git or Python to follow the assisted setup. Your assistant
handles the commands and explains the choices. A chat website uses the user-run
paste workflow in `docs/ASSISTANT_ACCESS.md`; it cannot perform local setup itself.

## What it does

- Keeps memory, unfinished tasks, lessons, project updates and checkpoints in your
  private workspace, separate from this reusable framework.
- Lets another assistant recover verified durable context and continue your work.
- Saves through checked writers and supports interrupted-operation recovery.
- Offers optional local Git history, scanned skills, offline keyword recall and a
  user-installed MemPalace connection.

You decide which assistant names may write. A name, profile, skill or chat response
does not grant tools or permissions. The assistant must still perform its own work;
checkpoints do not prove that unsaved actions happened. Cloud recall is not the
authoritative record, and Aham does not automatically upload or synchronize your Brain.

## Supported systems

Python 3.10–3.14 on Linux and macOS for the core workspace lifecycle. Native
Windows core lifecycle is verified on hosted Windows with Python 3.14 and local
NTFS. Platform exclusions and exact evidence: `docs/PLATFORM_SUPPORT.md`.

This is a public preview, not a 1.0 release: real newcomer walkthroughs and some
live runtime evidence are still open.
Status, exact test evidence and historical runtime smoke tests: `docs/STATUS.md`.

## Why I built this

I am a working class non technical person. I have to jump through one deal to another for subscriptions. My pc is very old too and I cannot afford a Macbook Ultra or whatever it is called now with massive VRAM to run LLMs locally.

If you have gone from one subscription to another or have faced usage loss due to bugs on $30 monthly subscriptions then you will know the pain.

I cannot stick with just one LLM, I have to keep switching around, so I thought, what is one constant that has remained in all this jumping around?

The idea is simple: the tool you are using can change. Your memory, projects, lessons, unfinished work and history should stay with you.


## Help and source

The official repository is [loud-whisper/Aham-Brahmasmi](https://github.com/loud-whisper/Aham-Brahmasmi).
Check that address when choosing a copy or a fork.

Read `START_HERE.md` for setup, `docs/TROUBLESHOOTING.md` for a failing check,
`docs/ASSISTANT_ACCESS.md` for unlisted tools and chat websites,
`docs/MANUAL_SETUP.md` for manual inspection, and `docs/ARCHITECTURE.md` for how the
pieces fit. `PROJECT_CHECKLIST.md` and `docs/TEST_PLAN.md` retain the build gates.

Contributors: [contribution guide](CONTRIBUTING.md), [code of conduct](CODE_OF_CONDUCT.md)
and [changelog](CHANGELOG.md). Report vulnerabilities through the private route in
[the security policy](SECURITY.md); do not post private Brain content in issues.

## Why the name?

*Aham Brahmasmi* is a Sanskrit phrase commonly translated as “I am Brahman.” The name fits the central idea here: the underlying continuity remains even when the outward tool changes.

## License and support

Aham Brahmasmi is licensed under the Apache License 2.0.

If you are a regular non-business user, you are free to use it.

If you are a business, nonprofit, public-sector organization, etc., please ask me first.

The Apache 2.0 license is the legal license. The request above is a personal request from me, not an additional restriction on the rights Apache 2.0 grants you.

If any of you wish to buy me a subscription, help me toward a new desktop PC with 32 GB or more VRAM to run LLMs locally, or help me toward a MacBook with a large amount of unified memory for running LLMs locally, you can support me through [GitHub Sponsors](https://github.com/sponsors/loud-whisper) or [Ko-fi](https://ko-fi.com/vm1700) :)
