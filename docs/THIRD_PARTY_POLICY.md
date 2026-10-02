# Third-party source policy

Aham Brahmasmi should make useful external skills and tools easy to adopt without pretending they belong to this project.

## Default rule

Link to the original upstream project and fetch from a verified source. Do not copy a third-party tree into this public repository unless redistribution is necessary, the license permits it, attribution is complete, and the reason is documented.

## Registry requirement

Every supported external source must be listed in `third_party/registry.json` before it is offered by setup or documentation. `third_party/registry.schema.json` defines the complete machine-readable shape.

Each entry records:

- a stable internal ID and public name;
- what kind of external source it is;
- the original public upstream URL;
- an exact reviewed Git commit;
- the license and a source-specific license URL;
- how Aham Brahmasmi connects to it;
- whether local changes exist;
- the date the source was checked;
- the review status;
- whether it is offered as a default;
- how activation occurs;
- attribution text and notes.

If `local_changes` is true, the registry must also state the original commit, summarize the adaptation, and list the changed paths. A locally adapted copy may not hide or replace the original project's attribution.

## Integration methods

Preferred methods, in order:

1. `link`: point the user to the original project when no automated fetch is needed.
2. `installer`: fetch the exact reviewed upstream commit into the user's private workspace.
3. `adapter`: keep only Aham Brahmasmi-specific integration code here while the original project remains external.

Vendoring [copying another project into this repository] is not part of the initial design.

## Supply chain

An installer source follows this sequence:

```text
registered source
      |
      v
fetch exact reviewed commit
      |
      v
private-workspace quarantine
      |
      v
scanner
      |
      +-- PASS --> activate under external/ and record provenance
      |
      +-- REVIEW --> quarantine until explicit valid per-finding human acceptance
      |
      +-- FAIL --> leave quarantined; do not activate
```

The source must be fetched into `state/quarantine/` first. The fetched Git `HEAD` must exactly match the reviewed commit recorded in the registry.

The default scanner uses bounded offline deterministic rules for structural integrity,
instruction deception, lifecycle tampering, sensitive/network targets, secret-like
prefixes, execution surfaces and skill format. A `PASS` does not prove safety.
Optional advisory review and explicitly invoked registered external adapters can
only raise concern. No external scanner is installed or registered by default.
See [Skill scanner](SKILL_SCANNER.md) for exact contracts and limits.

A source needs `PASS` or valid human acceptance of every REVIEW finding. Raw REVIEW
remains recorded alongside `PASS-WITH-WAIVER`. FAIL and incomplete scans cannot be
waived. Content, rule-pack or finding changes void acceptance. A blocked candidate
leaves the active copy untouched. The registered Superpowers pin currently produces
FAIL and cannot activate; [S1 evidence](S1_SCANNER_EVIDENCE.md) records the findings.

Successful activation records the upstream URL, exact commit, license, attribution, scanner identity, scanner version, verdict, and installation time in the private workspace's `state/installed_sources.json`.

Activation also retains the reviewed report, its canonical SHA-256 digest and the
scanned tree digest. Tree identity includes sorted relative paths, regular-file
SHA-256 and execute bits, directory entries and symlink targets; `.git` is excluded
at every depth. Hard-link aliases, special files and links outside reviewed content
are refused. Identity work is bounded to 20,000 entries, 25 MiB per file and 128 MiB
of file content per tree. A content change after scanning or during publication
refuses activation. A PASS report without a tree identity cannot activate.

Startup and doctor recompute active identity. Legacy unbound entries, altered reports
and changed or unreadable trees are excluded from the usable-source list, with a
review action. Future skill indexing must consume only this verified usable list.
Explicit `--replace` fetches and reviews a fresh candidate, including at the same
commit; it does not silently approve edited active content.

Active content is read-only on POSIX. Its owner can deliberately restore write
permissions, so this prevents accidental edits, not a determined local attacker.
Git metadata is excluded from the freeze and digest. A controller move temporarily
allows owner writes on the tree root and restores its permissions; files stay frozen.

Activation uses the shared writer lock and session authority, with one immutable
`external_activation` operation record and a structured receipt. Active runtime
calls need their exact `--session-id`; read-only sessions cannot activate. Project-bound
sessions cannot use a workspace-wide activation to escape their project scope.
An interrupted manifest publication is completed through the journal and ledger;
earlier interruptions restore the prior tree. Unrelated writers refuse while this
journal remains. The receipt verifies reviewed content at commit time; startup and
doctor check its current identity. Old v1/v2 journals retain their historical recovery
semantics and do not acquire a retrospective receipt.

Fetching a source into `external/` does not automatically grant it model-specific permissions or hooks. Runtime-specific activation is a separate layer.

## Updates

An upstream update is not automatically trusted. A new commit must be reviewed, recorded in the registry, fetched into quarantine, and scanned before it can replace a previously active version.

When replacement is explicitly requested, the existing active copy is moved into `state/replaced_sources/` only after the new copy has passed scanning. This keeps the old copy recoverable during the change.

## Ease of use

Users should not need to discover every dependency manually. The reviewed sources can be listed with:

```text
python3 scripts/external_sources.py list
```

Approved sources marked as defaults can be fetched with:

```text
python3 scripts/external_sources.py install-defaults --workspace <path>
```

A single approved installer source can be fetched with:

```text
python3 scripts/external_sources.py install <source-id> --workspace <path>
```

The installer explains what it fetched, the exact reviewed commit, license, scan result, and where the source was placed.

## Licensing

Aham Brahmasmi's Apache 2.0 license does not replace a third party's license. Each external project keeps its own license and attribution requirements. Any redistribution decision requires a separate review before publication.
