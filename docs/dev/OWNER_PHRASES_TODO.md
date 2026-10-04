# Owner phrases anti-drift todo

This file is the working todo for owner-chosen lifecycle phrases: the words an
owner says to request Regular start, Quick start or wrap up. It is a usability
improvement inside the existing lifecycle. It adds no new procedure, permission,
runtime adapter or harness behavior, so it does not resume runtime/harness
expansion. `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` (M1-M6 complete) and
`PROJECT_CHECKLIST.md` remain the controlling documents.

## Problem

The documentation says the assistant runs wrap-up "when the user says wrap up",
and startup has `regular` and `quick` modes, but nothing lets the owner choose
their own words or makes those words portable between assistants. A phrase kept
only in one assistant's private memory is lost when the owner switches tools.

## Design constraints

1. Phrases live in the private workspace through the single writer, as an
   immutable ledger-backed owner choice (same pattern as runtime trust). No
   direct file edits and no new mutable state file.
2. Phrases only name existing procedures. They grant no authority: startup
   still issues sessions, wrap-up still needs session authority, Quick mode
   still needs already-loaded verified context.
3. Phrases are untrusted short data: bounded length and count, restricted
   characters, no phrase shared by two procedures.
4. Defaults (`regular start`, `quick start`, `wrap up`) apply when the owner
   never chose; existing workspaces need no migration.
5. Bridge plus compact startup output stays inside the 12 KiB instruction budget.
6. Assistants read the phrases from the startup report or a read-only command.
   Nothing in the controller listens to chat messages.

## Checklist

- [x] A. Regression-first: tests describing set/list/default/validation/receipt/startup/bridge behavior fail before implementation.
- [x] B. `scripts/owner_phrases.py`: validation, ledger replay, owner-controlled `set`, read-only `list`.
- [x] C. Register `phrase_control` operation kind and its structured receipt.
- [x] D. `aham.py phrases` command routing.
- [x] E. Startup report and compact output include `owner_phrases`; `core/startup.json` lists the field.
- [x] F. Runtime bridge tells assistants to honor the owner's phrases; budget test still passes.
- [x] G. START_HERE setup step asks the owner in plain English; README and LIFECYCLE explain phrases (ASSISTANT_ACCESS needed no change).
- [x] H. CHANGELOG `Unreleased` entry.
- [x] I. Foundation verification passes; full unit suite shows no failures beyond the recorded environment baseline.
- [ ] J. Commit, push the feature branch, open a pull request, CI green before any merge.

## Evidence

- A: before implementation, all 10 initial tests in `tests/test_owner_phrases.py` failed (9 errors, 1 failure).
- Review found that `phrases set`, like `trust-runtime`, replaces the single session record. Setup now asks
  about phrases before `start`; the bridge and LIFECYCLE say to run `start` again after a change; an 11th
  test pins that the superseded session is refused and a fresh start regains authority.
- Older framework copies refuse a Brain holding `phrase_control` records without mutation (unknown kind);
  recorded in CHANGELOG rather than adding a schema migration before any published version.
- I: Foundation verification passed. Full local suite: 425 tests, the same 15 environment failures as the
  baseline below and no new failures. Hosted CI remains the authoritative run.

## Environment baseline (before this change)

Local container runs as root. With bubblewrap installed, the full suite ran 414
tests with 15 failures, all in sandbox rehearsal tests
(`test_astra_m6_live_evidence_emission`, `test_m5_live_rehearsal_isolation`,
`test_m5_rehearsal_sandbox`, `test_runtime_negative_path_rehearsal`,
`test_runtime_switch_handoff_containment`, `test_runtime_switch_recovery`) plus
`test_r7_newcomer_flow.test_setup_permission_refusal_has_no_traceback_or_parent_changes`,
which cannot observe a permission refusal as root. Hosted CI is the authoritative
check for those tests.
