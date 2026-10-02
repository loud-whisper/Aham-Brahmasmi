# Security policy

## Reporting

Do not report exploitable vulnerabilities through public issues, pull requests or
chat transcripts. Do not include private Brain files, credentials or personal data.
Use a small synthetic reproduction and the affected framework commit/version.

Before publication, the maintainer must enable GitHub private vulnerability
reporting and verify that this repository's Security page offers **Report a
vulnerability**. That route is not claimed to be enabled while this repository is
private. Email the maintainer at aham1700@outlook.com as the private fallback.
This address was designated by the maintainer for project reports; no response-time
guarantee is offered. See `docs/MAINTAINER_PUBLICATION_CHECKLIST.md`.

Include the operating system, Python version, expected behavior, actual behavior,
and a minimal reproduction. Keep an existing workspace intact. Coordinate a fix
and disclosure with the maintainer before publishing exploit details.

## Scope and supported versions

The project is pre-release. Reports against current main are welcome; no older
release maintenance promise is made. Future supported versions will be listed here
when their release policy is established. Platform guarantees are limited to
`docs/PLATFORM_SUPPORT.md` and retained exact test evidence.

Scope includes controller authority, containment, durable state/recovery,
third-party scanning/activation, scoped recall, import/export, and unintended
disclosure through the framework. Static scanner PASS is not a security guarantee.
Aham does not sandbox the account that owns its files, encrypt the Brain, verify a
human's identity from a confirmation string, or make a fully compromised account
safe. See `docs/THREAT_MODEL.md`.
