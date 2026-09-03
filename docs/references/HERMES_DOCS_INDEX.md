# Hermes Documentation Areas to Keep Tracking

Official docs:
https://hermes-agent.nousresearch.com/docs/

Important sections for Agentik:

- Getting Started / Quickstart
- Updating
- Docker
- Profiles
- Profile Distributions
- Multi-profile gateways
- Discord
- Projects / CLI reference
- Kanban
- Goals
- Delegation
- Git Worktrees
- Context Files
- Skills
- Bundles
- Curator / Learn
- Plugins
- Hooks
- MCP
- Memory Providers
- Memory Provider Plugin developer guide
- Context Engine Plugin
- Cron
- Webhooks
- Checkpoints / Rollback
- Security
- Doctor / diagnostics / CLI reference
- Provider pools / fallback providers

## Documentation discipline

Because Hermes evolves quickly:

1. Agentik compatibility CI should track upstream.
2. Production should use approved versions.
3. New Hermes primitives should be evaluated before adding new custom AGK code.
4. `agentik.lock` should pin tested runtime combinations.

## Bot Mode (v3)
- https://hermes-agent.nousresearch.com/docs/user-guide/bot-mode

## v4 engineering harness references

- Self-improving learning loop: https://hermes-agent.nousresearch.com/docs/
- Persistent memory / background learning review: https://hermes-agent.nousresearch.com/docs/user-guide/features/memory
- Verification-on-stop + loop guardrails: https://hermes-agent.nousresearch.com/docs/user-guide/configuration/
- Git worktrees: https://hermes-agent.nousresearch.com/docs/user-guide/git-worktrees
- Subagent delegation + child worktree isolation: https://hermes-agent.nousresearch.com/docs/user-guide/features/delegation
- Kanban multi-agent durable task state: https://hermes-agent.nousresearch.com/docs/user-guide/features/kanban
- Providers: https://hermes-agent.nousresearch.com/docs/integrations/providers
- Provider routing: https://hermes-agent.nousresearch.com/docs/user-guide/features/provider-routing
- Fallback providers: https://hermes-agent.nousresearch.com/docs/user-guide/features/fallback-providers
- API per-request model selection: https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server
- Hermes logs CLI: https://hermes-agent.nousresearch.com/docs/reference/cli-commands
