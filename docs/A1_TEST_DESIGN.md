# A1 assistant access test design

Base: S4 and its evidence checkpoint merged through PRs #57/#58. Work remains
solo, on a separate branch, with local red/green checkpoints before one ready
platform matrix. The existing scripts remain compatible entry points.

## Authority

Vendor profiles choose instruction-file integration only. A runtime name does
not grant write authority. Trust is an explicit workspace-owner control recorded
in the immutable ledger through the shared writer. An exact runtime confirmation
is required; no trust is inferred from an edited cache, capability report, prior
session, bridge install, provider setup or package installation.

Normal startup grants writes only after workspace verification, explicit
`write_files` reporting, current committed runtime trust, a mechanical writer
write/read/cleanup self-test, and mode/pending-operation checks. Trust changes and
startup share the writer lock. Revocation invalidates existing runtime sessions;
every supported mutation checks trust again. Degraded mode never probes for or
grants writes. Direct workspace setup and explicit owner controls remain local
owner paths; their confirmation records intent, not authenticated human identity.
They must not be invoked by an assistant to grant itself permission.

Trust reads default to empty for existing workspaces. R1 migration continues to
verify/repair the existing schema before trust setup; no historical ledger, Brain
fingerprint or record IDs are rewritten to infer vendor trust. Existing owners
explicitly trust each runtime once and restart it. Tests that need runtime writes
establish this prerequisite explicitly while preserving M5 denial, stale-session,
revision, recovery, project-boundary and isolated-rehearsal assertions.

The writer probe is transient, contains no user record content, is excluded from
Git/portable export, and never constitutes a task/checkpoint completion. Failed
probe or cleanup leaves startup read-only. Mechanical controller writes do not
prove an external model actually has a tool; capability reporting and owner trust
remain distinct from the probe result.

## Entry point and instructions

Root `aham.py` exposes setup, check, start, save, wrap-up, resume, connect,
trust/revoke-runtime, skills, memory, backup/restore and context/import-wrapup.
It delegates through the current interpreter with argument vectors and preserves
underlying exit status and verification receipts. It performs no shell expansion,
automatic package installation, arbitrary source execution or remote push.
Recovery guidance uses the running interpreter. Unlisted runtimes receive the
universal manual bridge; native copies remain deferred under D4.

The portable bridge and normal compact startup report have a combined 12 KiB
instruction budget. Diagnostic JSON remains available separately. Instructions
reference `aham.py`, retain receipt verification, skill full-file reads and user
authority, and contain no generated local private paths.

## Chat paste mode

`context --for-chat` reads a bounded project context packet and prints a strict
wrap-up template. A chat model returns data; it receives no writer authority.
The response binds workspace ID, stable project ID and current base revision.
The user saves the response to a file and imports it under their held session.
Validation uses the existing canonical wrap-up path and scope rules.

Before any writer mutation, reject oversized input, malformed/duplicate JSON,
multiple or incomplete blocks, unknown fields, foreign workspace/project, stale
revision, invalid canonical bundle and unauthorized session. Do not let response
data select filesystem paths, session authority, runtime trust or a provider.
An operation ID makes replay of the same valid response idempotent; different
content under the same ID refuses. Optional recall failure preserves the committed
wrap-up receipt, as established by S4.

## Regression gate

1. Unlisted and listed names without trust stay read-only despite capabilities.
2. Exact owner confirmation commits trust with a receipt; unknown/missing/edited
   trust records cannot grant authority.
3. Trusted unlisted runtime becomes writable only with write reporting and a
   successful writer probe.
4. Probe write/read/cleanup failure, missing capabilities, pending operations and
   degraded mode all refuse writes; degraded mode does not run the probe.
5. Revocation denies new startup and already-issued runtime mutation authority.
6. Owner controls reject unconfirmed intent and unsupported runtime identities
   before ledger or session changes; ordinary read-only callers cannot self-trust.
7. Trust receipts and derived-view recovery preserve canonical ledger identity.
8. Entry-point verbs preserve script exit status, authority, scope and receipts;
   help, missing/invalid arguments and optional-provider setup are concrete.
9. Unknown bridge install uses manual file-reading and remains path-private.
10. Chat round trip commits and verifies a scoped wrap-up; same content replays,
    conflicting content refuses, and optional indexing failure stays isolated.
11. Every malformed/foreign/stale/unauthorized paste case has zero workspace
    mutation, including ledger, session, cache, routed files and pending metadata.
12. Compact instructions meet the combined byte budget and retain authority and
    verification rules. R1 migration and all prior M5/S4 regressions stay green.

Save initial failing tests with CI skipped, implement and expand tests for every
discovered gap, run Foundation and the full suite on a stable commit, then one
ready Linux/macOS/Windows framework gate. D3 is now approved: native Windows support and its lifecycle gate follow at W1.
D9 is approved for owner-only POSIX setup and doctor checks at R7.

## Local implementation review evidence

The initial 15 tests failed locally before implementation. A first full-suite pass
exposed 21 compatibility failures after removal of automatic vendor trust.
Explicit synthetic trust prerequisites preserved all nine M5 authority/recovery
tests; a stable implementation then passed 370 full-suite tests with one expected
skip. Expanded chat regressions failed for project-session forwarding and changed
replay base revision before both fixes. Setup's superseded-session output was also
reproduced before correction. Final coverage adds real Git/export exclusions,
exported trust replay, R1 migration, corrupt trust history, cache repair, probe
cleanup/readback refusal, pending operations and bounded duplicate JSON input.
Hosted acceptance remains required on the final exact head.
