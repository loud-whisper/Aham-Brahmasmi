# Preview status

Release: 0.1.0-preview.1, launch edition dated 2026-10-25.

The lifecycle, checked writer, recovery, optional integrations and diagnostics are implemented. This release remains a preview. A passing unit suite does not establish that a real person or external assistant completed the workflow.

## Runtime evidence

<!-- runtime-evidence-status:start -->
Runtime evidence source of truth: `evidence/runtime_harness_register.json`.

| Runtime/profile | Current evidence | Scope |
| --- | --- | --- |
| Claude | No live rehearsal evidence recorded | Live release gate remains open |
| Gemini | No live rehearsal evidence recorded | Live release gate remains open |
| Codex | No live rehearsal evidence recorded | Live release gate remains open |
| Local/open-model | No live rehearsal evidence recorded | Live release gate remains open |
| Framework/profile tests | No framework/profile evidence recorded | Framework/profile only |

A live pass records one independently verified rehearsal in one tested environment. It does not establish a reliability percentage or prove other runtime/model/harness configurations.
<!-- runtime-evidence-status:end -->


## Open acceptance checks

- Real newcomer setup, model switch and recovery walkthroughs.
- Current live rehearsals for each advertised assistant configuration.
- Hosted macOS and Windows results for the final release commit.
- Final privacy, packaging, provenance and publication review.

Linux unit results and release-rehearsal output are retained with the release review. Use the checked-in CI workflows to establish results for a specific commit. Unsupported or skipped checks remain visible. No reliability percentage is claimed.

Registry review dates concern pinned upstream source/interface checks, not successful runtime activation. Optional sources are not installed or activated by this repository. See `docs/SOURCE_REVIEW.md` and `docs/MEMORY_CONNECTION.md`.
