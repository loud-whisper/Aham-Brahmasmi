# Authorship and provenance

A license tells people what they may do with Aham Brahmasmi. Provenance [proof of where something came from] helps show which project state existed first and who controlled it at that time.

No watermark can be guaranteed to survive deliberate rewriting, file renaming, model-assisted refactoring, or an attacker who is actively searching for hidden markers. Aham Brahmasmi therefore treats cryptographic evidence and ordinary public history as the primary proof rather than relying on a secret phrase hidden in source code.

## Evidence layers

The release strategy uses several independent records:

1. Git commit history preserves the evolution of the project.
2. Release tags identify reviewed release states.
3. A cryptographic commitment can bind an offline secret to the exact Git tree of a reviewed state.
4. The `NOTICE` file and repository history identify the project and copyright holder.
5. Optional signed tags or release signatures can add another identity signal when the maintainer chooses to configure signing.

None of these prevents copying. Together they make origin easier to demonstrate later.

## Create a release commitment

Before the first public release, create a random secret of at least 32 bytes and keep it outside this repository. Do not commit it, upload it, paste it into an issue, or send it to a model.

One example on a system with OpenSSL is:

```text
openssl rand -out /safe/offline/location/aham-provenance-secret.bin 64
```

The command above is only an example. The essential requirement is a private random file kept outside the repository.

From the reviewed Aham Brahmasmi checkout, create the public commitment:

```text
python3 scripts/provenance.py create \
  --secret-file /safe/offline/location/aham-provenance-secret.bin \
  --output PROVENANCE_COMMITMENT.json
```

The tool reads the current Git tree, combines that tree identifier with the secret under a project-specific domain, and stores only a SHA-256 commitment. The secret itself is never copied into the output or printed.

The generated public JSON can then be committed with the release preparation. Because adding that JSON creates a later Git tree, the commitment deliberately points to the reviewed tree immediately before the commitment file was added. That is not circular: it records exactly which earlier source tree the secret was bound to.

## Verify later

If proof is ever needed, make a copy of the offline secret available for that proof and run:

```text
python3 scripts/provenance.py verify \
  --secret-file /path/to/revealed-secret.bin \
  --commitment-file PROVENANCE_COMMITMENT.json \
  --repo /path/to/Aham-Brahmasmi
```

A successful verification shows that the revealed secret matches the commitment tied to the recorded Git tree.

Revealing the secret should be treated as a one-way event. After public disclosure, use a new secret for later release commitments.

## What this proves and what it does not

The commitment can support a claim that someone possessing the secret created a public commitment tied to a specific project tree before later disclosure of that secret.

It does not by itself prove ownership of an abstract idea, patent rights, trademark rights, or that nobody independently created similar software. It also does not replace the Apache 2.0 license, copyright law, release history, or professional legal advice if an actual dispute occurs.

## Hidden fingerprints

Distinctive tests, fixtures, wording, schemas and structural choices may incidentally help identify copied code. They should remain legitimate parts of the project rather than fragile or malicious traps.

Do not insert secrets, tracking code, telemetry, misleading behavior, or code whose only purpose is to harm someone who copies the repository. Provenance should remain inspectable and compatible with the project's public trust model.

## Public release gate

Before changing repository visibility, the maintainer should:

- generate a fresh offline secret;
- create `PROVENANCE_COMMITMENT.json` for the final reviewed pre-release tree;
- commit the public commitment but not the secret;
- retain the secret in at least one safe offline location;
- create the release tag only after the final release audit passes;
- optionally sign that tag when a signing identity has been deliberately configured.

Publication required explicit maintainer authorization, given on 2026-10-02 for a public preview. No provenance commitment exists yet; generate one before the first tagged release.
