# How Aham Brahmasmi fits together

This page shows the same project at two levels. The first view is for someone who only wants to understand what happens. The second view is for someone who wants to inspect how the pieces are separated.

## The simple view

```mermaid
flowchart LR
    A[You] --> B[Your current model or tool]
    B --> C[Aham Brahmasmi rules]
    C --> D[Your private Brain]
    D --> E[Memory]
    D --> F[Projects]
    D --> G[Tasks]
    D --> H[Lessons]
    D --> I[History and checkpoints]

    J[Optional skills] -. help with work .-> C
    K[Optional semantic memory] -. helps find related past information .-> D
    L[Optional local Git history] -. versions selected durable state .-> D
```

The important part is that the box on the left can change. Claude, Gemini, Codex, a local model, or a future tool can all use the same private Brain when they can follow the framework's instructions.

The private Brain belongs to the user. The model, skill collection, memory service and Git host do not own it.

## What using it feels like

```mermaid
flowchart LR
    A[Open a model or tool] --> B[Load Quick or Regular mode]
    B --> C[Give it a task]
    C --> D[Use an optional skill when useful]
    D --> E[Work]
    E --> F[Save meaningful checkpoints]
    F --> G{More work?}
    G -- yes --> E
    G -- no --> H[Wrap up]
    H --> I[Sort durable information]
    I --> J[Next session can continue]
```

If a session crashes after a checkpoint, the next session verifies that checkpoint and resumes from the last completed milestone instead of inventing what might have happened.

## The technical view

```mermaid
flowchart TB
    U[Person]

    subgraph R[Runtime layer]
        RC[Claude bridge]
        RG[Gemini bridge]
        RX[Codex bridge]
        RL[Local or unknown bridge]
    end

    subgraph C[Brain core]
        RULES[Rules and precedence]
        START[Startup modes]
        ROUTE[State routing]
        LIFE[Checkpoint, resume and wrap up]
        VALID[Validation]
    end

    subgraph W[User-owned private workspace]
        MEM[MEMORY.md]
        TODO[TODO.md]
        LES[LESSONS.md]
        PROJ[projects/]
        HIST[history/]
        STATE[state/ checkpoints and wrapups]
    end

    subgraph S[External-source safety]
        UP[Original upstream]
        REG[Registry and exact reviewed ref]
        Q[Quarantine]
        SCAN[Scanner]
        ACTIVE[Approved active source]
    end

    subgraph M[Optional memory and history]
        SMP[MemPalace adapter]
        GIT[Local Git transport]
    end

    U --> R
    RC --> RULES
    RG --> RULES
    RX --> RULES
    RL --> RULES

    RULES --> START
    START --> ROUTE
    ROUTE --> LIFE
    LIFE --> VALID
    VALID --> W

    UP --> REG --> Q --> SCAN
    SCAN -->|PASS only| ACTIVE
    ACTIVE -. optional capability .-> C

    SMP -. semantic recall only .-> W
    GIT -. selected durable snapshots .-> W
```

## Separation rules

The public project contains the framework only. Personal memory, private projects, machine-specific notes, credentials and private infrastructure belong outside it in the user's private workspace.

Runtime bridges translate the same core lifecycle into the instruction mechanism available to the current tool. A runtime name never grants permissions or capabilities by itself.

Skills and other third-party sources keep their original ownership and licenses. Installable sources are fetched from their original upstream at the exact reviewed commit, staged in quarantine, scanned, and activated only after a `PASS` result.

Local workspace files are the required durable state. MemPalace can improve semantic recall, and Git can add version history, but neither is required for the Brain to start or preserve its basic state.

## Design principle

Your tools may change. Your memory, skills, projects and progress should not.

Everything important belongs to the user, not to one model or one harness.
