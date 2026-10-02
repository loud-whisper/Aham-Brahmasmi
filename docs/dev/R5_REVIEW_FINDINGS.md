# R5 supplementary review findings

This file is **not** the R5 working list. Active R5 work lives on branch `fix/r5-platform-git-hardening` (draft PR #43), whose `docs/dev/R5_TODO.md` and `docs/dev/CURRENT_WORK_CHECKPOINT.md` are the working list and handoff. `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` remains the controlling checklist.

This file records findings from a separate code and documentation review on 2026-09-28, done against `main` at `e33a9de` on Linux (Python 3.11, Git 2.43). The review did not initially see PR #43. Each finding below is then marked against PR #43 as of its head `63a4ce4`:

- **Covered by #43**: the branch already addresses it; no action unless #43 changes.
- **Partly covered by #43**: some of it is addressed; the remainder is listed.
- **Open**: not addressed on #43; fold into R5 on the #43 branch if it belongs to R5, otherwise keep for the named milestone.
- **Deferred with Windows**: only relevant once Windows durable mutation support is attempted; #43 documents Windows as unsupported.

Nothing was executed on macOS or Windows. Every open finding is a hypothesis: reproduce it with a failing regression test before changing code, and record "does not reproduce" if it does not. Items marked "believed" rest on platform documentation that must be re-verified from the named primary source.

## How to use this file

1. Finish and merge PR #43 first, following its own handoff. Do not start a parallel R5 branch.
2. For each **Open** item that belongs to R5, either add it to the #43 working list or record why it is out of R5 scope.
3. Items for R6-R8 are a parking list only. Do not start them from R5.

## Findings

### F1. Minimum Python version (Covered by #43)

#43 declares CPython 3.10 through 3.14 in `docs/PLATFORM_SUPPORT.md` and runs both endpoints in CI. Correction to this review: its original note that the scripts "parse under the Python 3.9 grammar" was a weak check. `ast.parse(..., feature_version=(3, 9))` does not reject PEP 604 unions such as `Path | None`, which fail at runtime on 3.9 outside postponed annotations. #43's 3.10 lower bound, backed by CI, stands.

### F2. `python3` is not the normal Windows command (Open, R5/R7)

`START_HERE.md`, `docs/MANUAL_SETUP.md`, `docs/TROUBLESHOOTING.md`, and recovery strings such as `scripts/checkpoint_core.py` ("Recovery command: python3 scripts/checkpoint.py ...") and `scripts/checkpoint.py` (`recovery_action=`) say `python3`. On Windows, `python3` commonly resolves to a Microsoft Store stub; the documented commands are `py -3` or `python` (verify in the Python docs section "Using Python on Windows"). On a fresh Mac, `python3` may trigger the Command Line Tools install prompt. Decide whether recovery actions should name the running interpreter (`sys.executable`) or give per-platform wording, and add a test.

### F3. Windows writer lock requires `fcntl` (Covered by #43 as a documented boundary; implementation Deferred with Windows)

`writer_lock()` in `scripts/state_store.py` fails closed without `fcntl`, which blocks checkpoint, wrap-up, resume, record lifecycle and export on native Windows. #43 documents Windows durable mutation as unsupported. When Windows support is attempted: the standard-library `msvcrt.locking` is a candidate, but its semantics differ from `flock` (mandatory byte-range locks; `LK_LOCK` retries for a limited time, then raises; verify in the Python `msvcrt` docs), so the independent-process concurrency regression (Astra F4) must pass on Windows before any claim. WSL2 could be offered as a Windows path only after it has its own evidence.

### F4. Windows junctions versus symlink refusals (Deferred with Windows)

M4 containment relies heavily on `Path.is_symlink()`. NTFS junctions are directory reparse points that `is_symlink()` does not report (believed; Python 3.12 added `os.path.isjunction` and `Path.is_junction`). Resolved-path containment may still catch them because `Path.resolve()` follows junctions, so reproduce first by junctioning a managed directory such as `state/` and attempting a checkpoint.

### F5. Immutable records use hard links (Open, R5)

`create_immutable_json()` in `scripts/state_store.py` publishes with `os.link()`. Hard links are unavailable on FAT32/exFAT volumes (common on USB drives, including on macOS, which #43 supports) and on some network or cloud-backed folders. Expected behavior: a clear refusal with an actionable message at setup/verify time, not a mid-operation failure. Add a test that simulates `os.link` raising `OSError`.

### F6. Durability on macOS (Open, R5)

`sync_directory()` silently returns on `OSError`. On macOS, `fsync(2)` is believed not to flush the drive's write cache; Apple documents `fcntl(F_FULLFSYNC)` for that (verify in Apple's `fsync(2)` man page). Because #43 declares macOS supported for the durable lifecycle, either implement the stronger flush where needed or document the weaker guarantee in `docs/STATE_WRITER.md` and `docs/PLATFORM_SUPPORT.md` so receipts do not overstate local durability.

### F7. Private directory permissions on Windows (Deferred with Windows)

`scripts/runtime_bridge.py` creates `.aham/` with `mode=0o700`, which Windows ignores. `.aham/runtime.json` holds private local paths.

### F8. Case-insensitive and Unicode-normalization collisions (Partly covered by #43)

#43 rejects portable-export paths that collide after NFC normalization and case folding. Remaining check: a regression proving project records, checkpoint heads and slugs cannot collide on a case-insensitive volume, including an accented project name.

### F9. Line-ending conversion (Partly covered by #43)

#43 neutralizes automatic CRLF conversion where Git transport controls the invocation. Remaining check: a user who copies or clones a Brain with their own Git and `core.autocrlf=true`. Decide whether the private workspace template needs a `.gitattributes` (for example marking state files `-text` or `eol=lf`) so R4 SHA-256 manifest comparison survives.

### F10. Missing `.gitignore` for Python caches (Resolved on `main`)

Running the suite created untracked `scripts/__pycache__/` and `tests/__pycache__/`. A root `.gitignore` containing `__pycache__/` was added on `main`. #43 does not add a `.gitignore`, so it merges without conflict.

### F11. Windows path limits and reserved names (Deferred with Windows)

Paths over 260 characters and reserved device names (`CON`, `NUL`, `AUX`, `COM1` and similar) in project names or slugs.

### F12. Cloud-synced folders (Open, R5/R7)

Beginners often choose Documents or Desktop, which OneDrive (Windows) or iCloud Drive (macOS) may sync. Sync clients can interfere with locks, atomic renames and hard links and can create "conflicted copy" files. Setup and `scripts/doctor.py` should warn when the workspace appears to be inside a known sync root, with a test. Detection heuristics must be verified per platform, not guessed.

### F13. Setup platform and capability gate (Open, R5/R7)

`START_HERE.md` section 1 asks the assistant to determine capabilities but does not require it to identify the operating system, confirm a Python in the declared range, or stop on a platform outside `docs/PLATFORM_SUPPORT.md`. Add an explicit "Step 0": detect OS and command capability; if the session cannot run local commands (for example a chat website), say so and stop instead of simulating setup; on native Windows, stop and point to the platform support document. Add documentation tests following `tests/test_documentation.py`.

### F14. No framework repairs during setup (Open, R5/R7)

When setup hits a framework failure, a capable agent may edit framework scripts to "fix" it, or report success that did not happen. `START_HERE.md` should instruct the assistant to stop, report the exact failing command and output, and point to `docs/TROUBLESHOOTING.md`, without modifying framework files or weakening checks. Add a documentation test.

### CI cost (Covered by #43)

#43 adds concurrency cancellation, removes duplicate feature-branch push runs, limits the matrix to support endpoints, and adds a self-hosted Linux runner.

## Running checks locally

From the repository root on `main`:

```
python3 tests/verify_foundation.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

On a Linux machine without bubblewrap installed, expect 12 failures, all reporting `bubblewrap (bwrap) is required for OS-enforced rehearsal isolation`. On the 2026-09-28 review run: 214 run, 12 failed, 5 skipped. Any other failure is real. #43 adds `tests/run_portability_suite.py` for the cross-platform subset once merged.

## Later milestones: parking list only

- **R7, "point any LLM at it" only works with local coding agents.** A chat website model runs on the provider's servers and cannot install anything on the user's device; only an agent harness running locally with file and command tools can (for example Claude Code, Codex CLI, Gemini CLI, OpenCode). Most of those agents must themselves be installed first. Add a beginner guide "Getting an assistant that can set this up", with steps verified from each agent's official documentation. README should state the requirement plainly.
- **R7, prerequisites written out per platform.** Add a short "Before you start" section with exact, verified per-platform steps for Python (and Git if used), for example the python.org installer or `winget` on Windows and python.org or Homebrew on macOS. Verify every command and package identifier against its official source before publishing.
- **R7, scripted human handoff moments.** Agents cannot click operating-system permission dialogs (Windows User Account Control, the macOS Command Line Tools installer), and a new Python is often not on `PATH` until a new terminal is opened. `START_HERE.md` should script these moments ("A permission window will appear; click Yes, then tell me when it is done"; "Close and reopen the terminal, then ask me to continue") and require approval before anything needing administrator rights.
- **R7/R8, official-source and fork safety.** "Point your assistant at this repository" is also the pattern an attacker would use with a modified fork whose `START_HERE.md` adds harmful commands. Name the official repository address in README and `START_HERE.md` and tie it to the final `PROVENANCE_COMMITMENT.json`.
- **R6/R7, a curated installer, not a monolith.** The goal of one beginner-friendly package that includes MemPalace and other tools must still respect `AGENTS.md` rules 6-8. Grow the reviewed default set behind `scripts/external_sources.py install-defaults` rather than copying or absorbing third-party code.
- **R7/R8, a narrow protection promise.** Aham protects durable Brain state and installs only reviewed sources. The included scanner is structural and cannot reliably detect instructions inside a third-party skill that steer a model into harmful actions (prompt injection). User-facing wording should say "protects your saved Brain and installs only reviewed sources", never "keeps you safe".
- **R7/R8, README for newcomers.** Keep the personal opening. Consider moving build-status tables, evidence IDs and milestone names to a status document, and internal working notes (`docs/dev/M5_TODO.md`, `docs/dev/M6_TODO.md`, `docs/dev/R5_TODO.md`, this file, `docs/dev/CURRENT_WORK_CHECKPOINT.md`) under a development subfolder before publication. Check doc-path references in tests first.
- **Phase 6/R8, Claude live evidence.** Claude is the only named runtime with no live rehearsal evidence in `evidence/runtime_harness_register.json`.
- **R8, comparison claims.** Do not claim that no similar project exists without a documented search. Other memory projects exist (for example Mem0, Letta, Basic Memory, and MemPalace itself). The defensible distinction is runtime neutrality plus beginner-first setup plus independent verification.

## R8 privacy findings and publication plan

### Maintainer intent

This repository itself is intended to become the public repository; it was created separately from the maintainer's private Brain so that no private data would enter it. The findings below come from assistant sessions, not from the maintainer copying private data.

### Scope and sensitivity

Making a repository public exposes every branch, every commit on them, and every pull request's commits, including closed and merged pull requests. Deleting a branch does not remove commits that a pull request still references. A pattern scan of all 45 remote branches and all pull request heads on 2026-09-28 found the following. This file deliberately does not repeat the sensitive values.

| Where | What | Sensitivity | In a pull request record? |
| --- | --- | --- | --- |
| `main` | Nothing found. All `main` commits use the GitHub no-reply author address. The evidence register records a Linux kernel string revealing the maintainer's distribution. | None / very low | n/a |
| Branch `review/astra-architecture-2026-09-18` | 7 commits authored with a personal email address instead of the GitHub no-reply address | **Moderate**: links the maintainer's GitHub identity to a personal address | No. Deleting the branch removes them from public view. |
| PR #43 (`fix/r5-platform-git-hardening`) | Private-range (RFC 1918) home-network addresses, a QEMU-default VM MAC address, a host machine name, and self-hosted runner service details, in docs and in the runner workflow's isolation probe | Low: private-range addresses are not reachable from the internet and are common router defaults; the MAC is randomly generated for the VM. Still conflicts with `AGENTS.md` rule 3. | **Yes.** They stay visible on PR #43 if this repository becomes public. |
| Branch `runner-smoke-20260920` | The same kind of network details in its workflow and docs | Low | No. Deleting the branch removes them from public view. |

The branch `review/astra-architecture-2026-09-18` also held the only copy of the original architecture review behind the "Astra F1-F11" findings. An exact copy (source commit `ccaedac`) is now preserved on `main` at `docs/dev/reviews/2026-09-18-astra-architecture-review.md`, so deleting the branch loses no content.

### Why the self-hosted runner matters at publication

PR #43's isolation probe needs the real addresses to prove the runner VM cannot reach the home network, and the runner is the maintainer's substitute for exhausted GitHub-hosted minutes. Keep it working until R5 acceptance is complete. However, GitHub's documentation recommends self-hosted runners only for private repositories: in a public repository, a pull request from anyone's fork can add a workflow that targets the runner and executes code on the maintainer's machine, subject to fork-approval settings. The VM containment reduces the impact but is not a reason to keep the runner attached to a public repository.

### Pre-publication checklist (ordered)

1. **When R5 acceptance is complete, before merging PR #43:** replace the specific addresses, MAC address and machine name in #43's docs with general wording ("the home router", "the workstation", "the runner VM"). Decide whether the self-hosted runner workflow and `docs/FEDORA_LIBVIRT_SELF_HOSTED_RUNNER.md` belong in the public framework at all; they describe maintainer infrastructure, not the product. If they stay, move the probe targets out of the file (for example into a repository Actions variable) and make the probe fail when the variable is missing rather than skip. Then merge as usual. The goal is that `main`'s files never contain these details.
2. **Before changing visibility:** remove the self-hosted runner from the repository (GitHub: repository Settings, Actions, Runners) and delete or disable workflows that target `self-hosted`. Confirm the fork pull request approval setting in repository Settings, Actions, General. Verify the exact setting names against GitHub's current documentation.
3. **Before changing visibility:** delete branches `review/astra-architecture-2026-09-18` and `runner-smoke-20260920`. Neither is referenced by a pull request. Confirm the architecture review copy on `main` first.
4. **Prevent recurrence:** in GitHub account email settings, keep the email address private and enable blocking of command-line pushes that expose it (verify current setting names in GitHub's "Setting your commit email address" documentation). Configure every machine and assistant session that commits here to use the GitHub no-reply address.
5. **Decide on the remaining branches:** most other branches are merged feature or evidence branches and matched no pattern in the scan. Keep or delete them as a tidiness decision; evidence branches may be worth keeping because evidence IDs refer to them.
6. **Accept or escalate PR #43's record:** the low-sensitivity network details stay visible in PR #43's commit list after publication. GitHub Support can be asked to remove pull request data if that is ever judged necessary.
7. **Human review:** re-run an all-branch and all-pull-request scan immediately before publication, then do the required human privacy and history review. Pattern scans do not replace it.
