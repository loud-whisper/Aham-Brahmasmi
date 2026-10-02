# Context packets and runtime conformance

R3 adds a bounded project-scoped context surface and an evidence-derived runtime/harness conformance matrix. These are separate claims: framework tests prove how packets are assembled, while retained live evidence proves only the runtime capabilities actually exercised by those historical runs.

## Bounded project context

`scripts/context_packet.py` builds one deterministic JSON packet for a stable project ID from authoritative workspace state.

The packet is revision-bound. `source_revision` is the current immutable operation-ledger revision, while the checkpoint block records the latest independently attributable checkpoint for the requested project and its own committed revision.

The packet uses:

- the stable project registry and immutable operation ledger;
- the current R2 fact/task lifecycle replay, not stale Markdown projections;
- the latest structurally valid checkpoint bound to the requested project and workspace identity;
- committed project updates attributable to the requested project;
- S2 verified active skills and project preferences from the same ledger revision,
  represented only by qualified names and one-line untrusted descriptions.

Only active facts and open tasks are included. Superseded/retracted facts and completed/cancelled tasks remain in durable history but are not injected into the compact packet.

### Project scoping rule

Legacy wrap-up facts and tasks do not carry per-item project IDs. They are therefore injected into a project packet only when their authoritative wrap-up operation names exactly one stable project. If a wrap-up spans multiple projects, those otherwise ambiguous facts/tasks remain unscoped and are omitted rather than copied into every project packet.

A superseding fact inherits the project scope of the fact it replaces. Explicit lifecycle assertions that have no project binding remain global/unscoped and are not silently injected into a project packet.

This rule favors omission over cross-project context leakage.

## Budget semantics

The CLI accepts `--max-bytes`. The emitted JSON, including its trailing newline, must fit that exact byte ceiling.

R3 does **not** claim that bytes equal model tokens. Every packet and matrix therefore records `token_equivalence_claimed: false`.

The required project/checkpoint core must fit. If it does not, packet construction fails rather than emit an invalid fragment. Optional content is added deterministically in this order:

1. project updates;
2. active facts;
3. open tasks;
4. optional skill names/descriptions, with descriptions capped at 160 characters.

When the byte ceiling is reached, omission counts are explicit in `budget.omitted`, `budget.truncated` becomes true, and repeated construction from the same authoritative revision and verified external content produces the same serialized result. `packet_sha256` binds the packet content excluding the digest field itself.

Full skill bodies are read only on demand. Disabled and drifted skills are absent.
Broken optional source metadata or a skill snapshot from a different revision omits
the skill list and reports `skills_status: unavailable`; core project context remains
available. This feature does not demonstrate live runtime skill consumption or grant
execution permissions. See [Portable skill discovery](SKILL_INDEX.md).

## Checkpoint integrity

Context assembly does not trust a checkpoint merely because a referenced file exists. The selected checkpoint must:

- pass the normal checkpoint schema validation;
- belong to the current workspace identity;
- match the authoritative operation revision;
- identify the requested project.

A corrupt or mismatched authoritative checkpoint is rejected rather than silently replaced with unrelated project state.

## Capability-based conformance tiers

`core/runtime_conformance.json` defines vendor-neutral tiers. Runtime or vendor names do not grant capability.

- `context_packet`: bounded project context is available for consumption without whole-Brain browsing.
- `lifecycle_reader`: bounded context plus independently demonstrated authoritative lifecycle reading.
- `lifecycle_writer`: an independently verified live lifecycle rehearsal completed with exact runtime/harness/context metadata.
- `recovery_verified`: a fresh target session independently recovered committed durable state.

A tier is an evidence statement, not a quality score or reliability percentage.

## Retained evidence matrix

`scripts/runtime_conformance.py matrix` reads the canonical runtime evidence register and selects only sufficiently rich independently verified entries. Current retained rich evidence supports:

- DeepSeek Harness 0.1.5-rc.2 with the recorded Qwen3.8-27B run at 65,536 context as `lifecycle_writer` evidence;
- OpenCode 1.14.25 with the recorded Qwen3.8-27B live/recovery evidence at 65,536 context as `recovery_verified` evidence.

Recovery conformance is bound to the exact demonstrated harness version, model, context size and quantization. A recovery pass for one model/configuration does not upgrade a different model on the same harness version.

Historical Gemini/Codex passes remain retained but unclassified when exact metadata is insufficient. A future runtime name by itself cannot grant conformance.

The selected R3 matrix sets `new_live_runs_required: 0` because existing retained evidence already covers the selected lifecycle/recovery tiers. This avoids spending model/runtime cost merely to reproduce claims already independently verified.

### Important evidence boundary

The retained DSH/OpenCode live rehearsals occurred **before** R3 introduced `context_packet.py`. They therefore do not prove that either harness consumed the new compact packet in a live session. R3's packet construction, project isolation, lifecycle freshness, byte bounds and checkpoint validation are framework-level claims covered by automated regression tests.

No current runtime is promoted to a packet-consumption or lifecycle-reader tier merely from its name or from those historical runs. A future live test may establish that additional capability if it becomes necessary for a release claim.

## Cost and context policy

R3 uses byte-bounded framework packets and retained evidence to keep context/cost explicit. It does not infer token counts from bytes, does not require low-context runtimes to browse the whole Brain, and does not require a new paid/live model invocation when existing evidence already proves the selected capability tier.
