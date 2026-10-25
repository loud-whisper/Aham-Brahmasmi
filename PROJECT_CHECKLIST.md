# Preview acceptance checklist

## Framework verification

- [ ] Foundation checks pass on the final release tree.
- [ ] The complete Linux unit suite passes, with skips reported.
- [ ] The Ubuntu/macOS portability matrix and native Windows core jobs pass for the final commit.
- [ ] The offline isolated release rehearsal passes.
- [ ] Privacy, attribution and release assets are reviewed.

## Live-runtime acceptance

- [ ] Claude-compatible live runtime path tested.
- [ ] Gemini-compatible live runtime path tested.
- [ ] Codex-compatible live runtime path tested.
- [ ] At least one local/open-model live runtime path tested.

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


## Human acceptance and publication

- [ ] Fresh user completes setup without architecture knowledge.
- [ ] Fresh user switches assistant using durable state.
- [ ] Fresh user recovers an interrupted operation using diagnostics.
- [ ] Reviewer checks that reader-facing claims match current evidence.
- [ ] The maintainer approves the exact public candidate and available repository safeguards.
- [ ] Offline provenance is prepared before the first tagged release.

This is a preview. Open boxes describe work still required for broader acceptance, not completed demonstrations. See `docs/TEST_PLAN.md` and `docs/dev/WALKTHROUGH_PROTOCOL.md`.
