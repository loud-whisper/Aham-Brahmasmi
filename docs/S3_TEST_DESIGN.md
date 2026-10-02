# S3 test design

## Checkpoint 1: Superpowers context review

D8: review Superpowers first; defer additional default collections. Its full
collection remains blocked while findings require review. No finding is accepted
by this checkpoint, and no source is activated.

Public source reviewed: `obra/superpowers` at
`b36e0829c6d0140e93cfef2ca599b1b07d4a7797`.

- `tests/brainstorm-server/windows-lifecycle.test.sh`, lines 240 and 304:
  past-tense failure messages about a test server's own state.
- `skills/brainstorming/scripts/start-server.sh`, line 119: full-line shell
  comments describing a browser reconnect cookie, with unrelated reads elsewhere.
- JavaScript environment-property access is distinct from a `.env` file path.

Regressions use inert synthetic strings. Establish local failures first, then
preserve actual direct writes, dotenv paths, indirect credential reads, inline
comments, targets spanning executable lines and hidden instruction overrides.
Full-line shell comments retain REVIEW; they never grant execution permission.
No automatic waiver, scanner installation or default-source expansion.

CI budget: save the red test checkpoint with `[skip ci]`. Run the targeted tests
locally, then the full suite at a stable commit. Publish one ready PR for the
Linux/macOS/Windows framework gate after local verification. Do not run hosted
red tests or a second draft gate for this bounded correction.

## Remaining lifecycle gate

Test offline installed-versus-reviewed refs without network; announced upstream
checks without activation; successful updates and failed updates preserving the
active copy; rollback with archive identity verification and fresh-process crash
recovery; archive-preserving removal; local skill copying with digest-only
provenance; authority refusal; manifest/index consistency; startup and doctor
summaries. Use synthetic local Git repositories for lifecycle integration.

S3 remains unchecked until these commands and the maintainer review workflow
pass their acceptance gates. Scheduled upstream checks are deferred to conserve
Actions allowance.

## Checkpoint 2: lifecycle commands

Saved local red checkpoint `bea559f`: 11 tests fail against the absent lifecycle
module/CLI. Expanded regressions use synthetic local repositories and temporary
workspaces. No malicious strings or fetched upstream scripts are executed.

The implementation gate covers:

- Offline reviewed-ref comparisons and announced `ls-remote` checks that never
  change the manifest or ledger.
- Successful update, rejected update preserving active content/quarantine, then
  verified rollback with a controller receipt.
- Changed archive refusal, immutable replacement/archive binding and dotted IDs.
- Corrupt historical deactivation payload refusal, including after reinstallation.
- Concurrent updates refusing stale candidate publication.
- Removal preserving content, removing manifest/index rows and recording a receipt.
- Local copied content, digest-only provenance, unchanged public registry, blocked
  malicious local content and exact synthetic finding confirmation.
- Refusal from a read-only runtime before network fetch or local copying.
- Expected scan mismatch raising REVIEW without masking FAIL; malformed registry
  metadata rejection.
- Retained advisory concerns surviving reviewed activation.
- Fresh-process rollback at all five activation journal boundaries and removal at
  all four deactivation boundaries, with exact ledger counts and pending cleanup.
- Fresh startup/doctor skill counts.

Run targeted tests locally, commit a stable implementation, then run Foundation
and the full local suite. Save with CI skipped until the acceptance candidate is
ready. Use one ready PR matrix for the lifecycle checkpoint, then merge only after
all required jobs pass. Archive data and immutable ledger identity must agree;
cache or metadata edits never stand in for reviewed content.

The initial stable 313-test run passed. A subsequent archive-integrity regression
then reproduced one missing historical-deactivation payload check (20 lifecycle
tests, exactly one failure). This local red led to a payload digest recheck before
archive selection. The final stable suite includes that regression; no hosted
minutes were used for the failure.
