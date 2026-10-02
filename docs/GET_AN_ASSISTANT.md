# Get an assistant for setup

Choose a tool that can read and write local files and run local commands in the
folders you approve. It can be a terminal agent, an editor assistant or a desktop
agent. The tool's name is not enough: ask it to report the capabilities actually
available in this session before you let it set up a Brain.

If your existing assistant has these tools, open the framework folder and say:

> Read `START_HERE.md` and set this up for me.

You do not need to install another assistant merely because yours is not listed.
Unlisted tools use the universal file-reading bridge and the same explicit owner
trust rule. See `docs/ASSISTANT_ACCESS.md`.

## Official setup pointers

These are vendor instructions, checked 2026-10-01. Installation, accounts and tool
permissions remain your choices; Aham installs none of these automatically.

| Tool family | Official guidance |
| --- | --- |
| Claude Code | [Anthropic setup instructions](https://code.claude.com/docs/en/setup), including terminal and desktop choices. |
| Gemini CLI | [Google's installation guide](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/installation.mdx) and [quickstart](https://github.com/google-gemini/gemini-cli/blob/main/docs/get-started/index.md). |
| OpenAI tools | [OpenAI's current quickstart](https://learn.chatgpt.com/docs/quickstart). Verify local file and command access in the chosen interface; Aham retains its Codex-compatible instruction profile. |
| Local or other assistants | Use the tool maintainer's own installation instructions, then verify local file/command tools. Aham needs no particular model size or serving stack. |

If an installer asks for administrator rights or a permission window appears,
read it yourself and decide whether to approve. Reopen the terminal after a new
runtime or Python installation if needed, then check the actual command works.
Do not let an assistant record an intended installation as completed.

## If you only use a chat website

A chat window without local tools cannot create or verify files on your computer.
A local user or assistant first performs setup. You then export a bounded context
packet, inspect what it contains, paste it into the website, and import the model's
saved JSON response under your held writer session. Follow
`docs/ASSISTANT_ACCESS.md`. Chat responses are data; they never write directly.
