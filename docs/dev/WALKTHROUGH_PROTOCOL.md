# Nontechnical newcomer walkthrough protocol

## Status and participants

Pending: no human outcomes are recorded here. Recruit **two or three** testers with
**no Git or Python** knowledge, using fresh machines or disposable VMs on supported
systems. Use **synthetic** data only. Do not invite people or send messages through
tools without the maintainer's authorization. Do not make the private repo public
to recruit testers.

Automated rehearsals establish controller behavior; they do not count as these
human tests. The four R7 checklist gates remain unchecked until real outcomes are
reviewed. Record the exact framework commit used. Do not transfer a PASS to newer
code without determining whether the relevant flow changed.

## Observer preparation

1. Provide a clean framework copy at the reviewed commit and an available assistant
   that meets its own official prerequisites. Prepare supported Python only if the
   test's declared scope excludes prerequisite installation; record that choice.
2. Prepare a synthetic project outside the framework. Use no personal Brain,
   credentials, real account names or private project content in test artifacts.
3. Give the participant only README and the setup instruction. Keep architecture
   explanations and developer notes out of the user flow.
4. Have a second assistant/model available for the switch task. Record whether it
   is a distinct tool, model or fresh session; do not claim a harness switch when
   only its label changed.
5. For the interrupted task, use the real writer's tested fault injection on the
   synthetic workspace after the participant authorizes the save. Set
   `AHAM_BRAHMASMI_TEST_MODE=1` and
   `AHAM_BRAHMASMI_TEST_CRASH_POINT=checkpoint_after_pending` on that save process
   only. It must exit 86 and leave a valid pending checkpoint. See the concrete
   process fixture in `tests/test_r7_newcomer_flow.py`. Never fabricate a pending
   file or invent successful markers. The participant sees the ordinary diagnostic
   and recovery instructions, not fault-injection machinery.

## Participant tasks

Ask the participant to complete each task with the documentation and their assistant:

1. **Setup:** open the framework, ask it to read START_HERE, approve a separate local
   workspace and decide whether the assistant may save. Complete prerequisite
   permission/terminal hand-offs and verify the Brain. A failure must show a useful
   next action rather than false readiness.
2. **Connect and work:** connect the synthetic project. Give it a small task that
   creates a harmless text artifact and records a synthetic fact and an unfinished
   task. Save and wrap up through the canonical commands with actual verification
   markers. Record the durable operation/checkpoint IDs, not assistant prose.
3. **Switch:** open the other assistant/model in a fresh session, make a separate
   owner trust choice if needed, start and resume the same Brain. Ask it for the
   saved fact and next task. Verify the selected checkpoint and durable content.
4. **Interrupted recovery:** after the observer prepares the valid interrupted
   operation, ask the participant to run `aham.py check` through their assistant,
   follow its next action, recover and verify. The recovered operation must be the
   same accepted operation, with no duplicate ledger entry. An old/no-trust session
   may need confirmed `recover-access`; it must not grant unrelated new work.
5. **Explain:** ask the participant where their private data is stored and which
   command or message convinced them that saving worked. Do not coach the answer.

## Observation and outcome

Record where the participant became stuck, what the screen/message said and what
they tried next. Help only when requested or the task cannot continue; record every
intervention. A task completed after coaching is not an independent PASS. Create
a sanitized issue description for each stuck point; the maintainer decides whether
to publish an issue. No automated tool messages to testers or issue posting is
authorized by this protocol.

Use `docs/dev/WALKTHROUGH_RESULT_TEMPLATE.md` with tester codes such as T1/T2,
OS/Python/assistant versions, exact framework revision, scope and outcome per task.
Store only synthetic commands/results and redacted screenshots if needed. Avoid
usernames, private paths, account data, tokens, personal memory and raw chat logs.

Mark R7 gates complete only after reviewed human evidence supports them. Keep
unresolved failures as open work and rerun the affected flow after a concrete fix.
Publication remains a separate maintainer decision after R8.
