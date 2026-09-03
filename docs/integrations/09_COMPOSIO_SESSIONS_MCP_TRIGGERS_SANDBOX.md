# Composio Sessions, MCP, Triggers and Sandbox

## Session lifecycle

Use a new Composio session for a new mission/task context or materially different tool/auth policy. Reuse the same session only when the same durable conversation/mission should retain its tool, auth and sandbox state.

```text
Hermes Mission / Session
        ↓
Station integration binding
        ↓
Composio session_id
```

Store the live session ID in runtime state, never in the immutable package.

## Direct tools vs meta tools

```text
stable production workflow -> direct allowlisted tools preferred
exploratory operator work   -> meta tools allowed within toolkit policy
```

Meta-tool discovery never overrides AGK capability policy.

## Hosted MCP

A Composio session may expose a hosted MCP endpoint. Hermes can consume that endpoint when MCP is the cleanest transport. The endpoint is runtime configuration and is not package content.

## Triggers

Composio events enter Station through governed ingress:

```text
Composio trigger
   -> Station webhook ingress
   -> signature/identity/policy checks
   -> event normalization
   -> route to OS
   -> create/reopen Mission or Kanban task
   -> Nano Director
```

Do not route a trigger directly to unrestricted external writes.

## Sandbox boundary

Use Composio's session sandbox for large external-tool responses, bulk transformations and session-local remote work when appropriate. Use Hermes project/worktree/sandbox primitives for repository coding and codebase isolation. Avoid stacking two sandboxes without a clear reason.
