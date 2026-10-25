# Evidence semantics

Aham Brahmasmi uses distinct evidence terms so a successful command does not imply more preservation or recovery than was actually proved.

## Local durable persistence

**Committed local durable state** means the accepted operation crossed the immutable local commit boundary in the selected Brain workspace. It does not mean the state was copied to another machine or service.

## Content and artifact verification

**Verified checkpoint data** means the persisted checkpoint was read back and matched the accepted operation record.

**Verified routed workspace content** means the accepted wrap-up items were found again at their recorded durable destinations and the final checkpoint matched the committed operation.

These statements cover only the items and destinations named by the receipt. They do not cover unrelated project files or editor buffers.

## Git-history verification

**Committed Git history verified** is used only when recovery checks a recorded repository identity, branch and commit ancestry against the supplied repository. Recording repository metadata during checkpoint creation is not itself Git-history verification.

Dirty tracked files, untracked files and unsaved editor buffers are outside this guarantee unless a separate mechanism explicitly preserves them.

## Replicated backup

**Replicated backup** means a separate copy was successfully written to another storage location or service and verified there. A local checkpoint or wrap-up never implies replicated backup.

## Runtime instruction compliance

**Runtime instruction compliance** means evidence shows that a particular runtime or harness followed the required lifecycle instructions in the tested session. A successful checkpoint or wrap-up command proves durable state behavior, not that the runtime followed every instruction around it.

## End-to-end recovery

**End-to-end recovery verified** means a separate recovery path was exercised and independently demonstrated that the intended continuation state can be reconstructed. Successfully writing and reading back a checkpoint is not by itself an end-to-end recovery test.

## Receipt rule

Operation receipts must state what was verified, what was excluded, warnings that narrow the guarantee, and any recovery action. A broad word such as `VERIFIED` is always qualified by its scope in human-facing output. Structured receipts expose the same boundary through `verification_scope`, `warnings`, and `recovery_action`.
