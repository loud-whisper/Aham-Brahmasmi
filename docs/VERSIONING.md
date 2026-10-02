# Versioning and release preparation

Framework releases use [Semantic Versioning 2.0.0](https://semver.org/): MAJOR for incompatible public command
or contract changes, MINOR for compatible capabilities and PATCH for compatible
fixes. Pre-release identifiers may describe reviewed release candidates. There is
no published framework version assigned by this document. Tags use `vMAJOR.MINOR.PATCH`
after the maintainer approves a specific release; no tag or GitHub release is
created automatically. The public API consists of documented commands and core
contracts; internal Python helpers do not imply a stable public library API.

Workspace schema versions are independent integers governed by the R1 migration
contract. Changing the framework version does not silently migrate a Brain. A
release must describe any schema change, backup requirements and supported
migration/recovery route. See `core/` schema contracts and `scripts/schema_compat.py`.

Before tagging, complete the publication checklist and run release checks on the
actual reviewed tree. Record exact acceptance commits/runs, source pins, platform
limits, migration notes and known issues in release notes and CHANGELOG. The
provenance commitment follows `docs/PROVENANCE.md`: a fresh secret is generated
offline, kept outside Git and never uploaded or provided to a model. Its public
commitment binds the reviewed pre-commitment tree. Later tree changes require a
new review/commitment. Human privacy review and explicit publication authorization
remain required even when automated checks pass.
