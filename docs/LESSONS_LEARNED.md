# Lessons Learned

## 2026-10-01: archive provenance must verify the historical payload

A valid current activation and a valid prior source entry do not verify the
replacement operation that links them to an archive. After removal followed by
reinstallation, rollback could select an archive whose historical deactivation
record had a corrupt payload digest. A synthetic regression reproduced it before
the fix. Archive selection now checks that operation's complete payload digest as
well as its path, prior entry and source identity. Rechecking only the current
operation would miss this case.

This file records project-specific lessons that should influence ongoing Aham Brahmasmi development. It is active project context, not a substitute for tests, evidence, or the ordered remediation and release checklists.

## 2026-10-01: POSIX parent aliases in the skill index

S2's initial matrix passed Linux and Windows refusal checks but both macOS jobs
failed during index materialization. Its temporary workspace path used an operating
system parent alias; managed-path checks returned the canonical root. Comparing a
canonical skill path against the unresolved workspace raised a relative-path error.

A synthetic POSIX parent-alias test reproduced the error locally. The fix keeps
the existing workspace/containment checks and then uses the canonical root for
relative index paths. Exact head `476222d` passed corrected matrix `36879782673`.
Retain this regression when adding lifecycle or archive operations. Resolve the
declared root consistently; do not relax child-path containment to hide an alias
error. A Linux pass alone did not establish macOS behavior.

## 2026-09-19: Local Qwen + DeepSeek Harness live rehearsal

### Context

A local Qwen3.8-27B path repeatedly failed the prior day. It would have been easy to conclude that the model itself was not capable enough for the Aham lifecycle. After the Astra architecture review, M1-M6 remediation, stricter runtime isolation, and a different harness path, the same model family completed the full lifecycle and passed the independent trusted verifier.

The independently verified successful run used:

- framework commit: `97f90bce914f0b2e44c84fe44703eecf37b719ce`
- runtime profile: `local`
- harness: DeepSeek Harness `0.1.5-rc.2`
- model: `unsloth/Qwen3.8-27B-GGUF`
- quantization: `UD-Q4_K_XL`
- context: 65,536 tokens
- rehearsal ID: `40d65ed2680049e3`
- project commit: `eb01ad4348b21b175a14f7b0c570e4aee6775aec`
- independent result: `LIVE RUNTIME REHEARSAL VERIFIED`

This is one smoke test in one tested environment. It is not a reliability percentage and does not prove that one harness is universally superior.

### Lessons

1. **Do not blame the model before isolating the system.** A failed agent run can be caused by the framework, harness, permissions, context, sandbox, runtime integration, process lifecycle, or verifier. Hold the model and task constant and vary one surrounding layer at a time.

2. **Treat model quality and harness quality as separate variables.** To compare harnesses fairly, use the same model, quantization, context, framework revision, task, and verification criteria. The successful DSH run proves this model can complete the tested Aham lifecycle under that configuration. It does not yet prove that DSH is generally better than OpenCode.

3. **Separate trusted model serving from sandboxed agent execution when practical.** Trying to place Unsloth model serving inside the agent sandbox required exposing GPU device nodes, sysfs metadata, virtual-environment dependencies, and parts of the real home. That was the wrong trust boundary. The safer architecture is to keep the GPU/model server on the trusted host and let the sandboxed harness reach only the loopback API.

4. **Do not weaken isolation just to make an integration fit.** A preflight may reveal that a runtime needs more host state. Before adding exceptions, ask whether the architecture can be rearranged so the privileged component stays outside the agent trust boundary.

5. **Use deterministic headless paths for certification.** The DSH headless profile was appropriate for the live gate because it provided a one-shot process, visible tool activity, a meaningful exit code, and a clean point for independent verification. Interactive terminal or browser interfaces are useful for normal work but should not replace the deterministic evidence path.

6. **Independent verification outranks runtime prose.** Statements such as "all gates passed" are useful diagnostics but are not authoritative. Success exists only after the trusted host verifier confirms exact task state, repository hygiene, lifecycle receipts, checkpoint/wrap-up state, and framework identity.

7. **Preserve the exact tested framework revision.** A live rehearsal proves the exact commit that was exercised. Do not change the branch after the successful run and then merge the changed head as though the new code had been tested. Follow-up evidence, documentation, or cleanup should happen on a later branch if it would alter the tested commit.

8. **Preserve failed rehearsals until the cause is understood.** The unsuccessful GPU, Unsloth, and sandbox preflights were useful because they identified specific infrastructure boundaries. Do not clean up or mutate failed state merely to obtain a green run.

9. **Wait for a normal harness exit before invoking the verifier.** A harness can finish its logical task before the process itself has returned. Pressing Ctrl+C at that point can convert an otherwise successful run into an interrupted process and make the result ambiguous. Wait for the shell prompt or use a deliberate graceful-termination procedure if the process is truly stuck.

10. **External architecture review is most useful when converted into durable gates.** Astra's value was not that it made the local model smarter. Its review exposed systemic weaknesses and led to the ordered M1-M6 remediation checklist. Architecture review should produce regression tests, acceptance criteria, and a durable work queue rather than remain advisory prose.

11. **Preflight each layer separately.** Before spending time loading a large model, verify executable paths, harness versions, sandbox identity, dependency visibility, API reachability, and required permissions independently. This distinguishes bootstrap failures from model or harness failures.

12. **A successful result should reduce uncertainty, not erase it.** The verified DSH run changes the diagnosis from "the model probably cannot do this" to "the model can do this under at least one known-good harness and architecture." Further controlled comparisons are still required before making broader claims.

### Working rule for future runtime investigations

When a model or harness fails, classify the failure before changing anything:

1. framework logic
2. lifecycle/session authority
3. filesystem or Git hygiene
4. sandbox/permissions
5. runtime bootstrap/dependencies
6. model server/API
7. harness behavior
8. model behavior
9. independent verification

Change one layer at a time, preserve evidence, and rerun the same task under the same verification contract.

### S4 provider-process portability

macOS can return a process-group `PermissionError` after a short-lived parent has
already exited. Group cleanup must distinguish that case from a still-running
owned child, which needs direct termination. Preserve the original timeout or
output-limit result instead of replacing it with a cleanup exception. Reproduce
both cases locally by injecting the signal refusal before spending another CI
matrix. Process-group cleanup is best effort, not an execution sandbox or proof
that every provider-created descendant was stopped.

### A1 authority prerequisites and chat import review

When authority defaults change, give positive lifecycle fixtures explicit synthetic
owner prerequisites before startup. Keep refusal assertions bound to unchanged
ledger bytes rather than assuming an empty ledger, and compute expected revisions
from the prerequisite state. Preserve exact session, project and revision checks.

Validate chat input before invoking a writer, forward the selected stable project
ID into the canonical writer, and bind duplicate imports to the original base
revision as well as payload and project. Test project-bound sessions separately
from an unbound owner session. After setup records optional trust, print the active
session ID rather than a superseded bootstrap ID.
