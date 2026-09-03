# Skills, Plugins and Hooks

## Hermes-first rule

Use native Hermes skills/plugins/hooks rather than building parallel Agentik infrastructure.

## Canonical skill bundles

```text
devops-engineering
├── plan-first
├── verification-engineering
├── architecture-review
├── github-pr
├── evidence-capture
└── ponytail integration
```

## Ponytail

Ponytail is a canonical **engineering discipline plugin** for DevOps/Builder/Engineering OSs.

Official Hermes install:

```bash
hermes plugins install DietrichGebert/ponytail --enable
```

Restart Hermes after installation.

Expected available commands/skills include:

```text
/ponytail
/ponytail-review
/ponytail-audit
/ponytail-debt
/ponytail-gain
/ponytail-help
```

Policy:
- FULL mode by default for engineering Director/Architect/Developer
- review/audit skills for Reviewer/QA/Security
- pin the plugin revision in `agentik.lock`
- never grant plugin lifecycle commands to untrusted Discord users

## Agentik Control plugin

Primary custom Hermes plugin:

```text
agentik-control
```

Responsibilities:
- expose resolved organization/project/OS context
- enforce AGK capability policy around sensitive tools
- create/read AGK mission metadata
- emit evidence
- submit memory candidates
- synchronize integrations
- expose Discord binding metadata to the orchestrator

It should **not** recreate Hermes sessions, delegation, Kanban or gateway.

## Discord Provisioner plugin/service

System-only component:

```text
agentik-discord-provisioner
```

Responsibilities:
- inspect current guild state
- compile desired state
- compute plan/diff
- apply idempotently
- persist immutable ID bindings
- verify routing
- remove bootstrap privilege
- reconcile drift

Only the Bootstrap Director gets its privileged capability.

## Important hooks

```text
on_session_start
on_session_end
pre_tool_call
post_tool_call
kanban_task_claimed
kanban_task_completed
kanban_task_blocked
subagent_start
subagent_stop
discord_bootstrap_started
discord_resource_created
discord_binding_written
discord_bootstrap_verified
discord_runtime_demoted
discord_drift_detected
```

Before sensitive actions:

```text
pre_tool_call
→ resolve org/profile/project/environment/capability
→ allow / deny / require approval
```
