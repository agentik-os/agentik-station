# Hermes First

## Native capabilities to maximize

Agentik Node should deliberately exploit Hermes capabilities before writing custom infrastructure.

### Runtime
- gateway
- profiles
- sessions
- multi-profile / multiplex operation

### Work
- Projects
- Kanban boards
- task dependencies
- triage / dispatch
- review states
- durable worker lifecycle

### Agents
- delegation
- subagents
- recursive orchestration
- worktree isolation

### Verification
- Goals
- deterministic gates
- verify-on-stop
- review / request-changes
- checkpoints
- rollback

### Knowledge / behavior
- SOUL
- context files
- skills
- bundles
- skill taps
- curator / learning workflows

### Extensibility
- plugins
- hooks
- MCP
- memory providers
- context engine plugins
- cron
- webhooks

### Operations
- doctor
- status
- security audit
- logs
- backups
- updates
- migrations

## Development rule

Before adding a new custom AGK service, answer:

1. Does Hermes already do it?
2. Can a plugin extend it?
3. Can a hook enforce it?
4. Can MCP expose it?
5. Can a profile distribution package it?
6. Can a skill encode it?
7. Can a Memory Provider handle it?

Only then create a new independent component.
