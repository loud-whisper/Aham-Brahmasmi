# Skill scanner

The scanner works offline with Python's standard library. It treats fetched skill
text as data. Scanning does not execute scripts, enable hooks or install packages.
Scanner schema version 3 retains the original contract; “scanner v2” in the release
plan names the S1 milestone, rather than the schema number.

## Verdicts and findings

Any FAIL finding produces FAIL. Any REVIEW finding produces REVIEW. INFO findings
alone produce PASS with notes. Each finding names the rule, file and line, gives a
bounded escaped excerpt, explains the concern and suggests a next step. Possible
secret excerpts are redacted. Structural findings use line 0 when no text location
exists. Tree SHA-256 binds the complete reviewed content, excluding Git metadata;
the rule-pack digest binds the bundled rules and deterministic scanner code.

The scanner checks hidden Unicode, instruction overrides, Aham lifecycle tampering,
sensitive targets, download/execute and other network surfaces, secret-like token
prefixes, executable files, binaries, package lifecycle commands, Git-hook settings,
Claude hooks, VS Code automatic tasks and MCP configuration. Agent Skills name,
description, compatibility and permission requests are checked too. Frontmatter
supports scalar YAML fields and multiline strings; unsupported YAML requires review.
The rule pack links the primary sources used to verify formats and filenames.
Token checks use issuer prefixes and heuristic body lengths, rather than authenticating
tokens or claiming to implement every current issuer format.

This is bounded heuristic detection. Novel phrasing, other languages, ordinary-looking
instructions and indirect code behavior can escape it. A PASS is not proof of safety.
The R6 recall envelope and S2 runtime bridge rules still matter. Broad patterns can
also flag harmless examples, comments and application state. The pinned Superpowers
result is recorded in [S1 scanner evidence](S1_SCANNER_EVIDENCE.md).

Text review reads at most 2 MiB per file and emits at most 2,001 deterministic
findings, including an incomplete-review marker. Existing identity limits cap the
tree at 20,000 entries, 25 MiB per file and 128 MiB total. More than 10,000 files
requires review. Incomplete scans cannot be waived for activation.

## Scan and accept

```sh
python3 scripts/scan_external.py /path/to/quarantine/source --json-out /path/to/report.json
```

Exit status is 0 for PASS, 2 for REVIEW and 1 for FAIL or a scanner error. Updates
retain the full scan and list new findings against the previous accepted report.
An unaccepted candidate leaves the existing active copy intact.

Only the human may explicitly accept a REVIEW finding after reading its content
and explanation. An agent must present the specific finding and reason and obtain
that decision before invoking acceptance. FAIL cannot be accepted. The command's
confirmation argument records a decision; it does not authenticate a person's identity.

```sh
python3 scripts/skills_review.py --workspace /path/to/workspace --source SOURCE_ID \
  --tree /path/to/quarantine/source --report /path/to/report.json \
  --finding FINDING_ID --reason "Human's specific reason" --human-approval FINDING_ID
python3 scripts/external_sources.py activate-reviewed SOURCE_ID \
  --workspace /path/to/workspace --quarantine /path/to/quarantine
```

Use `--session-id` when the current runtime session requires it, and `--replace`
only for an intended replacement. Acceptance uses the shared writer lock, session
authority, immutable operation ledger and structured receipt. It binds source ID,
whole-tree digest, rule pack, rule, file digest and exact finding content. Changes
invalidate it. Raw REVIEW is retained alongside `PASS-WITH-WAIVER`; the receipt
records historical acceptance rather than proving current content or safety.

## Optional advisory review

D5 is opt-in. No hosted model is called automatically. Preparing a packet does not
send it anywhere. The user chooses whether to provide it to a local or hosted model.

```sh
python3 scripts/scan_external.py /path/to/source --advisory-packet-out packet.json
python3 scripts/scan_external.py /path/to/source \
  --advisory-packet packet.json --advisory-response response.json
```

The packet contains escaped SKILL.md text, a fixed rubric, content/report digests
and a random canary. The response must contain exactly `format`
(`aham-skill-advisory-response`), `version` (1), `packet_digest`, `canary`, `verdict`
(PASS or REVIEW) and a nonempty `reason` of at most 2,000 characters. Unknown fields,
changed content or mismatched digests/canaries are refused. REVIEW adds concern;
advisory PASS cannot lower deterministic REVIEW or FAIL. The canary checks the
response contract; it does not prove that a model resisted manipulation.

## Optional external adapters

D6 is opt-in. No external scanner is bundled, registered or installed by default.
The normal third-party review must establish the public upstream, exact commit,
license and supported interface before adding an approved tool/adapter entry.
`scanner_adapter` declares `protocol: aham-json-v1`, exact executable version,
executable basename and version arguments. This is Aham's protocol; it does not
claim that a named third-party scanner already implements it.

```sh
python3 scripts/scan_external.py /path/to/source \
  --registry /path/to/reviewed-registry.json --external-scanner SCANNER_SOURCE_ID
```

The user-installed adapter receives `--tree ABSOLUTE_PATH`. It must emit exactly
`format: aham-external-scan`, `version: 1`, `tree_digest`, `verdict` (PASS, REVIEW or
FAIL) and `findings` (up to 200 objects with only `severity` and `message`). Finding
severity is REVIEW or FAIL. Version output must exactly match the registry string.
No shell is used; execution has a temporary working directory, a reduced environment,
a time limit and a 128 KiB output cap. These controls are not an execution sandbox
or an offline guarantee for the chosen tool. Missing tools, errors, bad output,
timeouts or changed trees add REVIEW and cannot lower FAIL. Combined verdict is
the most severe. Scanner failures must be resolved, rather than waived.
