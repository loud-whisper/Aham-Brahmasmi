# Skill lifecycle

These portable commands work in a verified private workspace. Final entry-point
names will be supplied by A1. Use `--session-id` when a runtime session is active.
Mutation requires its write authority; a read-only runtime cannot fetch, copy,
activate, roll back or remove sources through these commands.

```sh
python3 scripts/skills_lifecycle.py check-updates --workspace /path/to/workspace
python3 scripts/skills_lifecycle.py check-upstream --workspace /path/to/workspace
python3 scripts/skills_lifecycle.py update superpowers --workspace /path/to/workspace
python3 scripts/skills_lifecycle.py rollback superpowers --workspace /path/to/workspace
python3 scripts/skills_lifecycle.py remove superpowers --workspace /path/to/workspace
python3 scripts/skills_lifecycle.py add-local /path/to/my-skill --workspace /path/to/workspace
```

`check-updates` is offline and compares installed refs with reviewed registry refs.
`check-upstream` announces its network access, reads upstream HEAD and reports
unreviewed differences. A different ref does not establish chronological order.
Neither check installs anything. Startup and doctor show active skill and reviewed
update counts; unreadable optional metadata does not grant authority.

## Review and update

Updates fetch the exact reviewed commit into quarantine. Output contains the full
scanner report and `new_findings` compared with the active copy. A rejected
candidate leaves active content unchanged. Registry `expected_scan` metadata
records the maintainer's scan; a content, rule-pack or verdict mismatch raises a
new REVIEW concern. It cannot make a current FAIL acceptable.

For REVIEW, inspect each finding and explicitly confirm its exact identity using
[the scanner review procedure](SKILL_SCANNER.md). No controller automatically
accepts findings. FAIL and incomplete scans cannot be waived. Advisory and external
scanner concerns stay in the retained report during reviewed activation.

Once every current REVIEW finding has been explicitly accepted:

```sh
python3 scripts/skills_lifecycle.py activate-reviewed superpowers \
  --quarantine /path/to/workspace/state/quarantine/candidate \
  --workspace /path/to/workspace --replace
```

This also handles retained local and rollback candidates. Changes to content or
rules require a fresh scan. A different active installation invalidates a prepared
update/rollback candidate; review the current copy again.

Superpowers is offered for fetching at its exact public pin. Its retained scan is
REVIEW, with no accepted findings; it is not activated by framework setup. D8
selects reviewing Superpowers first and defers additional default collections.
Native-loader copies and automatic hooks remain deferred under D4.

## Rollback and removal

Successful replacements retain the prior tree in `state/replaced_sources/`.
Rollback selects the latest committed archive, verifies its content digest and
immutable provenance binding, copies it into quarantine, and scans it under the
current rules before activation. Changed or unbound archives are refused. A failed
update does not displace the previous archive. Older archives without the new
immutable path binding are not inferred to be valid rollback candidates.

Removal deactivates the source, refreshes the index and returns the archive path
and a ledger receipt. It **does not delete files**. This milestone provides no
deletion command. Archived content may remain sensitive and is local to the
workspace. Portable backups retain ledger history but exclude third-party trees;
an archive must actually be present and verified before rollback can work.

Rollback and removal use the shared writer lock and durable lifecycle journal.
After an interruption, run:

```sh
python3 scripts/external_sources.py recover --workspace /path/to/workspace
```

Recovery restores the prior state before manifest publication or finishes the
committed operation afterward. Receipts describe the recorded operation; they do
not establish current archive integrity, runtime compliance or physical power-loss
durability.

## Your local skill

`add-local` takes a folder containing `SKILL.md`. Its name must match that folder.
It copies the folder into quarantine and scans the copy; changes to the original
cannot alter the installed tree. Unsafe aliases and special entries are refused.
Local IDs start with `local-`; use `--source-id local-example` to set a stable ID.
Replacing an installed local skill requires `--replace`.

Provenance is `local_digest`: a content digest, no upstream URL and no asserted
third-party license. Local skills never enter the public registry. Scripts still
need separate approval before execution. REVIEW uses the same exact finding
confirmation and `activate-reviewed` path as external sources.

Maintainer process: [SOURCE_REVIEW.md](SOURCE_REVIEW.md). Scheduled upstream polling
is deferred to conserve Actions allowance; explicit checks are available.
