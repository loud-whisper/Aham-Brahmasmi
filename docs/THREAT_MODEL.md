# Threat model

## Assets and trust boundaries

The private Brain contains personal records, projects, operation receipts and
recovery state. The public framework must not contain those records. Project
repositories and downloaded sources are separate from the private workspace.
The controller and committed writer ledger determine authority and durable state;
model prose, caches, recall and profile names do not.

The owner decides which runtime may write and which optional tools may run. Owner
confirmation records intent; it is not authenticated human identity. An assistant
with the same filesystem permissions can bypass application checks by writing
files directly. Use a separately configured OS sandbox when that threat matters.

| Actor | Concern | Framework controls | Remaining boundary |
| --- | --- | --- | --- |
| Model mistakes | False completion, stale session, conflicting retry, lost work | Exact sessions/revisions, writer receipts, checkpoint/recovery, explicit verification | Unsaved model actions are not preserved; a receipt proves the recorded operation only |
| Malicious project content | Prompt injection, path redirection, forged authority | Data envelopes, scoped import, managed containment, bridge identity checks | A model can still disobey; these are application checks, not an OS sandbox |
| Compromised third-party source/tool | Malicious instructions, script execution, source drift or global recall leakage | Pinned provenance, quarantine, bounded deterministic scanner, exact review acceptance, drift checks, scoped recall | PASS cannot prove safety; explicitly approved external executables run with their process permissions |
| Another ordinary local user | Reading or modifying private files | POSIX owner-only roots/files; native Windows protected roots for current user, SYSTEM and Administrators; read-only doctor diagnostics | Access depends on the OS/filesystem; exports and sync copies need their own private storage; same-user processes and administrators are not isolated |
| Fully compromised owner account | Attacker controls interpreter, controller, files or credentials | None sufficient | Out of scope; recover through trusted system/account restoration and verified backups |

## Durable and portable state

Native locks serialize participating writers. Immutable operation records and
replay rules cover tested process interruption boundaries. CI does not prove
physical power-loss durability, every filesystem, or adversarial kernel behavior.
Unkeyed export hashes detect corruption relative to a manifest; they do not
authenticate a bundle against someone who can replace both manifest and content.
Provenance commitment binds a reviewed tree to a private secret under its stated
protocol; it is not proof of ownership of an abstract idea.

## Optional integrations

No memory provider, Git host, skill loader or cloud is required for core operation.
Recall is unverified data unless matched to exact authenticated committed records;
even then it cannot grant tools or writer authority. Indexing is opt-in and
provider-reported progress is not independent proof of durable remote ingestion.
No skill scripts, hooks or model advisory reviews execute by default. Deterministic
FAIL or incomplete scans cannot be waived by a human/advisory response.

## Privacy and disclosure

Diagnostics should use metadata and synthetic reproductions. Do not paste private
Brain records into public issues or PRs. Pattern scans do not replace human review
of the current tree, all branches, PR history, artifacts and publication claims.
See `SECURITY.md` and `docs/MAINTAINER_PUBLICATION_CHECKLIST.md`.
