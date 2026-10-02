# Authoritative state writer

Aham Brahmasmi serializes supported Brain mutations through one workspace writer and one monotonic revision stream.

## Authority and revisions

- `scripts/state_store.py` owns cross-process writer coordination and the committed revision ledger.
- Supported wrap-up and standalone checkpoint mutations take the same exclusive workspace lock before examining pending state or choosing a revision.
- External activation uses that lock, session authority and revision ledger too.
  Its receipt covers reviewed content at commit time; startup and doctor separately
  verify current content. Existing semantic-provider configuration is unchanged in
  R6; its migration to a revisioned connection operation belongs to S4.
- `state/store.json` is a reconciled cache of the latest committed revision. It is not the source of truth.
- `state/operations/*.json` is the authoritative immutable commit ledger. Records are numbered by strictly increasing revision and must form a contiguous sequence.
- An operation record is created only after its projected files/checkpoint have been written and verified. Creation of that immutable record is the commit boundary.
- A cached `store.json` that lags the ledger is repaired from the ledger. A cached head that claims a revision newer than the immutable ledger is treated as corruption.
- `--expected-revision N` provides optimistic concurrency control [reject stale state-dependent writes]. A stale expectation fails before that new operation mutates durable user state.

## Pending and recovery semantics

Wrap-up operations use `state/pending_wrap_up.json`; standalone checkpoints use `state/pending_checkpoint.json`.

External activation uses `state/pending_external_activation.json`. R6's v3 journal
binds a unique activation identity, the reviewed manifest entry and the base writer
revision. Before manifest publication, recovery restores the old trees. After the
matching manifest entry exists, recovery verifies content and finishes the immutable
operation record, cached head and session revision. A crash after that record cannot
create a second revision. Unrelated writers refuse while the journal exists. v1/v2
journals are recovered using their original rules, without retrospective ledger claims.

Before the immutable operation record exists, the operation is pending. Its projection writes may already have occurred, but no other supported writer may proceed until that pending operation is recovered or resolved. Recovery replays the projection idempotently [safe to repeat] and then creates the single committed revision.

After the immutable operation record exists, the operation is committed even if a crash prevented the cached head, receipt, or pending-file cleanup from finishing. The next writer reconciles `store.json` from the ledger and recovery finishes the derived files without creating another revision.

## Filesystem durability assumptions

Aham fsyncs [forces buffered data to storage] immutable operation-record files before accepting them as committed. It also synchronizes the containing operation directory and synchronizes directories after state-head, pending-state, receipt, and routed projection updates where the platform/filesystem permits directory fsync.

Current cross-process locking uses POSIX `flock`. On a platform where that primitive is unavailable, the authoritative writer fails closed instead of pretending concurrent mutation is safe. Broader Windows/macOS conformance remains part of the later platform-hardening milestone.

Filesystem and hardware stacks can still have failure modes below the guarantees exposed by the operating system, for example storage devices that falsely acknowledge flushes. Aham's durability guarantee is therefore bounded by the host OS/filesystem honoring successful `fsync` operations.

The supported workspace location is a local filesystem providing hard links,
atomic replacement and POSIX locks. Immutable publication uses `os.link`; a
filesystem refusing hard links cannot commit records. Removable, network and
cloud-synced locations are not certified by the platform matrix. Setup-time
filesystem diagnostics remain a usability follow-up, rather than a claim that
setup currently checks every storage capability.

On macOS Aham uses `os.fsync`, not Apple's stronger `F_FULLFSYNC` command.
Directory synchronization is best effort and may be unavailable. Receipts prove
the committed logical state and read-back verification, not survival of every
physical power loss or storage-cache failure. The CI crash tests terminate
processes; they do not cut power to a disk. Apple's documentation distinguishes
`fsync` from flushing a drive's buffered cache with `F_FULLFSYNC`:
https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html
(verified 2026-10-01).

## Test-only crash injection

The environment variables `AHAM_BRAHMASMI_TEST_MODE=1` and `AHAM_BRAHMASMI_TEST_CRASH_POINT=<name>` activate deterministic process exits used by the regression suite. Production behavior ignores crash-point names unless test mode is explicitly enabled.

The suite covers wrap-up interruption after pending-state creation, projection, commit-record creation, cached-head update, and receipt creation. It also covers standalone-checkpoint interruption after pending-state creation, projection, commit-record creation, and cached-head update.
