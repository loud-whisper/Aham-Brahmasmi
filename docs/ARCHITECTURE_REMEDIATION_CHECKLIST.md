# Architecture and acceptance checks

Preserve the implemented canonical writer, immutable identities, crash-safe revision boundary, containment, runtime trust, evidence classification and recovery behavior. Review their regression tests before modifying these interfaces. Use `docs/TEST_PLAN.md` for the verification entry points.

## Preview gates

- [ ] Fresh user completes setup without architecture knowledge.
- [ ] Fresh user switches assistant using durable state.
- [ ] Fresh user recovers after an interrupted operation.
- [ ] Live-runtime results are captured and independently verified for the tested configurations.
- [ ] Platform checks cover the final release commit.
- [ ] The final public tree passes privacy, attribution, packaging and provenance review.

## Implementation boundaries

- Keep one canonical writer and revision authority. A receipt must reflect verified durable state.
- Keep user workspaces independent of the public framework and of any provider.
- Preserve migrations, read compatibility and deterministic crash recovery.
- Keep external sources pinned, quarantined and inactive until their required review is satisfied.
- Keep single-run evidence separate from reliability claims and framework tests separate from live assistants.
- Add broader runtime or shared-workspace support only with explicit requirements and corresponding tests.

`PROJECT_CHECKLIST.md` owns current release acceptance. `docs/STATUS.md` is generated from the evidence register where applicable. No checklist item is evidence of execution by itself.
