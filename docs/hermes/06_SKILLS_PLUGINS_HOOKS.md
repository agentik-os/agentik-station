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
└── ponytail integration (required; blocked delivery)
```

## Ponytail

Ponytail is the intended **engineering discipline plugin** for DevOps/Builder/
Engineering OSs. It remains required but **NOT_INSTALLED** on the reviewed Host:
the retained native Hermes security scan rejected its reviewed immutable pin.
The integration is **SCAFFOLDED**; its commands and modes are unavailable.

Repair requires an upstream-reviewed scanner correction or published plugin
distribution, a reviewed immutable pin, the full native security scan and then
scoped runtime/command/ACL acceptance. Preserve the guard; no filtered source,
manual plugin copy, trust exception or bypass. See the
[native scan evidence](../audit/2026-09-05-ponytail-native-scan.md).

Intended commands/skills after acceptance, **not available now**:

```text
/ponytail
/ponytail-review
/ponytail-audit
/ponytail-debt
/ponytail-gain
/ponytail-help
```

Future scoped policy, only after the delivery gate passes:

- intended FULL mode for engineering Director/Architect/Developer;
- intended review/audit skills for Reviewer/QA/Security;
- retain the reviewed plugin revision in canonical `config/versions.lock`;
- verify process-global mode and Unix `HOME` defaults do not cross the intended runtime scope;
- never grant plugin lifecycle commands to untrusted Discord users

Independent work can use Station's reviewed engineering guidance without
pretending that it is Ponytail. Ponytail-dependent acceptance remains pending.

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
