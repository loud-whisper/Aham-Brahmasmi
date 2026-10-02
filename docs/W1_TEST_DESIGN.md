# W1 native Windows test design

The maintainer approved native Windows implementation and continuation while real
R7 walkthroughs remain pending. This branch does not mark those human gates done.

## Before implementation

1. Keep POSIX flock and add Windows locking over byte zero of the same persistent
   lock file. Seek to zero for both acquisition and release. Never truncate or
   delete the shared lock. Retry contention only, with a finite timeout; reject
   missing backends before mutation. Python documents that byte ranges can extend
   beyond EOF and that LK_LOCK has only ten retries, so use bounded nonblocking
   attempts rather than assuming an indefinitely blocking Windows call.
2. Test contention and release after process exit with independent processes.
   Preserve Astra F4's six independent wrap-ups: six accepted operations, contiguous
   revisions, each fact once. Test unsupported backend refusal on every platform.
3. Refuse Windows junction/reparse components and reserved/ambiguous names before
   managed writes. Portable export/restore must reject Windows-invalid names on
   every host, before destination mutation. Test spaces and Unicode positively.
4. Exercise setup, owner trust, startup, checkpoint, pending-operation recovery,
   wrap-up, resume and backup/restore using the real hosted Windows filesystem.
   POSIX permission modes do not establish Windows ACL privacy. Create protected
   Windows ACLs before writing workspace, bridge or backup data and verify them
   through native security APIs. Allow only the current user, SYSTEM and local
   administrators; ordinary other users remain excluded. Existing unsafe folders
   are refused without rewriting their ACLs. Administrators and same-user processes
   are not sandboxed. Test a deliberately broadened ACL and paths beyond 260 chars.
5. Run local regressions, Foundation and the full stable Linux suite first. Save
   design/red and green implementation commits remotely with CI skipped. Then
   use one ready PR matrix replacing the Windows refusal-only job with the core
   portability suite. Retain platform-specific exclusions with explicit reasons;
   no Linux sandbox or physical power-loss claim follows from Windows results.

## Verified primary references

- [Python msvcrt locking](https://docs.python.org/3/library/msvcrt.html): file-position
  byte ranges, nonblocking modes, and bounded built-in retries.
- [Microsoft file naming](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file):
  reserved devices, forbidden characters, alternate streams and trailing dots/spaces.
- [Python pathlib](https://docs.python.org/3/library/pathlib.html): Windows junctions;
  the 3.10 minimum requires a compatible lstat reparse check.
- [Microsoft CreateDirectoryW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createdirectoryw),
  [security descriptor conversion](https://learn.microsoft.com/en-us/windows/win32/api/sddl/nf-sddl-convertstringsecuritydescriptortosecuritydescriptorw),
  [GetNamedSecurityInfoW](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-getnamedsecurityinfow),
  [GetTokenInformation](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-gettokeninformation)
  and [GetAce](https://learn.microsoft.com/en-us/windows/win32/api/securitybaseapi/nf-securitybaseapi-getace):
  native protected-folder creation and read-only access checks. No shell tool or
  ACL-changing command is used by the production implementation.

Checked 2026-10-01. Local backend doubles cannot prove native Windows locking;
native acceptance remains pending until the exact hosted head is green.

## Local regression progress

The first six tests reproduced fifteen failing assertions for unsupported Windows
preflight, lock selection, reserved names and reparse containment. Expanded failing
cases exposed bridge/source reparse aliases, managed stream/device names and
POSIX-only script execution. Missing PowerShell formatting was reproduced before
implementation. Twelve W1 tests now pass locally with two native-only skips.
Provider fixtures use literal argv through the current Python interpreter rather
than batch/shell wrappers; no third-party installation is needed. Existing Astra
F4, backup/restore, R6 retrieval, S4 and R7 targeted suites pass.

Initial hosted matrix `36933452297` passed Linux (402), Ubuntu (367 each) and
Windows Astra F4/recovery (six tests). Both macOS jobs and Windows core exposed
unresolved-path fixture matching; a local TMPDIR ancestor alias reproduced the
same two assertions before correction. Windows also exposed trailing-dot removal
during native absolute-path normalization. A local injected normalizer reproduced
it before lexical validation moved ahead of normalization. Windows ran 367 tests
with three failures and nine explicit skips; its native junction and PowerShell
execution tests passed. No blind hosted rerun was used.

ACL coverage was then completed before consolidated acceptance: the pure policy
rejects foreign grants/ownership, inherited ACLs and absent owner full access. Native
checks cover workspace/bridge/backup/restore, drift diagnosis and long local paths.
The corrected matrix must pass before support is claimed. No personal SIDs are
recorded in the public evidence or framework ledger.

Corrected head `38c76df5cb02dbe8f23dfba999ef52b0697ecf53`, run `36935402196`,
passed Linux (407), both Ubuntu and macOS jobs (372 each), and Windows Astra
concurrency/recovery (six). Windows core ran 372 tests with four failures and nine
skips. Native ACL creation/drift, long paths, junction refusal and PowerShell passed.
Two older bridge fixtures created inherited, unprotected folders; they must create
private folders to reach their intended ignore/unmanaged-file assertions. The R7
simulated-platform fixture also depended on its host's OS name; a local injected
native OS reproduced that assertion before explicitly isolating the simulated
backend. No production access gate is relaxed. The scanner's 10,000-file case took
31.75 seconds on hosted NTFS, exceeding its POSIX-oriented 30-second ceiling.
Its Windows test ceiling is now 60 seconds; the 10,000-file and byte safety limits
are unchanged. This is test timing tolerance, not a scan safety exemption.

The next consolidated acceptance binds the saved corrected head. The workflow has
no Windows-only dispatch, so it will run the existing six jobs once after local
verification. Failed runs are retained; do not rerun an unchanged failed head.

## Final acceptance

PR #64 merged as 3a5f139a3ac730ee5a19b6b51faa7a95d16ece0d. Exact head 1027f70c9c9d62f8edcb849c338feac20eea15c8 passed all six jobs in workflow 36936673766: 407 Linux tests (four skips), 372 per Ubuntu/macOS portability job (four Ubuntu/six macOS skips), and 372 native Windows core tests (nine skips) plus six independent-process concurrency/recovery tests. Windows Python 3.14.7 on the hosted local filesystem passed protected ACL creation/drift, long paths, junction refusal and literal PowerShell execution. The matrix used 997 summed runner seconds, or 20 minutes rounding each job up; these are measured runner times, not billing usage.

Stable local save `1cfe513` passed Foundation and 407 tests in 100.232 seconds
with five skips. Acceptance commit has the identical file tree. Three hosted
matrices were used after local reproduction/correction; none was an unchanged
blind rerun. Native-only checks passed; POSIX backend doubles are not native proof.
