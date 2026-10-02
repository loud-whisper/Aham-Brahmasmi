# Public boundary

Aham Brahmasmi must be usable by strangers without containing or depending on the maintainer's personal workspace.

## Allowed

- Generic contracts, schemas, adapters, tests, documentation, and examples created for this repository.
- Public upstream links to third-party projects after source and license review.
- Reproducible installation instructions that fetch approved public upstream sources.
- Synthetic example data created specifically for documentation or tests.
- Optional adapters for external services when the service is not required for core startup.

## Not allowed

- Personal memory or preferences copied from an existing Brain.
- Private project notes, handoffs, history, TODOs, lessons, or work records.
- Credentials, tokens, cookies, account numbers, private URLs, or authentication material.
- Personal machine hostnames, local usernames, absolute personal filesystem paths, internal IP addresses, or private infrastructure details.
- Code or configuration copied from a private repository merely because it already works there.
- Hidden dependency on a maintainer-owned service, private repository, home directory, or machine.
- Third-party skill trees copied into this repository by default.

## Clean-room rule

Development of this public project must be driven by its own requirements and verified public sources. Existing private systems may inspire the product requirements, but their files are not an implementation source.

A fresh clone on a clean machine must not need access to any maintainer-owned private repository or machine in order to initialize and operate.

## User data rule

The framework and the user's data are separate concepts. Setup must create or connect a user-owned private workspace. The public framework must not ship with personal memory, projects, history, or machine context.

## Release check

Before publication, perform both automated scans and a human review. Automated checks are safeguards, not proof that privacy or licensing is correct.