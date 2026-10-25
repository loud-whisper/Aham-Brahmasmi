# Reviewing an external source

Use this checklist for each new registry source or commit change. Registry
approval records maintainer provenance review; it does not accept scanner findings
on behalf of a workspace owner.

- [ ] Record the public upstream, exact commit, review date and reviewer.
- [ ] Read the license and attribution at that commit. Check compatibility with
  the intended use; retain notices. Do not infer a license from a repository name.
- [ ] Check recent maintenance, unresolved compatibility issues and the commands
  or file layout Aham relies on. Link the evidence and distinguish observations
  from guarantees of future support.
- [ ] Read the complete change from the prior reviewed commit, including scripts,
  hidden files, dependencies, hooks and permissions. Explain local adaptations
  and record their base commit and changed paths.
- [ ] Fetch into quarantine and retain the deterministic scanner report, content
  digest, rule-pack version and verdict. Compare findings with the previous scan.
  A report difference requires investigation; an expected verdict is evidence,
  never permission to bypass the scanner.
- [ ] Resolve FAIL through reviewed source changes or tested scanner corrections.
  FAIL and incomplete scans cannot be waived. Leave unresolved sources blocked.
- [ ] Inspect each REVIEW finding. A workspace owner can explicitly accept only
  the exact bound finding through `skills_review.py`; a generic collection
  approval cannot stand in for finding acceptance.
- [ ] Keep hooks and bundled scripts inactive. Any execution needs its own
  authorization; fetching and indexing do not enable hooks or native loaders.
- [ ] Update `THIRD_PARTY_NOTICES.md`, registry provenance and retained review
  evidence. Record `expected_scan` with the raw `verdict`, `tree_digest`,
  `rule_pack_version` and `reviewed_at` date. Any difference adds a REVIEW concern;
  it never replaces the current scanner findings or lowers FAIL.
- [ ] Test with a synthetic local repository: unchanged pin, reviewed update,
  rejected candidate preserving active content, rollback and recovery. Run the
  hosted framework gate once after local checks pass.

Default-set criteria: clear compatible license, active maintenance, PASS or only
waivable REVIEW findings, usefulness to newcomers, and no required account or
network service. D8 selects Superpowers review first and defers more defaults.

Upstream branch heads are informational and unreviewed. A differing head does not
prove chronological order or authorize installation. Scheduled polling is
deferred; explicit checks avoid recurring Actions use.
