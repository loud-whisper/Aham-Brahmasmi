# S1 test design preparation

R6 is merged. D5 is approved: include opt-in advisory review that can only raise
concern. D6 is approved too: optional user-installed external-scanner support with
explicit invocation. No third-party scanner is installed or registered by default.

## Corpus contracts

Use inert text in synthetic directories, never execute a malicious fixture. Each
fixture has an expected PASS, REVIEW or FAIL, and expected rule IDs. A FAIL-category
fixture must not receive PASS. Retain the failing baseline in a draft PR before
implementation. Basic scanner behavior and supply-chain/crash tests remain gates.

- Benign conforming skill and ordinary prose: PASS; informative notes allowed.
- Bidi/tag controls in instruction files: FAIL. Zero-width deception: REVIEW.
- Long comments, oversized single lines and encoded instruction blobs: REVIEW.
- Instruction override alone: REVIEW; override plus sensitive/network target: FAIL.
- Direct Brain state writes, forged verification markers, skipped checkpoints or
  framework-script edits: FAIL. Preserve quotation/context false-positive evidence.
- Sensitive target prose: REVIEW; script reading the same target: FAIL.
- Download-and-execute: FAIL. Upload/webhook/raw-IP/tunnel patterns: REVIEW.
- Executable/shebang/binary and verified lifecycle/hook configuration: REVIEW.
- Invalid Agent Skills frontmatter, broad allowed-tools: REVIEW. Long SKILL.md: INFO.
- Description/body mismatch: conservative advisory findings with explained limits.
- Private keys and issuer-verified token formats: FAIL, synthetic nonfunctional data.

Every finding has stable rule ID, severity, path, line, bounded escaped excerpt,
plain-language explanation and remediation. CLI output must not reintroduce controls.
Report retains scanner/version/verdict/findings/scanned_at plus tree/rule-pack digests.

## State and update checks

Waivers require explicit per-finding human reason and bind source ID, reviewed tree,
rule ID and file digest. They cannot waive FAIL. Change a file or rule version and
prove the prior waiver becomes unusable. Use writer/session authority and receipts;
read-only sessions cannot accept findings. Failed/review-unaccepted candidates leave
the current active tree and ledger intact. Diff-aware replacement lists new findings
against the retained accepted report without suppressing the full scan.

## Bounds and evidence

Measure a 10,000-file synthetic tree with a stated runtime ceiling; enforce bounded
reads before rule evaluation. Use exact pinned Superpowers public content for the
network-gated false-positive rehearsal. Review each finding and record disposition;
do not weaken rules merely to get a PASS. Public sources must verify every issuer
token format and tool-specific filename before adding it to the rule pack.

Agent Skills specification verified live at https://agentskills.io/specification
on 2026-10-01: required YAML frontmatter name/description; name 1-64 lowercase ASCII
letters/digits/hyphens, parent-name match, no consecutive or edge hyphens; description
1-1024; compatibility 1-500 if supplied; experimental allowed-tools; under-500-line
SKILL.md guidance. Parsing without dependencies must refuse unsupported YAML features
for automatic acceptance and give a concrete review reason.
