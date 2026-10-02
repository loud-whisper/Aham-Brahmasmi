# S2 test design

D4 is approved: universal file-reading bridge first, native loader copies later.
S1 is merged and its six-job acceptance is recorded. Work on a separate S2 branch.

Start with a hosted Linux failing baseline for these synthetic local contracts:

- Activation materializes a writer-owned, revision-stamped skill index with source,
  pin, tree identity, relative path, enabled state and project overrides.
- Populate the existing `BRAIN.json` optional skill list as a compatibility summary;
  it remains derived metadata rather than granting authority or changing identity.
- Enable/disable and optional project overrides use the immutable ledger, writer
  lock, session authority and receipts. Unknown projects and read-only sessions fail.
- Drifted sources are excluded, even if a cached index still claims they are active.
  Editing the cache cannot inject a skill description or preference.
- Context packets carry only names and one-line descriptions under the existing
  byte budget. Full skill bodies are read on demand; disabled skills are omitted.
- The universal bridge points to the list, requires reading the full SKILL.md and
  preserves user/lifecycle authority. Skills cannot authorize Brain writes or
  execution of their scripts.
- Additional local cases cover manifest claims without a matching committed
  activation, CLI preferences, interrupted cache writes and optional-source failure
  isolation. The long-description fixture uses readable prose; repeated characters
  correctly triggered the S1 encoded-blob rule and were unsuitable as benign input.
- macOS acceptance exposed a temporary-directory parent alias. A local POSIX alias
  regression reproduces it; index paths must use the canonical managed workspace
  root without weakening managed-path containment.

Use benign conforming temporary skill folders and existing project/checkpoint
fixtures. Do not execute fetched skill scripts. Verify the pinned public Superpowers
layout from its public tree; its S1 FAIL remains a block on actual activation.
Run local checks first, then one final hosted portability/Windows boundary matrix.
