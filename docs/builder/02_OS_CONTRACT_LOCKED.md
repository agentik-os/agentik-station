# AGK OS Contract v2 — Canonical 2026-09-03

**Canonical date:** 2026-09-03  
**Meaning:** OS = **Operative System**.

An AGK OS is not a computer operating system, a prompt, an agent, a workflow, a Discord bot, or a package by itself.

> **An AGK OS is a versioned, installable, bounded autonomous operating capability that compiles real domain expertise into a governed Hermes-powered team, executes durable missions against real systems through declared capabilities, exposes state and interfaces, verifies and proves its work, learns under policy, and can be upgraded, rolled back and recovered safely.**

## Canonical equation v2

```text
OS =
  immutable package
+ outcome / mission contract
+ Nano Director
+ NanoTeam
+ persistent profiles / Bots
+ Kanban worker roles
+ ephemeral subagent roles
+ ordered skill graph
+ deterministic programs
+ capability contracts
+ integration adapters
    (Hermes native tools + MCP + Composio + direct APIs)
+ identity / auth / connected-account scopes
+ knowledge scopes
+ memory scopes
+ data schema + state/event model + migrations
+ mission model + durable execution graph
+ provider / model routes
+ workflows
+ automations + triggers
+ permissions + approvals + trust-zone constraints
+ execution isolation
    (projects + worktrees + sandboxes where appropriate)
+ engineering harness when the OS writes code or deploys
+ evaluations
+ verification engineering + Gauntlet policy
+ evidence + logs + traces
+ Discord control surface
+ plan-first Mission Progress UX + interactive Components V2/fallback
+ dedicated OS bot commands
+ views / UI
+ doctor
+ update / migration contract
+ rollback
+ recovery artifact
+ self-improvement / promotion policy
+ Librarian multi-lane intelligence (Book Deep + Bestseller synthesis + Web Deep + Expert/Topic maps) + Builder handoff + provenance
+ install / upgrade / uninstall lifecycle
```

The 2026-08-31 contract is preserved inside this contract. v2 extends it; it does not weaken or remove any prior primitive.

## Four planes of one OS

### 1. Definition Plane — immutable and versioned
Contains the OS identity, contract, NanoTeam design, profile distributions, skills, deterministic programs, capabilities, schemas, views, workflows, evals, policies, Doctor, migrations, rollback/recovery definitions and Librarian provenance.

### 2. Runtime Plane — live Hermes organization
Contains the installed Hermes profiles/Bots, sessions, Kanban boards/tasks, projects, worktrees, provider routes, Skills, plugins, MCP servers, cron jobs, hooks and runtime configuration.

### 3. Connected Capability Plane — real-world action
Binds abstract AGK capabilities to controlled adapters:

```text
AGK capability
   -> deterministic/local implementation OR
   -> Hermes native tool/toolset OR
   -> Hermes plugin/MCP OR
   -> Composio session/toolkit/tool OR
   -> explicit direct API adapter
```

The package declares intent and policy; live credentials and connected-account IDs remain outside the immutable package.

### 4. State / Evidence / Interface Plane
Contains mutable domain state, memory, mission state, evidence, logs/traces, schema-backed views, Discord surface and Agentik UI views. It proves what the OS did without turning logs or secrets into package content.

**Governance is cross-cutting across all four planes.**

## Nano Director and NanoTeam

The Nano Director is a **persistent Hermes profile/Bot** and the canonical owner of the OS outcome. Under the locked Discord rule it also has a dedicated Discord bot identity and primary channel.

NanoTeam members are classified explicitly:

```text
persistent responsibility  -> Hermes Profile / Bot
long-lived async role       -> Kanban worker profile
small temporary assistance  -> delegate_task subagent
durable work                -> Mission + Kanban root task/DAG
```

Do not turn every subagent into a persistent Bot.

## Schema + views are still essential

A complete OS is also an Agentic App. Its schema defines the durable domain objects and state transitions. Its views expose useful human-readable and machine-readable representations of that state through Discord, Agentik UI, dashboards, React Flow/graph views or domain-specific interfaces.

A view must never become the system of record when durable state belongs in the OS data layer.

## Capability contract is more important than the connector

The OS must request capabilities such as:

```text
gmail.read
gmail.send
github.pr.create
linear.issue.update
deployment.staging
crm.contact.write
```

It must not simply receive “all tools”. Builder resolves each capability to the simplest safe adapter available under Station policy.

## Composio role

Composio is a **Connected Capability Plane**, not the execution kernel.

Use it when an OS needs governed access to external SaaS accounts, broad tool discovery, managed authentication, connected accounts, event triggers, hosted MCP, or a session-scoped remote sandbox.

Station maps:

```text
AGK principal_id        -> Composio user ID
AGK capability contract -> allowed toolkits/tools
AGK connection policy   -> auth-config / connected-account references
Hermes mission/session  -> Composio session
Composio trigger        -> Station ingress -> policy -> Mission/Kanban
```

Production invariants:
- never use `default` as a Composio production user ID;
- use a stable Station principal identifier, not an email address;
- personal connected accounts never become company/client accounts by inference;
- client Nodes do not share connection namespaces;
- package files contain references and policies, never OAuth tokens or live connection secrets;
- destructive/external-write tools still pass AGK approval policy;
- tool discovery is constrained by toolkit/tool policy.

## Engineering-capable OS extension

Any OS with code-write or deployment capabilities inherits the Station Engineering Constitution:

```text
Plan First
-> understand existing system
-> Ponytail simplification ladder
-> Loop-Graph plan
-> isolated parallel workstreams when justified
-> implement
-> verify_on_stop / deterministic checks
-> independent verification
-> Gauntlet critic loop
-> integration
-> staging/live E2E
-> evidence
-> governed learning candidate
```

Hermes-native primitives are used first: delegation, Kanban, worktrees, hooks, cron, logs, provider routing and learning loop. AGK adds semantics, policy and gates rather than duplicating Hermes.

## Fresh-session acceptance

No persistent automation, trigger-driven workflow or scheduled agent is considered released until its critical path succeeds from a fresh deployed session using only declared inputs, installed Skills/tools, durable state and allowed credentials.

## What an OS is not

| Primitive | Meaning |
|---|---|
| Agent/Profile | one actor/runtime identity |
| Bot | a persistent Hermes Profile exposed as a coworker |
| Skill | reusable on-demand expertise/procedure |
| Program | deterministic executable logic |
| Workflow | one ordered operational path |
| Kanban task | durable unit of work |
| Composio session | scoped external-tool/auth execution context |
| Discord bot | one control identity/surface |
| Package | immutable definition/distribution |
| View | representation of schema-backed state |
| **OS** | complete governed composition across definition, runtime, connected capabilities and state/evidence/interface |

## Company analogy

| Company | AGK OS v2 |
|---|---|
| Charter + objectives | OS/outcome contract |
| CEO / owner | Nano Director Bot |
| Team / departments | NanoTeam / profiles / workers |
| SOPs | ordered Skills + workflows |
| Software / scripts | deterministic programs |
| SaaS accounts | scoped Composio/MCP/API adapters |
| Permissions | capability contracts + approvals |
| Institutional knowledge | knowledge + memory scopes |
| Operating cadence | missions + Kanban + automations/triggers |
| Database | schema/state/event model |
| Dashboards | views |
| QA / internal controls | evals + Verification + Gauntlet |
| Audit trail | evidence + logs/traces |
| Front desk | dedicated Discord OS bot/channel + Agentik UI |
| Health check | Doctor |
| Change management | update/migrations |
| Disaster recovery | rollback + recovery artifact |
| Training / learning | Librarian provenance + governed self-improvement |


## Discord Experience extension
Every canonical OS bot inherits Station's plan-first Discord Experience Contract. Operative work must expose one semantic Mission Progress Card, updated from durable mission/Loop-Graph state, and finish with a verified final report. Raw tool/reasoning streams are diagnostics, not the default human UI.

## Librarian Intelligence extension
The research basis is multi-lane. `/book --deep` remains mandatory, but Builder also uses current Web Deep research, Topic mapping, evidence-backed Expert/Operator mapping, and original `--bestseller` editorial synthesis. Research lanes may be skipped only with an explicit not-applicable rationale.
