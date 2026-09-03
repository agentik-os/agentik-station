# Discord Experience Contract — Canonical

Discord is the primary human control surface of a live OS, not a debug console.

## Hard goals

1. A human sees the **mission plan**, not raw chain-of-tool noise.
2. Every working mission has one stable **Mission Progress Card** that is edited in place.
3. The card exposes current state, completed steps, next step, loop/retry state, blockers and approvals.
4. The agent creates a structured plan **before execution** and keeps it synchronized with the durable mission graph.
5. The final state replaces the working card with a clean completion/failure report.
6. Low-level Hermes logs and tool traces remain available for audit without flooding the human chat.
7. Interactions use Discord-native Components V2 where supported, with a legacy fallback.
8. Buttons are actions, not paragraphs. Long labels/instructions live in Text Displays, Sections, Containers, selects or modals.
9. All interaction handlers re-resolve Station context and permissions server-side. The model never chooses authorization.
10. Each canonical OS has its own dedicated Discord bot identity and primary channel; internal specialists stay behind Hermes unless explicitly exposed.

## Surface model

```text
Dedicated OS Bot
    -> primary OS channel
        -> thread = Hermes conversation/session surface
            -> Mission Progress Card = live human projection of mission state
                -> Mission = durable AGK work object
                    -> Hermes Kanban root task / DAG
                    -> Loop-Graph
                    -> workers / subagents / worktrees
```

Discord is a projection. Durable mission state, evidence and graph state do not live only inside a Discord message.

## Evidence Before Claims projection

The progress card has two independent dimensions:

1. **graph progress** — which planned nodes have been traversed;
2. **evidence stage** — prepared, observed, reported, verified, read back, accepted.

The renderer derives evidence labels from durable Station state. An LLM cannot promote its own status by wording a message differently. Execution and verification owners are shown when useful, especially for engineering and high-risk missions.
