# Worktree Isolation Standard

Hermes has native Git worktree support for sessions, delegated children and Kanban workspaces. Agentik standardizes its use.

## Important correction

A Discord thread is a conversation/session surface. It does **not** automatically equal a Git worktree.

```text
Discord Thread → Hermes Session
Engineering Mission → Kanban root task
Code-writing workstream → Worktree
```

A conversational thread may never touch code. A single engineering thread may create several isolated worktrees when the mission fans out.

## Canonical rules

- One substantial mutable code workstream ≈ one branch/worktree.
- Parallel code-writing workers MUST use separate worktrees.
- Each worktree has its own checkpoint/rollback history.
- Integration happens deliberately through reviewed commits/branches.
- Dirty or unmerged worktrees are preserved for recovery.
- Cleanup only prunes safe, merged/clean worktrees.

## Naming

```text
.worktrees/
├── mis-184-api/
├── mis-184-ui/
└── mis-184-tests/
```

Branches:

```text
agentik/mis-184-api
agentik/mis-184-ui
agentik/mis-184-tests
```

## Integration gate

No branch is merged only because its worker reports success. Required evidence travels with the branch and the integration node reruns relevant checks after merge.
