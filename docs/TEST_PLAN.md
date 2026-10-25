# Verification plan

Use Python 3.10 to 3.14 for the core lifecycle; native Windows coverage uses Python 3.14 and local NTFS. Follow the checked-in workflow setup for Linux isolation and platform dependencies.

## Commands

```bash
python3 tests/verify_foundation.py
python3 -m unittest discover -s tests -p 'test_*.py'
python3 tests/run_portability_suite.py
python3 scripts/release_audit.py
```

The complete Linux suite exercises canonical writes, concurrent revisions, interrupted writes, lifecycle records, recovery checkpoints, project containment, Git transport, scoped context, runtime trust, credential redaction, command guards, source pin integrity, quarantine and activation, optional memory and backup/restore. Real external APIs are not substitutes for the controlled fixtures in unit tests.

The portability workflow checks Ubuntu/macOS Python configurations and native Windows core behavior. Linux Bubblewrap isolation is not claimed on macOS or Windows. Native Windows checks cover protected ACLs, long paths, junction refusal and literal command arguments. Report each platform's actual result and skips for the tested commit.

## Evidence and acceptance

Use `scripts/runtime_evidence.py` to validate the versioned register and reconcile generated blocks in `docs/STATUS.md` and `PROJECT_CHECKLIST.md`. Record a live pass only after an independently verified real-runtime rehearsal. Unit tests use synthetic fixtures, including fixed dates and fake commit IDs; those are not release evidence.

For live assistants use `docs/LIVE_RUNTIME_REHEARSAL.md` and `docs/LIVE_REHEARSAL_SAFETY.md`. For real people use `docs/dev/WALKTHROUGH_PROTOCOL.md`; simulated personas do not close human gates. Scope current release claims through `docs/STATUS.md`.

## Privacy and release

Review credentials, private URLs and paths, account metadata, source/license declarations, generated reports and binary assets. Validate offline provenance against the reviewed source tree before a tag. Run an anonymous clean-clone setup and download check after authorized publication.
