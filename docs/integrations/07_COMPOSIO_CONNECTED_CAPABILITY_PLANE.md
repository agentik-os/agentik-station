# Composio Connected Capability Plane

Composio is an integration adapter available to AGK OSs. It does not replace Hermes, AGK capability policy, Station trust boundaries or deterministic programs.

Current Composio capabilities relevant to Station include a large toolkit catalog, per-user sessions, authentication/connected accounts, meta-tool discovery, direct tools, triggers, hosted MCP and a session-scoped sandbox.

## Canonical place in the stack

```text
OS capability contract
        ↓
AGK/Station policy compiler
        ↓
Adapter selection
 ┌──────┼───────────────┬──────────────┐
 ↓      ↓               ↓              ↓
Hermes  MCP/plugin     Composio      Direct API
native                  session
                          │
                 toolkit/tool allowlist
                          │
                 connected account refs
                          │
                    external SaaS
```

Hermes remains the agentic execution kernel and owns sessions, Bots/profiles, Kanban, delegation, cron, hooks and mission execution. A Composio session is a scoped external-tool context used by a Hermes profile/mission when required.

## Production default

An OS does not receive all Composio tools. It declares capabilities. Builder compiles those capabilities into a restricted Composio session policy.

Exploratory operators may use constrained meta-tool discovery. Production workflows should prefer known direct tools when the required action set is stable.
