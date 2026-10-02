# Aham Brahmasmi: audit findings and public-release plan

Prepared 2026-10-01 for `loud-whisper/Aham-Brahmasmi`.
Audited against `main` at `be97c50` and draft PR #43 (`fix/r5-platform-git-hardening`) at `63a4ce4`.
This is a plan only. Nothing in the repository was changed while preparing it.

---

## Implementation status: 2026-10-01

This is the retained audit plan, not a claim that its unchecked work is complete.
The maintainer requested PR #43 be accepted and merged before starting remaining
milestones, so R5 landed before P0 reconciliation. R5 exact-head acceptance at
`c480e00073416f254493bfc218a6de1516200e51` passed all six jobs in workflow
`36861543247`; PR #43 merged as `4a3b0d47c98aa354ef64f14f2e78bf1abbea4989`.
D1 is resolved: hosted macOS Python 3.10/3.14 acceptance executed and passed.
Windows acceptance demonstrated unsupported-write refusal only. Native Windows
support remains W1 and requires D3. No release-staging change is approved: the
existing private-until-walkthrough/publication-authorization gates remain in force.
R6 merged through PR #48 as `63d5fcf22e55c93b11fc3dfdeba44bb38dba1651`.
Exact tested head `eddff878b2ab328ae1527ee901b5ec539bcd6901` passed all six
jobs in workflow `36866478419`: 248 Linux tests, 213 tests per portability job
(two skips per macOS job), and Windows refusal checks. R6 recall was explicitly unverified; S4 now maps exact committed bindings. S1 merged through PR #50 as
`4e2d68ad13cefc927539ae7a68063bc72a282270`; exact head `de9c1ea` passed all six
jobs in workflow `36873888390`. D5/D6 are approved opt-in features. Pinned Superpowers
produced FAIL at S1 completion; S3's tested context corrections now produce REVIEW,
with activation blocked until exact findings are accepted. S2 merged through PR #52 as `74633e0ad7874696388bb199e0a47d57638af5db`;
corrected head `476222d` passed all six jobs in workflow `36879782673`. A local
regression reproduced and fixed the macOS parent-alias failure from its initial
matrix. D4 is approved: universal bridge first, native copies later. S3 merged
through PR #55 as `8c76a10f779f7a9025b33e8805ab4a1cf45a320e`; exact head `d748ca4`
passed all six jobs in `36897056292`. D8: review Superpowers first; defer more
defaults. S4 merged through PR #57 as `47c32ed8fee5b44cd4743bc6e8e2c1f7042bc4e1`;
corrected head `d406545` passed all six jobs in `36904820142`. D10: include offline
keyword recall. Whole-tree MemPalace scans remain FAIL; no source activation is
approved by its CLI interface review. A1 is complete; R7 is next.
Other decisions are asked at their milestone.

The original audit below describes the historical starting point. Current status
is owned by `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` and
`docs/dev/CURRENT_WORK_CHECKPOINT.md`.

## 0. Instructions for the executing LLM

Read this section fully before doing anything.

1. **This plan adds work; it does not replace the repository's rules.** Read `AGENTS.md` first. Its non-negotiable boundaries and stop conditions win over this document wherever they conflict.
2. **Order matters.** Work one milestone at a time in the order given in section 6. The first unchecked milestone in `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` is still R5. Do not start a later milestone because it is easier or more interesting.
3. **One milestone, one branch, one PR.** Never commit to `main` directly. Regression first: write the failing test, show it failing in CI, then implement. Update checklists only after the acceptance gate is demonstrated with evidence (commit and workflow run).
4. **Read before working:** `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md`, `docs/LESSONS_LEARNED.md`, `docs/dev/R5_REVIEW_FINDINGS.md`, `docs/dev/reviews/2026-09-18-astra-architecture-review.md`, and on the PR #43 branch: `docs/dev/R5_TODO.md`, `docs/dev/CURRENT_WORK_CHECKPOINT.md`, `docs/PLATFORM_SUPPORT.md`.
5. **Verify every external fact at implementation time.** Anything marked `VERIFY` below is unverified or may have changed since 2026-10-01. Verify it from the primary source (official docs, upstream repository at a pinned commit). If you cannot verify, record it as unresolved and stop that item. Do not guess command names, flags, file locations, spec fields or setting names.
6. **Privacy rule.** Never write machine names, network addresses, MAC addresses, personal email addresses, local usernames or similar details into any file, commit message, issue or PR. Some already exist on PR #43 and on certain branches; refer to them only generically ("the runner VM", "the home network"). Do not copy them out of `docs/dev/R5_TODO.md` on the PR #43 branch.
7. **Decisions.** Items marked `DECISION Dn` need the maintainer. Ask once, put the recommended option first, and do not pass a blocking decision on your own.
8. **Dependencies.** The framework is standard-library-only Python today (verified: no third-party imports in `scripts/` or `tests/`). Keep it that way unless a decision approves a dependency.
9. **Maintainer-only actions.** Do not change repository visibility, delete branches, remove runners, or change GitHub settings. Prepare checklists for those; the maintainer performs them.
10. **Honest claims.** A single successful run is a smoke test, not a reliability figure. Never weaken a verifier or test to get a pass.

---

## 1. What the project is

**Purpose.** Aham Brahmasmi is a model-neutral "Brain" framework. A person keeps their memory, tasks, lessons, projects, history and recovery points in a private workspace they own. Whatever assistant they use today (Claude, Gemini, Codex, a local model, a future tool) reads and updates that same workspace through one set of rules and commands. Switching tools, crashing, or closing the session must not lose accepted work.

**The pieces (paths are relative to the repository root):**

| Piece | Where | Role |
| --- | --- | --- |
| Entry docs | `README.md`, `START_HERE.md` | Human story; the one-line setup instruction ("Read START_HERE.md and set this up for me") and assistant instructions |
| Core contracts | `core/*.json` | Model-neutral rules: modes, state routes, lifecycle, memory, Git transport, semantic memory, external sources, backup, conformance |
| Private workspace template | `templates/private-workspace/` | `BRAIN.json`, `MEMORY.md`, `TODO.md`, `LESSONS.md`, `projects/`, `history/`, `state/` |
| Writer and lifecycle | `scripts/state_store.py`, `checkpoint*.py`, `wrap_up*.py`, `resume.py`, `record_lifecycle.py`, `session_authority.py`, `operation_receipt.py` | One authoritative writer, monotonic revisions, immutable operation IDs, crash-safe commit boundary, receipts |
| Startup and context | `scripts/startup.py`, `context_packet.py`, `runtime_profiles/` | Ready report, session authority, bounded project context packets |
| Runtime bridges | `scripts/runtime_bridge.py`, `core/runtime_adapter.json` | Writes `.aham/runtime.md` plus a marked block in `CLAUDE.md`, `GEMINI.md` or `AGENTS.md`; private paths stay in ignored `.aham/runtime.json` |
| Optional memory | `scripts/semantic_memory.py` | MemPalace CLI adapter (status, search, wake-up), never authoritative |
| Optional history | `scripts/git_transport.py` | Local Git snapshots of an allowlist of durable files; no remote |
| Skills and tools | `third_party/registry.json`, `scripts/external_sources.py`, `third_party.py`, `scan_external.py` | Registry with pinned commits, fetch into quarantine, scan, activate on PASS |
| Backup | `scripts/portable_backup.py` | Provider-neutral export and verified restore |
| Diagnostics | `scripts/doctor.py`, `docs/TROUBLESHOOTING.md` | Plain-language checks with a next action |
| Evidence | `evidence/runtime_harness_register.json`, `scripts/runtime_evidence.py` | One source of truth for live-runtime claims, rendered into README and checklist |

---

## 2. Current state (verified on 2026-10-01)

- **Checks on `main`** (Linux, Python 3.11, Git 2.43, bubblewrap not installed): `python3 tests/verify_foundation.py` passes. `python3 -m unittest discover -s tests -p 'test_*.py'` ran 214 tests: 12 failed, 5 skipped. All 12 failures report that bubblewrap is required. This matches the expectation recorded in `docs/dev/R5_REVIEW_FINDINGS.md`.
- **Hands-on smoke test** in a scratch folder: `setup_workspace.py`, `verify_workspace.py`, `startup.py` and `doctor.py` all worked and produced plain-language output.
- **Completed:** M1 to M6, the post-M6 runtime/harness sequence, R1 (migrations), R2 (fact/task lifecycle), R3 (context packets and conformance tiers), R4 (portable backup/restore).
- **In progress:** R5 on draft PR #43. Linux acceptance is green on the self-hosted runner. macOS acceptance is blocked because the private repository's hosted Actions minutes are exhausted. A guest-reboot persistence proof for the runner is also outstanding.
- **Not started:** R6, R7, R8. Also open: Claude live evidence (Phase 6), the low-context footprint item (Phase 6), the nontechnical walkthrough (Phase 7), and the remaining Phase 8 release gates.
- **Remote branches:** 45, including evidence branches referenced by evidence IDs. `claude/aham-public-release-2sznx8` has no difference from `main`.

---

## 3. Audit findings

Severity: **High** blocks a stated goal or creates real risk; **Medium** degrades a goal; **Low** is polish.

| ID | Finding | Evidence | Severity | Addressed in |
| --- | --- | --- | --- | --- |
| F-01 | `docs/dev/CURRENT_WORK_CHECKPOINT.md` on `main` (dated 2026-09-19) says no R5 work has started, but R5 is active on PR #43. A fresh agent reading `main` gets the wrong starting point. | File on `main` vs checklist R5 note and PR #43 | Medium | P0 / R5 |
| F-02 | Write authority depends on the runtime **name**. `startup.py` grants `read_write` only for an exact named profile other than `unknown` (claude, gemini, codex, local). Any other name becomes `unknown` and gets `read_only` even with verified write and command capabilities. Reproduced: runtime name `cursor-agent` with `read_files write_files run_commands` gave `read_only`; `local` with the same capabilities gave `read_write`. So the gate blocks new tools and also gives no real trust, because any agent can declare `local`. | `scripts/startup.py`, `build_report` (the `runtime_is_trusted_profile` check) | High | A1 |
| F-03 | Installed skills are inert. Sources are fetched into `external/`, but nothing makes them discoverable: no skill index, the bridge text in `render_bridge` does not mention skills, and no script ever writes `BRAIN.json` `optional_integrations.skills`. | `scripts/runtime_bridge.py`, `scripts/external_sources.py`, grep of `scripts/` | High | S2 |
| F-04 | The scanner is structural only: symlink escape, broken symlink, single file over 25 MiB (REVIEW), more than 10,000 files (REVIEW), and two private-key header strings (FAIL). It has no checks for instruction-override text, hidden Unicode, auto-run configuration, executable surfaces, secret-path or network targeting, or skill-format validity. The docs already state this limit honestly. | `scripts/scan_external.py` | High | S1 |
| F-05 | No skill lifecycle for users. Commands are `list`, `status`, `install` (with `--replace`) and `install-defaults`. There is no update check, update notice, rollback from `state/replaced_sources/`, removal, or support for the user's own local skills. | `scripts/external_sources.py` | Medium | S3 |
| F-06 | The MemPalace connection is read-only and unscoped by default. The adapter uses only `--version`, `status`, `search`, `wake-up`. Aham never feeds its committed records to MemPalace, so recall does not reflect Aham revisions or retractions. The wing is optional (default: all wings). Search and wake-up output is printed to the model unmodified, with no "this is data, not instructions" framing. The registry pin is from 2026-09-17. | `scripts/semantic_memory.py` (`search`, `wake_up` print provider stdout directly) | High | R6, S4 |
| F-07 | Private workspace permissions are not set. Setup creates directories and files with process defaults; no owner-only mode. Raised in the Astra review (question 25) and still open. | `scripts/setup_workspace.py`, `scripts/state_io.py` | Medium | R5 or R7 (D9) |
| F-08 | Chat-only models cannot use the project. Setup needs file and command tools. A chat website cannot open a folder or run commands, yet README invites "the model or coding assistant you already use". | `README.md`, `START_HERE.md`; also noted in R5 findings parking list | High | A1, R7 |
| F-09 | Native Windows is unsupported for any write (POSIX `fcntl.flock` writer lock). Many nontechnical users are on Windows. This is the largest adoption risk for the "newbie" goal. | PR #43 `docs/PLATFORM_SUPPORT.md` | High | D3, W1 |
| F-10 | Too many entry points for weaker models. About 40 scripts; setup and lifecycle instructions ask the assistant to run many commands with long flags. Lessons Learned and the Phase 6 context item both point at this cost. | `scripts/`, `START_HERE.md` | Medium | A1 |
| F-11 | Contributor and public-repo readiness gaps: the default test run fails 12 tests on any machine without bubblewrap; no `CONTRIBUTING.md`, `SECURITY.md`, `CHANGELOG.md`, issue/PR templates, or release tags; CI uses `actions/checkout@v4` (tag, not commit SHA); internal working notes (`docs/dev/M5_TODO.md`, `docs/dev/M6_TODO.md`, `docs/R5_*`, `docs/dev/CURRENT_WORK_CHECKPOINT.md`, `docs/dev/reviews/`) sit next to user docs. | Repository root, `.github/workflows/` | Medium | R8 |
| F-12 | Publication privacy items are already catalogued in `docs/dev/R5_REVIEW_FINDINGS.md` ("R8 privacy findings and publication plan"): a branch with commits authored by a personal address, infrastructure details on PR #43 and another branch, and the risk of a self-hosted runner on a public repository. | `docs/dev/R5_REVIEW_FINDINGS.md` | High | R5, R8 |
| F-13 | README is long and status-heavy for a newcomer (phase tables, evidence IDs, milestone names). | `README.md` | Low | R7 |
| F-14 | Claude has no live rehearsal evidence; the low-context footprint item is open. | `evidence/runtime_harness_register.json`, `PROJECT_CHECKLIST.md` Phase 6 | Medium | E1 |

**Not re-audited:** the Astra review's note (question 17) that validation and Git execution are duplicated across modules. Check whether it still holds before relying on it.

**Strengths to preserve:** standard-library-only Python; regression-first discipline with retained evidence; strict separation of framework, private Brain and project; one writer with receipts; honest scope wording; registry with pinned commits and quarantine. None of the work below may weaken these.

---

## 4. Goals and non-goals

### Goals (maintainer's request, made measurable)

| ID | Goal | How we know it is met |
| --- | --- | --- |
| G1 | Model agnostic | An agent with file-read, file-write and command tools, using any model or tool name, can complete setup, checkpoint, wrap-up and recovery without being on a name list. |
| G2 | Reachable by chat-only models | A chat-only model can read a bounded context packet and propose a wrap-up that the user saves and Aham validates through the normal writer. |
| G3 | Newcomer friendly | Nontechnical testers on a supported OS complete setup, a model switch and an interrupted-operation recovery without help (R7 gates). |
| G4 | Skills connected | Installed skills are usable by any runtime through one portable path, and by native skill loaders where that is verified. |
| G5 | Prompt-injection safeguards | Every skill passes scanner v2 before activation; findings are explained in plain language; changes after activation are detected. |
| G6 | Skill updates | Users can see, apply and roll back reviewed updates; maintainers have a repeatable review workflow for new upstream commits. |
| G7 | MemPalace connected safely | Recall is project-scoped, labeled as untrusted data, and optionally fed from committed Aham records. |
| G8 | Public | R8 passes with no private data in any published branch or pull request, and the maintainer authorizes publication. |

### Non-goals (keep out of scope)

No universal agent orchestrator, no model serving, no skill marketplace, no automatic provider-account management, no autonomous memory rewriting without provenance, no telemetry, no silent installs, no automatic trust of upstream updates, no cross-machine sync in this plan. These come from the Astra review (question 30) and remain valid.

**User-facing promise wording:** "Protects your saved Brain and installs only reviewed, scanned sources." Never "keeps you safe" (from `docs/dev/R5_REVIEW_FINDINGS.md`).

---

## 5. Decisions needed from the maintainer

| ID | Question | Options | Recommendation and uncertainty |
| --- | --- | --- | --- |
| D1 | macOS evidence for R5 is blocked by exhausted hosted Actions minutes. | (a) Pay for minutes for one exact-head run. (b) Narrow R5's macOS statement to "not yet verified", merge Linux-only R5, verify macOS on hosted runners after publication. (c) Use another Mac. | (b): free and consistent with the no-unproven-claims rule. `VERIFY` in GitHub's Actions billing documentation that standard hosted runners are free for public repositories. Requires editing `docs/PLATFORM_SUPPORT.md` on PR #43. |
| D2 | Release staging. Today the repo stays private until the nontechnical walkthrough passes. | (a) Keep that gate. (b) Publish a clearly labeled public preview (v0.x) after R6, S1 and the R8 privacy items; release 1.0 after R7 walkthroughs and W1. | (b) breaks the chicken-and-egg problem (Windows and macOS CI become affordable once public). Risk: newcomers try a preview that is not ready for them, so README must state the audience. This changes an existing release gate, so it needs your explicit approval. |
| D3 | Windows. | (a) Stay unsupported. (b) Document WSL2 as the Windows path, only after it has its own evidence. (c) Native Windows lock and Windows CI (milestone W1). | (c), with (b) as an interim only if evidenced. Windows matters for the newcomer goal. |
| D4 | How skills reach native skill loaders. | (a) Instruction-only universal path. (b) Copy active skills into the runtime's native skill folder with a digest check. (c) Symlink. | (a) first in S2, then (b) per runtime after the native location is verified from official docs. Avoid (c): it conflicts with the M4 symlink containment rules. |
| D5 | Optional model-assisted skill review. It sends third-party skill text to whatever model the user runs, possibly a hosted one. | (a) Off. (b) Opt-in and advisory. | (b): opt-in, can only make a verdict stricter, never looser. |
| D6 | Optional external scanners (for example `cisco-ai-defense/skill-scanner`, `VERIFY` license, offline behavior and output format). | (a) No. (b) Allowed as optional registry sources behind the scanner interface. | (b): optional, never required, must pass the normal third-party policy. |
| D7 | MCP server for desktop apps and harnesses. | (a) Official SDK dependency. (b) Standard-library implementation of the needed subset. (c) Defer. | (c): decide after 1.0. Hand-rolling a protocol is risky; adding a dependency changes project policy. |
| D8 | Which skill collections to review next for the default set. | Your choice, using the criteria in S3. | Start with one small, well-maintained collection to exercise S1 and S3 end to end. |
| D9 | Owner-only permissions on the private workspace. | (a) Enforce `0700`/`0600` on POSIX at setup and check in doctor. (b) Warn only. | (a). On Windows, ACLs belong to W1. |
| D10 | Built-in "lite recall" provider (standard-library keyword search over committed records). | (a) No. (b) Yes, as a second provider behind the same interface. | (b) is optional but gives newcomers recall with zero installs and proves the interface is replaceable. |

---

## 6. Phased plan

**Order:** P0 → R5 → R6 → S1 → S2 → S3 → S4 → A1 → R7 → W1 (per D3) → R8. E1 can run whenever budget allows after A1 (it is evidence, not code). "Later" items wait until after 1.0.

Why this order: R5 is already in flight and controls the queue. R6 binds activated content to its scanned identity, which S1 needs. The scanner (S1) must exist before skills become easier to use (S2) and update (S3). MemPalace work (S4) reuses R6 scoping. The single entry point (A1) must exist before onboarding docs (R7) are rewritten around it. Publication (R8) comes last.

Each milestone below lists: goal, tasks, acceptance gate, and notes. File names are suggestions; follow existing naming patterns.

### P0. Planning reconciliation (documentation only)

**Goal:** make the repository's own sources of truth reflect this plan before any code work.

**Tasks:**
1. Commit this document as `docs/PUBLIC_RELEASE_PLAN.md` (or under `docs/dev/` if R7's move happens first). Do not include anything that violates rule 6 in section 0.
2. Add unchecked milestones S1, S2, S3, S4, A1, W1 and E1 to `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` in a new section after R7 (for example "Product completion before public release"), each with its acceptance gate copied from this plan. Keep R5 as the first unchecked item.
3. Add short matching lines to `PROJECT_CHECKLIST.md` (Phase 4, 6, 7 and 8 as appropriate).
4. Do not edit `docs/dev/CURRENT_WORK_CHECKPOINT.md` on `main` in this PR, because PR #43 rewrites it. Instead, make sure PR #43's version lands (it fixes F-01). If PR #43 stalls for weeks, add a two-line pointer at the top of `main`'s copy and resolve the conflict when #43 merges.

**Acceptance gate:** foundation checks and documentation tests pass; no code changed; PR #43 still merges cleanly or its conflicts are trivial and documented.

### R5. Finish platform and Git hardening (existing PR #43)

**Goal:** complete R5 exactly as its own handoff describes, plus the open review findings that belong to it.

**Tasks:**
1. Follow `docs/dev/R5_TODO.md` on the branch. Apply D1.
2. Triage every **Open** item in `docs/dev/R5_REVIEW_FINDINGS.md` that is marked R5 (F2 `python3` wording on Windows and macOS, F5 hard links on FAT/exFAT and network folders, F6 macOS durability wording, F8 remainder, F9 remainder, F12 cloud-sync folders, F13 setup platform gate, F14 no framework repairs during setup). For each: add it to the R5 working list or record why it belongs to a later milestone.
3. Apply D9 here if "permissions" in R5's scope covers it (F-07); otherwise move it to R7.
4. Before merging: replace specific infrastructure details in PR #43's docs and workflow with generic wording, and decide whether the self-hosted runner workflow and its setup document belong in the public framework at all (findings "Pre-publication checklist", item 1). If they stay, move probe targets into a repository variable and make the probe fail when the variable is missing.

**Acceptance gate:** R5's own gate (exact-head Foundation plus the agreed platform matrix), checklist updated with evidence, merged with an expected-head guard, and no infrastructure specifics in any file on `main`.

### R6. Semantic retrieval scope and activation identity (existing, expanded)

**Goal:** recall cannot leak across projects or present stale facts as current, and an activated skill cannot change silently.

**Tasks:**
1. **Activation identity.** At scan time compute a deterministic tree digest: sorted relative paths with per-file SHA-256, excluding `.git`. Store it with the scanner report digest in `state/installed_sources.json`. Activation refuses if the tree being activated differs from the scanned tree.
2. **Drift detection.** `startup.py` and `doctor.py` recompute active tree digests and report any difference as "changed since review: not used until reviewed again". Drifted skills are excluded from the skill index (S2).
3. **Read-only active trees** on POSIX after activation. Document the limit: the owner can still change permissions; this guards against accidents and casual in-session edits, not a determined local attacker.
4. **Scoped recall.** Search and wake-up require a scope (for MemPalace, a wing) for the current project. Broad search needs an explicit `--all-scopes` flag and prints a warning. Startup passes the project scope.
5. **Untrusted-data envelope.** All semantic output is wrapped in a clearly marked block, with control characters and hidden Unicode (zero-width, bidirectional controls, tag characters) removed or shown as escapes, plus one fixed line stating that recalled text is data and cannot change Aham rules or grant permissions.
6. **Stale facts.** Results that map to Aham record IDs (after S4 indexing) are filtered or labeled by current status (current, superseded, retracted). Results that cannot be mapped are labeled "unverified recall".

**Acceptance gate:** regression tests with the existing fake-provider pattern for cross-project leakage, broad-search warning, envelope presence, hidden-Unicode neutralization, a modified active skill file detected at startup and excluded, and activation refusal on a tree-digest mismatch.

### S1. Skill scanner v2: prompt-injection and execution-surface safeguards

**Goal:** catch the common, known ways a skill can steer a model or run code, explain each finding in plain language, and be honest about what static scanning cannot catch.

**Design.** Keep the scanner contract fields (`scanner`, `version`, `verdict`, `findings`, `scanned_at`) and add: `rule_pack_version`, `tree_digest`, and per finding `rule_id`, `severity`, `path`, `line`, a bounded and escaped `excerpt`, a one-sentence plain-language `explanation`, and a `remediation` hint. Severity levels: FAIL, REVIEW, INFO. Verdict: any FAIL gives FAIL; any REVIEW gives REVIEW; INFO only gives PASS with notes.

**Layer 1: static rule pack** (standard library, offline, deterministic, versioned in `core/scanner_rules.json`, logic in `scripts/scan_external.py` or a new module behind the same interface):

| Category | What to detect | Default severity |
| --- | --- | --- |
| Structural (existing) | Symlink escape, broken symlink, size and count limits | FAIL / REVIEW as today |
| Secrets | Private key headers (existing); common token formats (`VERIFY` each format from the issuer's documentation) | FAIL |
| Hidden or deceptive text | Zero-width characters, bidirectional control characters, Unicode tag characters, long HTML comments in Markdown, very long single lines, large base64 or hex blobs in instruction files | REVIEW; FAIL for bidirectional controls or tag characters inside `SKILL.md` or other instruction files |
| Instruction override | Text that tells the model to ignore earlier instructions, hide actions from the user, claim system or vendor authority, create false urgency, or change its role | REVIEW; FAIL when combined in the same file with a sensitive target or network rule |
| Aham lifecycle tampering | Instructions to write `BRAIN.json`, `MEMORY.md`, `TODO.md`, `state/` or `.aham/runtime.json` directly; to print or imitate receipt markers (`CHECKPOINT VERIFIED`, `WRAP UP VERIFIED`, `RESUME STATE VERIFIED`); to skip checkpoints or verification; to edit framework scripts | FAIL (this rule set is specific to Aham and is a real differentiator) |
| Sensitive targets | SSH keys, cloud credential files, browser profile and cookie stores, password stores, `.env` files, shell history, OS keychains | REVIEW in prose; FAIL when read by a bundled script |
| Network and exfiltration | Download-and-execute pipes, file uploads to webhooks or paste sites, raw IP URLs, tunnelling tools | REVIEW; FAIL for download-and-execute |
| Execution surfaces | Executable files, shebang scripts, compiled binaries, package lifecycle scripts, Git hooks, agent-tool hook or settings files, editor tasks that run when a folder opens, MCP server configuration files | REVIEW, listed so the user sees "this skill can run code". `VERIFY` every tool-specific filename from that tool's official docs before adding a rule |
| Skill format | Agent Skills rules for `SKILL.md`: `name` 1 to 64 characters, lowercase letters, digits and hyphens, no leading, trailing or consecutive hyphens, must match the folder name; `description` 1 to 1024 characters; `compatibility` up to 500 characters (verified from agentskills.io/specification on 2026-10-01) | REVIEW on violation; INFO when `SKILL.md` exceeds about 500 lines (spec guidance) |
| Permission requests | `allowed-tools` (experimental in the spec) pre-approving shell or broad tools | REVIEW |
| Description mismatch | Description claims a narrow task while the body or scripts touch network, credentials or the Brain | INFO or REVIEW (heuristic, keep conservative) |

**Layer 2: diff-aware updates.** On `--replace`, scan the full new tree and also report which findings are new compared with the previously accepted report, so reviewers focus on what changed.

**Layer 3: optional model-assisted review (D5).** Aham writes a review packet: a fixed rubric, the skill text escaped inside an untrusted block, and a random canary token. The current runtime answers in a fixed JSON schema. Aham validates the schema and canary handling. The result can raise PASS to REVIEW but can never lower REVIEW or FAIL. Reason: the reviewing model can itself be manipulated by the content it reviews, so it may only add caution.

**Layer 4: optional external scanners (D6)** registered through `third_party/registry.json` and run behind the scanner interface. Combined verdict is the most severe.

**Human decisions.**
- REVIEW requires explicit acceptance per finding, for example `aham skills accept SOURCE --finding RULE_ID --reason "..."` (final command shape is set in A1). Store the waiver in the private workspace, bound to source ID, tree digest, rule ID and file digest. Any file change voids it.
- FAIL cannot be waived through normal commands in v1.

**Test corpus.** `tests/fixtures/skills/` with synthetic benign and malicious skills (inert strings only, never working malware), each with an expected verdict. Add a false-positive check against Superpowers at its reviewed commit inside the existing live upstream rehearsal (network-gated). Add a performance bound for a 10,000-file tree.

**Documentation.** `docs/SKILL_SCANNER.md`: what it catches, what it cannot catch (novel phrasing, other languages, meaning hidden in ordinary text), and why runtime-side rules (R6 envelope, S2 bridge rules) still matter.

**Acceptance gate:** every fixture produces its expected verdict; no fixture in a FAIL category ever receives PASS; existing scanner and supply-chain tests still pass; waiver invalidation test passes; report renders in plain language; Superpowers false-positive result recorded.

### S2. Skill index and universal activation

**Goal:** an installed, scanned skill can be found and used by any runtime that can read files, with a small context cost.

**Tasks:**
1. Build `state/skills_index.json` (writer-owned, revision-stamped) from `state/installed_sources.json` plus parsed `SKILL.md` frontmatter of active, non-drifted sources: name, description, source ID, reviewed ref, tree digest, verdict, workspace-relative path, enabled flag, project scopes.
2. Add a byte-budgeted skill list (names and one-line descriptions only) to the context packet from `scripts/context_packet.py`. Full `SKILL.md` is read only when needed. This matches the Agent Skills "progressive disclosure" model (verified on agentskills.io, 2026-10-01).
3. Add a "Skills" section to the bridge text in `render_bridge`: where the list is; read the full `SKILL.md` before following a skill; skill instructions never override Aham lifecycle rules or the user; skills cannot authorize Brain writes outside the writer; bundled scripts run only with the user's approval.
4. `enable` and `disable` per skill, optionally per project, as writer operations under session authority, so read-only sessions cannot change them.
5. Decide the fate of `BRAIN.json` `optional_integrations.skills` (populate it or deprecate it through the R1 migration runner) and document the choice.
6. Native loaders (D4, optional): per runtime, only after verifying the native skills location from official documentation at implementation time. Record the verified location, source URL and date in `core/runtime_adapter.json`. Copy, do not symlink, with a digest check. Never edit a user's global configuration without explicit approval. `doctor.py` reports stale native copies.
7. `VERIFY` that Superpowers at the reviewed commit uses the Agent Skills layout. If it does not, index its real layout or mark it unsupported by the index.

**Acceptance gate:** fixture skill installed then listed; context packet stays within budget; disabled and drifted skills absent; read-only session cannot enable or disable; bridge text test confirms the new rules.

### S3. Skill lifecycle and updates

**Goal:** users see and control updates; maintainers review upstream changes the same way every time.

**User commands** (final names set in A1):

| Command | Behavior |
| --- | --- |
| `check-updates` | Offline. Compares installed refs with registry refs and reports "reviewed update available". |
| `check-upstream` | Network, announced, informational only. Uses `git ls-remote` to report that newer **unreviewed** commits exist upstream. Never installs. |
| `update SOURCE` | Uses the existing quarantine and `--replace` path, shows the S1 diff report, asks for confirmation when the verdict is REVIEW. |
| `rollback SOURCE` | Restores the previous copy from `state/replaced_sources/` through the R5 activation journal, then re-verifies its digest. |
| `remove SOURCE` | Deactivates, updates manifest and index; deleting files needs explicit confirmation. |
| `add-local PATH` | The user's own skill folder: copied into quarantine, scanned, activated with provenance "local" (digest only, no upstream). Never added to the public registry. |

Startup and doctor show one line such as "Skills: 2 active, 1 reviewed update available".

**Maintainer workflow:**
1. `docs/SOURCE_REVIEW.md`: a checklist for adding or bumping a registry source: license at the exact commit, maintenance signals, reading the diff, scanner v2 report, no auto-run hooks unless justified, notices update, registry entry, tests.
2. Record the expected scanner verdict and rule-pack version at the reviewed commit in the registry, so a user-side difference signals a rule-pack or content change.
3. Optional scheduled workflow (after D1/D2 make minutes available): weekly `git ls-remote` for each registered source; opens or updates one issue listing commits newer than the pin. Read-only permissions; no automatic PRs.
4. Default-set criteria (D8): license compatible and clear; actively maintained; scanner PASS or only waivable REVIEW; useful to newcomers; no required network services or accounts.

**Acceptance gate:** each command tested with synthetic local Git repositories (the existing test pattern), including rollback after a failed update and crash during rollback.

### S4. MemPalace connection v2

**Goal:** MemPalace stays optional but becomes easy to connect, project-scoped, safe to read, and optionally fed from Aham's committed records.

**Tasks:**
1. **Re-review** MemPalace at a newer upstream commit through the S3 maintainer workflow. Confirm the four commands the adapter uses still exist with the same flags; update fake-provider contract tests.
2. **Guided connection.** `doctor.py` (and later `aham memory setup`) detects whether `mempalace` is on `PATH`. If not, it shows the install options documented by upstream at the reviewed commit and lets the user choose. As of 2026-10-01 the upstream README lists `uv tool install mempalace`, `pipx install mempalace`, a Docker image, and an agent-guided `npx skills add MemPalace/mempalace` path (`VERIFY` at the reviewed commit). Aham never installs anything without explicit approval.
3. **Scoped by default.** Per-project scope from the stable project ID or a user-chosen wing, set when a project is connected. Uses the R6 scoping.
4. **Write path (opt-in).** After a committed wrap-up, export committed records (facts, tasks, lessons, project updates) as plain files stamped with record ID, project ID, revision and status into a transient staging folder; ask MemPalace to index it using its verified ingest command (the upstream README lists `mempalace mine`; `VERIFY` exact usage and whether re-indexing updates or duplicates). Record the indexed revision; `status` reports lag, for example "recall is 2 revisions behind". Failure never blocks wrap-up. The staging folder is excluded from Git snapshots and portable export.
5. **MCP note.** Upstream documents its own MCP server (README, 2026-10-01). Document that a runtime may connect to it directly, that its write tools are not Brain writes, and that Aham records stay authoritative. Do not build an MCP bridge here.
6. **Optional lite recall (D10).** A standard-library keyword provider over committed records, behind the same interface in `core/semantic_memory.json`.

**Acceptance gate:** fake-provider tests for scope enforcement, envelope, index-lag reporting, failure isolation, and no write without opt-in; re-review evidence recorded in the registry.

### A1. Any-assistant access

**Goal:** remove name lists from the trust decision, cut the number of commands a model must remember, and give chat-only models a safe path.

**Tasks:**
1. **Capability-based authority** (fixes F-02). Grant `read_write` only when all hold: workspace verified; runtime reported `write_files`; the runtime name is registered as trusted for this workspace by the user (a one-time `trust-runtime NAME` step during setup or later, recorded through the writer); and a mechanical self-test passes (startup writes and reads back a probe through the writer). Unknown names stay read-only until trusted. Keep vendor profiles only for choosing the instruction file. Plan the migration for existing workspaces with the R1 runner, and keep every M5 regression green.
2. **Single entry point** `aham.py` at the repository root with plain verbs, for example: `setup`, `check`, `start`, `save`, `wrap-up`, `resume`, `connect`, `trust-runtime`, `skills ...`, `memory ...`, `backup`, `restore`. It wraps the existing scripts; they stay for compatibility and tests. Printed recovery commands use the running interpreter (`sys.executable`) rather than a hard-coded `python3` (R5 finding F2).
3. **Shorter instructions.** Rewrite the bridge text and `START_HERE.md` assistant steps around `aham.py`. Add a documentation test with a byte budget for the bridge plus startup output (Phase 6 context item).
4. **Chat-only paste mode** (fixes part of F-08). `aham.py context --for-chat` prints a bounded packet plus a wrap-up template. The user pastes it into any chat model; the model returns a wrap-up block; the user saves it to a file; `aham.py import-wrapup FILE` validates it through the existing canonical wrap-up path under a user-held session. Chat models never write directly. Malformed input causes zero mutation.
5. **Docs:** "Using Aham with a tool that is not listed" and "Using Aham with a chat website".

**Acceptance gate:** an unlisted runtime name becomes writable only after trust plus self-test; trust can be revoked; degraded mode stays read-only; paste-mode round trip passes; malformed paste is rejected with zero mutation; instruction byte budget test passes.

### R7. Nontechnical usability (existing, expanded)

**Goal:** a person who knows nothing about Git or Python succeeds, and every message tells them what to do next.

**Tasks:**
1. `START_HERE.md` Step 0 (R5 F13): detect OS, Python version in the supported range, and command capability; stop on unsupported platforms; never simulate setup.
2. No framework repairs during setup (R5 F14): stop, report the exact failing command and output, point to `docs/TROUBLESHOOTING.md`.
3. Scripted human hand-off moments: permission windows, reopening the terminal after installing Python, approval before anything needing administrator rights.
4. `docs/BEFORE_YOU_START.md`: per-OS prerequisites, every command verified from the official source.
5. `docs/GET_AN_ASSISTANT.md`: which kinds of assistants can do setup (local agents with file and command tools), with verified install pointers; chat-only users go to paste mode.
6. Default workspace location avoids cloud-synced folders; doctor warns when inside a known sync root, with detection verified per platform (R5 F12).
7. Review every user-facing message from `aham.py`: what happened, what it means, what to do next.
8. README: keep the personal story; add a three-step quick start, "what it does and does not do", supported platforms, and the official repository address (fork safety). Move status and evidence tables to `docs/STATUS.md`, including the generated evidence block, and update `scripts/runtime_evidence.py` and its tests.
9. Move internal notes (`docs/dev/M5_TODO.md`, `docs/dev/M6_TODO.md`, `docs/R5_*`, `docs/dev/CURRENT_WORK_CHECKPOINT.md`, `docs/dev/reviews/`) to `docs/dev/`. Check test path references first.
10. Walkthrough protocol in `docs/dev/WALKTHROUGH_PROTOCOL.md`: two or three testers without Git or Python knowledge, synthetic data only, a fresh machine or VM. Tasks: setup, connect a project, a small task, wrap up, switch to a different assistant or model, recover from an interrupted operation using `aham.py check`. The observer notes where they got stuck; nothing private is recorded. Each stuck point becomes an issue. Record outcomes as evidence.

**Acceptance gate:** the four R7 checklist items, backed by walkthrough evidence.

### W1. Windows support (per D3)

**Tasks:** a Windows cross-process writer lock (`VERIFY` `msvcrt.locking` semantics in the Python docs, or an alternative), junction handling (R5 F4), reserved names and long paths (F11), ACLs for `.aham/` (F7), line endings (F9), `py` launcher wording (F2), and a Windows CI job.

**Acceptance gate:** the Astra F4 independent-process concurrency regression passes on Windows; the portability suite is green on a hosted Windows runner; `docs/PLATFORM_SUPPORT.md` updated with exact scope.

### R8. Publication (existing, expanded)

**Repository content:**
1. `SECURITY.md` (how to report a vulnerability, scope) and `docs/THREAT_MODEL.md` (the five actor classes from the Astra review: model mistakes, malicious project content, compromised third-party code, another local user, and a fully compromised account, which is out of scope).
2. `CONTRIBUTING.md` (the AGENTS.md rules in human terms, test commands, the bubblewrap note), a code of conduct of the maintainer's choice, issue templates (bug, setup help with a "do not paste private Brain content" warning, new skill source proposal), and a PR template with the regression-first checklist.
3. `CHANGELOG.md` and versioning: framework SemVer, separate from workspace schema versions (R1); tagged releases with release notes; a provenance commitment per release (`docs/PROVENANCE.md`).
4. Test ergonomics: bubblewrap-dependent tests skip with an explicit reason when bubblewrap is absent, unless `AHAM_REQUIRE_BWRAP=1` is set; CI sets it, so CI stays as strict as M5 requires. Alternatively, document `tests/run_portability_suite.py` from PR #43 as the contributor default.
5. CI hardening: pin third-party actions to full commit SHAs; least-privilege `permissions:` per job; Dependabot for GitHub Actions only (`VERIFY` configuration format); remove or gate self-hosted runner workflows.

**Maintainer actions** (prepare a checklist; do not perform): branch protection with required checks; secret scanning and push protection; fork pull-request workflow approval; private vulnerability reporting; remove the self-hosted runner; email privacy settings. `VERIFY` every setting name against current GitHub documentation.

**History and privacy:** follow the ordered "Pre-publication checklist" in `docs/dev/R5_REVIEW_FINDINGS.md`. Re-run the all-branch and all-pull-request scan right before publication, then the human review. Pattern scans do not replace human review.

**Claims and release:** reconcile README and `docs/STATUS.md` with the evidence register; run `scripts/release_audit.py` on the final tree; generate `PROVENANCE_COMMITMENT.json` from a fresh offline secret; the maintainer explicitly authorizes the visibility change.

**Acceptance gate:** the five R8 checklist items plus the Phase 8 items in `PROJECT_CHECKLIST.md`.

### E1. Runtime evidence follow-ups

1. Claude live rehearsal using `docs/LIVE_RUNTIME_REHEARSAL.md` (closes F-14).
2. After A1: one live run with an unlisted runtime name through the trust flow, and one paste-mode run with a chat-only model, recorded as a distinct evidence type.
3. Measure the bridge plus startup output size and track the Phase 6 low-context item.

Single runs remain smoke tests.

### Later (after 1.0)

- Local MCP server exposing Aham operations through the same writer and session authority (D7). `VERIFY` the current protocol revision; add conformance tests.
- Read-only HTML report (`aham.py report`) of tasks, facts and checkpoints, generated as a file, no server.
- Encrypted portable export (needs a dependency or an external tool; a decision then).
- Retention and archival tooling; incremental indexing.
- Multi-machine sync with explicit conflict handling.
- Translations of `START_HERE.md`.

---

## 7. Cross-cutting safeguards (apply in every milestone)

1. **Untrusted-content envelope.** Anything from skills, semantic recall, project files or the web that is shown to a model is labeled as data. Lifecycle rules state that such content cannot grant permissions or change Aham rules.
2. **Writer-only mutation.** Every command that changes Brain state goes through the state writer, session authority and a receipt.
3. **No silent network.** Every network action is explicit, announced and skippable; offline use keeps working.
4. **No silent installs or global configuration edits.**
5. **Least privilege for skills.** Active trees are read-only; Aham never runs skill scripts automatically.
6. **Drift detection** at startup and in doctor.
7. **Honest wording** in every message and document.
8. **Privacy.** No private paths in portable files; owner-only permissions; diagnostics never include Brain content by default.
9. **Bounded resources.** Subprocess timeouts, scan size limits, context budgets.
10. **Evidence discipline.** Regression first; preserve failed evidence; never weaken a verifier.

---

## 8. Definition of done for public release

- R5 through R8 and S1, S2, S3, S4, A1 checked in the controlling checklist with evidence; W1 done or Windows clearly marked unsupported per D3.
- Default test suite green on Linux and macOS (and Windows if W1 is done) in CI; contributors without bubblewrap see clear skips, not failures.
- Scanner v2 fixture corpus green; Superpowers false-positive result recorded.
- At least one live run each for Claude, Gemini, Codex and a local model, plus one unlisted-runtime run and one paste-mode run, all in the evidence register.
- Nontechnical walkthroughs completed per protocol, with issues closed or explicitly accepted.
- Privacy scan and human review complete for every branch and pull request that will become public.
- README claims match the evidence register; provenance commitment generated; maintainer authorization recorded.

---

## 9. External facts used in this plan

| Fact | Source | Checked | Status |
| --- | --- | --- | --- |
| Agent Skills: a skill is a folder with `SKILL.md` (YAML frontmatter plus Markdown); required `name` and `description`; optional `license`, `compatibility`, `metadata`, `allowed-tools` (experimental); progressive disclosure; reference validator `skills-ref` | agentskills.io, Specification page | 2026-10-01 | Verified; re-check before S1 and S2 |
| Agent Skills is supported by many clients, including Claude Code, Codex, Gemini CLI, OpenCode, Cursor, VS Code, GitHub Copilot and Goose | agentskills.io home page client list | 2026-10-01 | Verified as listed; native skill locations still `VERIFY` per client |
| MemPalace is MIT licensed, offers an MCP server and CLI commands including `search`, `wake-up` and `mine`, and documents install via `uv tool install`, `pipx`, Docker and `npx skills add` | github.com/MemPalace/mempalace README | 2026-10-01 | Verified from README on the default branch; `VERIFY` at the next reviewed commit |
| A skill security scanner exists at `cisco-ai-defense/skill-scanner` | GitHub search result | 2026-10-01 | Existence only; license and behavior `VERIFY` |
| Standard GitHub-hosted runners are free for public repositories | GitHub Actions billing documentation | Not checked | `VERIFY` before relying on D1 or D2 |

---

## 10. First actions for the executing agent

1. Read section 0 and the files it lists.
2. Ask the maintainer for D1 and D2 (they shape R5 and the release path). Ask the others when their milestone starts.
3. Open the P0 documentation PR.
4. Resume R5 on PR #43 following its handoff and the R5 tasks above.
5. Do not start R6 until R5 is merged and the handoff on `main` is current.

## Owner decisions recorded during A1 (2026-10-01)

- D9: enforce owner-only POSIX workspace permissions at setup and check in doctor.
- D3: implement native Windows support and verify it with Windows CI at W1.

These choices authorize implementation; they are not platform or walkthrough evidence.

## A1 acceptance checkpoint (2026-10-01)

PR #59 merged as `c739ad61a359c1d884b21588fe6c71fd4cb70c39` after exact head
`7fa757496bc293062031d1013223a65cfdd0b689` passed workflow `36909749861`:
372 Linux tests, 337 per portability job on Ubuntu/macOS Python 3.10/3.14 (two
macOS skips per job), and Windows unsupported-write refusal. Twenty-nine A1
regressions cover owner trust/probes/revocation, legacy migration, plain verbs,
compact bridge budget and strict scoped chat import. R7 is next; automated tests
do not substitute for its human walkthrough gates. D9/D3 implementation choices
are explicitly approved, as recorded above.

## R7 documentation relocation note

Internal TODO/checkpoint/review notes now live under `docs/dev/`; navigation
references in this retained plan use their current locations. Historical commits
and PR snapshots predate that relocation and retain the old paths. Generated
runtime status now lives in `docs/STATUS.md` and `PROJECT_CHECKLIST.md`.
