# Aham Brahmasmi project rules

These rules apply to any model, CLI, harness, contributor, or automation working in this repository.

## Non-negotiable boundaries

1. This repository is a standalone public-facing project. Do not read from, import from, sync with, or copy files from any private personal Brain, private workspace, private repository, home directory, machine-specific configuration, or unrelated project.
2. Build generic behavior from this repository's requirements and from verified public upstream sources only.
3. Never add credentials, tokens, private URLs, personal memory, machine hostnames, account identifiers, private infrastructure details, or absolute user-specific filesystem paths.
4. Do not invent commands, flags, integrations, APIs, file formats, capabilities, licenses, or upstream behavior. Verify them from the relevant public source before implementation. If verification is unavailable, record the item as unresolved instead of guessing.
5. Keep the framework independent of any single model, vendor, CLI, harness, operating system, memory backend, or skill loader.
6. GitHub-backed durable state and optional memory backends must remain replaceable components. Optional integrations must never become startup requirements unless the project explicitly changes that contract.
7. Third-party skills, forks, templates, or tools remain owned by their original authors. Prefer linking and reproducible installation from verified upstream sources over copying their content into this repository.
8. A third-party source may not be activated until its upstream URL, license, source reference, integration method, and review status are recorded in the third-party registry.
9. New or changed behavior requires tests. Do not claim a feature works unless its relevant checks have passed.
10. Work on a feature branch. Keep `main` reviewable and release-ready.
11. Before changes, read `PROJECT_CHECKLIST.md`, `docs/TEST_PLAN.md` and the relevant architecture or interface guide. Keep unfinished human and live-runtime gates open.
12. Preserve canonical writer, containment, recovery and evidence contracts; add behavioral tests before changing them.
13. Use `docs/LESSONS_LEARNED.md` as engineering guidance, not as evidence that a new case has the same cause.

## Sources of truth

- `docs/ARCHITECTURE_REMEDIATION_CHECKLIST.md` records architecture safeguards and current acceptance gates.
- `PROJECT_CHECKLIST.md` tracks the wider build and what remains before a public release.
- `docs/TEST_PLAN.md` defines the acceptance tests.
- `docs/LESSONS_LEARNED.md` records active project-specific lessons that should shape future diagnosis, isolation, and verification work.
- `docs/PUBLIC_BOUNDARY.md` defines what may and may not enter this repository.
- `docs/THIRD_PARTY_POLICY.md` defines how external skills and tools are connected.
- `third_party/registry.json` is the machine-readable list of approved external sources.

The project checklist controls release acceptance. Architecture guidance preserves implemented safety contracts. Engineering guidance does not override acceptance criteria or test evidence.

## Stop conditions

Stop and report the unresolved point rather than making assumptions when:

- a required upstream source cannot be verified;
- licensing or attribution is unclear;
- a change might expose private or machine-specific information;
- a proposed dependency would lock the Brain to one runtime;
- a test fails and the cause is not understood;
- the repository state differs from the expected branch or reviewed state;
- a proposed task bypasses an unfinished acceptance prerequisite.

The objective is not to reproduce anybody's private setup. The objective is to provide a clean, understandable system that a new person can configure for themselves.
