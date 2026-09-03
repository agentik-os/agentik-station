# Hermes Native Engineering Capabilities

Checked against Hermes documentation on 2026-09-03.

## Native primitives we should use instead of rebuilding

### Self-improvement
Hermes describes itself as having a closed learning loop with memory curation, autonomous skill creation/improvement and cross-session recall.

Source:
https://hermes-agent.nousresearch.com/docs/

### Verification-on-stop
Hermes can require fresh verification evidence after code edits before accepting the agent's final response.

Source:
https://hermes-agent.nousresearch.com/docs/user-guide/configuration/

### Worktrees
Hermes supports automatic session worktrees and child/subagent worktree isolation.

Sources:
https://hermes-agent.nousresearch.com/docs/user-guide/git-worktrees
https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation

### Parallel delegation
Hermes supports concurrent delegated children, bounded spawn depth and orchestrator/leaf topology.

Source:
https://hermes-agent.nousresearch.com/docs/user-guide/configuration/

### Model/provider portability
Hermes supports numerous provider integrations, custom OpenAI-compatible endpoints, route/fallback configuration, per-request model selection and delegation model overrides.

Sources:
https://hermes-agent.nousresearch.com/docs/integrations/providers
https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers
https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server

### Logs
`hermes logs` exposes agent, error and gateway runtime logs with profile-specific storage.

Source:
https://hermes-agent.nousresearch.com/docs/reference/cli-commands

### Ponytail
Ponytail supports Hermes directly:

```bash
hermes plugins install DietrichGebert/ponytail --enable
```

Source:
https://github.com/DietrichGebert/ponytail
