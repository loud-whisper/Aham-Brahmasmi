# S4 scoped recall and connection test design

D10 is approved: include offline keyword recall over committed records alongside
the optional MemPalace adapter. No provider installation is authorized by source
review or framework testing.

## Public source review

Reviewed update `MemPalace/mempalace` commit
`f8b9ed1507888cab47c7c7e1d90755f89e0353c4` (2026-09-18) follows the prior pin directly.
The complete one-commit delta is reviewed. The 2026-09-29 branch head was inspected
but has a substantially larger delta and is not the retained reviewed pin.
Latest published release is v3.10.0 from 2026-09-16; neither source pin asserts
package identity. License remains MIT, copyright 2026 MemPalace Contributors.
Whole-tree scans remain FAIL; independently installed CLI interface approval
does not authorize source activation or findings acceptance.

Reviewed primary files: `README.md`, `LICENSE`, `mempalace/cli/parser.py`,
`mempalace/cli/cmd_query.py`, `mempalace/cli/cmd_mine.py`, `mempalace/miner.py`.

- `--version`, `status`, `search QUERY --wing WING --results N` and `wake-up`
  remain. Scoped wake-up continues using filtered search; native wake-up includes
  global L0 identity.
- Ingest is `mine DIRECTORY --mode projects --wing WING`. Verify synchronous
  routing via `--direct`, verified in `mempalace/cli_write_routing.py`. Do not use
  `--background` or start a daemon. Existing provider hub forwarding can still
  prevent the expected synchronous summary; such output cannot advance index lag.
- Miner identity uses `str(filepath)`, an absolute source path. Modified files
  purge prior drawers by that path before reinsertion; random staging roots can
  duplicate records. Use stable corpus and record-file paths, with transient bytes.
- Mine can exit successfully after individual skips. Check processed/skipped
  counts before recording a successful index command revision. A command summary
  is provider-reported evidence, not proof of complete or durable provider storage.
- Upstream documents uv, pipx and Docker installs; `npx skills add` installs a
  setup skill, not the CLI itself. Present choices and links; never install silently.
- MCP is upstream's own integration. Its writes cannot write Aham's canonical
  records or bypass Aham session authority.

## Module and authority boundary

Use a small `memory_connection` module for revisioned connection configuration,
stable project-to-wing mappings, opt-in indexing and a canonical recall catalog.
Keep `semantic_memory.py` as the compatible provider CLI facade. Configuration
changes and index progress use the existing shared writer lock, session authority,
immutable operation ledger and receipts. BRAIN's existing optional field is a
derived compatibility view. Legacy configuration remains readable but cannot
silently opt into writes. A crash after ledger commitment must be repairable by
rematerializing configuration without inventing approval.

Build the catalog from verified committed wrap-up bundles and record-lifecycle
replay, never cached Markdown or provider claims. Reuse R3 scope rules: ambiguous
multi-project facts/tasks and unbound assertions stay unscoped. Superseding facts
inherit their parent's scope. Lessons need an unambiguous project binding; project
updates use their explicit project identity. Include current statuses so recall
cannot reactivate superseded/retracted facts or completed/cancelled tasks.

Provider text stays escaped untrusted data. Canonical mapping requires an exact
record binding and selected project, checked against current ledger state. A forged
ID or digest, stale status or out-of-scope record cannot assert current authority.
Offline keyword recall uses the same scoped catalog and envelope, without invoking
an external executable. Broad recall requires an explicit all-scopes request.

## Indexing and failure isolation

Export plain files stamped with record ID, project ID, content revision, status and
content binding. Stable staging paths live outside the Git/portable allowlists and
receive explicit exclusion rules. Clean only generated staging files, including
after failure; refuse unsafe aliases and unexpected occupied paths. Export stale
record statuses under the same paths so updates can replace their prior provider
representations. Do not install hooks, launch background miners or index arbitrary
project directories.

Indexing requires explicit opt-in and write authority. Preserve index lag after
timeouts, failed commands, skipped files or malformed summaries. Track content
revision separately from connection/index metadata revisions, avoiding perpetual
lag caused by recording index progress itself. Automatic post-wrap indexing runs
only after a committed wrap-up and cannot turn a successful wrap-up into a failure.

## Regression gate and CI budget

Synthetic temporary workspaces and fake providers cover:

1. Configuration and disable authority; no external process for lite recall.
2. Ledger-owned configuration versus edited BRAIN cache; read-only refusal.
3. Stable/custom project wings, unknown project refusal and isolation.
4. Opt-in refusal before any ingest process or staging write.
5. Stable staged paths across indexes, stamped content and cleanup.
6. Successful command progress versus skip/timeout/error lag preservation.
7. Staging exclusion from Git snapshots and portable backup manifests.
8. Current scoped keyword results, no cross-project leakage and stale-status
   handling after fact supersession/retraction and task completion.
9. Exact canonical binding; forged provider records remain unverified.
10. Escaped instruction-like provider output and scoped wake-up behavior.
11. Post-wrap failure isolation and indexing only committed content.
12. Guided missing-provider detection and verified install/MCP documentation.

Save local red tests with CI skipped. Expand regressions before each discovered
fix. Run Foundation and the full local suite at a stable commit, then one ready PR
Linux/macOS/Windows framework gate. No hosted red or extra draft gate is needed.
Do not mark S4 complete until its tests and registry re-review evidence pass.

## Local checkpoint evidence

Initial saved baseline `9453cbe` failed all 13 new tests because the connection
module did not exist. Expanded integration tests cover cache repair, legacy
opt-in refusal, default-wing collisions, read-only indexing, occupied/aliased
staging, real Git/export exclusion, stale stamps, offline CLI/startup,
post-wrap failure isolation, bounded processes, supersession, a single-ledger
catalog snapshot, forged bundles and ambiguous project items.

Two final regressions reproduced locally before fixes: malformed skip-summary
text advanced progress, and a missing project identity allowed an unbound
connection. Both now refuse. Their red logs are retained locally; no hosted red
workflow was used. The earlier full local checkpoint passed 341 tests with one
expected skip. Final acceptance includes 28 S4 tests plus the full suite and
one ready PR matrix; hosted evidence is recorded after that gate succeeds.

The initial ready matrix `36903749610` passed Linux and Windows refusal but both
macOS jobs failed solely in process-group cleanup after the short provider exited.
The exact initial head was `91b060b967be2e26b2e08eecdedafe1d870ba2d3`.
A local injected-permission regression reproduced both finished-parent and
timeout failures before the fix. Cleanup now tolerates a refused group signal
after parent exit and kills a still-live owned child directly. The final S4 suite
has 29 tests. A second exact-head matrix is required for this concrete portability
fix; no blind retry or live provider-data rehearsal is used.

## Hosted acceptance

S4 merged through PR #57 as `47c32ed8fee5b44cd4743bc6e8e2c1f7042bc4e1`.
Exact tested implementation `d406545418337764e68bd9c4af28337272e978d1`
passed all six jobs in workflow `36904820142`: 343 full Linux tests,
308 per Ubuntu/macOS Python 3.10/3.14 portability job (two skips per macOS job),
and Windows unsupported-write refusal. Local acceptance passed 343 tests with
one expected skip; the S4 module has 29 regressions.

Initial matrix `36903749610` passed Linux/Windows but both macOS jobs exposed
process-group cleanup refusal after provider exit. A local injected-permission
regression reproduced both exited-parent and timeout cases before the fix.
Initial/corrected matrices used 538/535 summed runner seconds, or 11/11 per-job
rounded minutes; these are runner measurements, not billing usage. No hosted red
baseline, draft gate, blind retry or live personal-data ingestion was used.

Configuration and progress use the immutable writer ledger and receipts. Project
wings are unique, indexing requires opt-in/write authority, and optional indexing
cannot invalidate a committed wrap-up. Catalogs use one verified ledger snapshot;
exact current bindings are matched, inactive records are stale, foreign stamps
are omitted and other provider prose remains unverified. D10 is approved: offline
keyword recall is included. Stable staging is excluded from Git/portable exports.
Command progress is provider-reported evidence, not durable ingestion proof.

Public MemPalace link pin is `f8b9ed1507888cab47c7c7e1d90755f89e0353c4`.
Both whole-tree scans remain FAIL, with no finding acceptance or source activation.
Registry approval covers the independently installed CLI interface only. Evidence:
`docs/MEMORY_CONNECTION.md`, `docs/S4_TEST_DESIGN.md`,
`docs/S4_SOURCE_REVIEW_EVIDENCE.md`, and the retained finding inventory.
