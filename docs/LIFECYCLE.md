# Work lifecycle

This page explains how Aham Brahmasmi keeps work recoverable without tying the Brain to one model or terminal.

## Starting work

For a normal session, first verify the private workspace.

If `state/pending_wrap_up.json` exists, do not start new work yet. Finish that interrupted wrap-up first.

If a durable checkpoint already exists, verify it before relying on it:

```text
python3 scripts/resume.py --workspace <workspace>
```

If the checkpoint recorded Git repository state, also provide the project repository:

```text
python3 scripts/resume.py --workspace <workspace> --repo <project-repository>
```

Recovery verifies the workspace identity. When Git state was recorded, it also verifies the branch and confirms that the checkpoint commit is still part of the current history.

## Saving a milestone

After a meaningful completed milestone, save a checkpoint:

```text
python3 scripts/checkpoint.py \
  --workspace <workspace> \
  --summary "What was actually completed" \
  --completed "Verified completed item" \
  --next-step "Next verified step"
```

When the task belongs to a Git repository, add:

```text
--repo <project-repository>
```

The checkpoint stores the repository name, branch and commit, not the local absolute repository path.

Only verified completed work belongs under `--completed`. Do not record an intended action as if it already happened.

## Wrapping up a session

When the user says `wrap up`, the assistant should classify durable session information into:

- durable facts;
- unfinished work;
- reusable lessons;
- project-specific updates;
- dated history;
- a final checkpoint.

The assistant then creates a temporary JSON bundle in the private workspace, not in the public framework repository. The shape is:

```json
{
  "session_id": "optional-stable-session-name",
  "durable_facts": ["A fact worth remembering"],
  "unfinished_work": ["A task that remains open"],
  "reusable_lessons": ["A lesson worth reusing"],
  "project_updates": [
    {
      "project": "Example Project",
      "content": "Project-specific state"
    }
  ],
  "history": ["A meaningful outcome from this session"],
  "checkpoint": {
    "summary": "Where the session ended",
    "completed": ["Verified completed work"],
    "next_steps": ["Where to continue"],
    "artifacts": ["Relevant commit, PR or file reference"],
    "project": "Example Project"
  }
}
```

Run:

```text
python3 scripts/wrap_up.py --workspace <workspace> --bundle <bundle-file>
```

Add `--repo <project-repository>` when repository state should be captured.

After a successful wrap-up, the temporary input bundle can be removed. The normalized completed transaction is already archived under `state/wrapups/`.

## If wrap-up is interrupted or fails

Aham Brahmasmi writes `state/pending_wrap_up.json` before routing durable state. Before each replay-safe stage, it also records the current step and useful detail in the transaction's `progress` field.

If a later operation fails, the command preserves the pending transaction and reports:

- the original error;
- the remaining wrap-up step;
- step detail when available;
- the recovery command to run.

For example, a failure while persisting a project update reports `route_projects` rather than merely saying that wrap-up failed.

Replay the preserved transaction with:

```text
python3 scripts/wrap_up.py --workspace <workspace> --recover-pending
```

If the transaction recorded Git state, provide `--repo` again.

Routed entries carry stable internal markers, so replaying the same transaction does not duplicate entries already written before the interruption. Progress is recorded before each stage so it remains useful even when the stage itself is the part that fails.

The tracked stages include repository verification, transaction validation, routing memory/tasks/lessons/projects/history, routed-state verification, final checkpoint creation, transaction archival and pending-transaction removal.

## What these scripts do not do yet

They do not automatically decide when a milestone has occurred. Runtime adapters still need to invoke checkpointing during long work and call wrap-up when the user requests it.

MemPalace is optional and is not required for any command on this page.
