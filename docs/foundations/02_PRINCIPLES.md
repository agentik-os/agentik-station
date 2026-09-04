# Canonical Principles

## P1 — Hermes first

Before building custom Agentik infrastructure, ask:

> Does Hermes already provide the primitive?

Preferred order:

```text
Hermes native
→ Hermes plugin / hook / provider
→ AGK custom service
→ Hermes fork only as last resort
```

## P2 — Architecture must prevent contamination

Never rely on an agent remembering:

> "Do not mix clients."

Instead:

> the other client's data, credentials and memory must not exist in the worker's accessible scope.

## P3 — Profiles are identity / trust boundaries

Profiles are not projects.

Use a separate profile when there is a meaningful difference in:
- credentials
- memory
- security
- durable identity
- permissions
- communication boundary

## P4 — Subagents are cognitive specialization

Use subagents for temporary specialists:
- researcher
- architect
- engineer
- QA
- critic
- reviewer
- analyst

Use profiles when the difference is a security boundary.

## P5 — Projects are workspaces

A project can contain one or multiple repos.

Map:

```text
Organization Project
→ Hermes Project
→ folders/repos
→ bound Kanban board
```

## P6 — Boards are durable execution boundaries

A board is not a chat session.

A board contains durable work:
- missions
- tasks
- dependencies
- reviews
- worker state
- workspaces

## P7 — Threads are conversations

```text
Discord server = organization cockpit
Category = macro domain
Channel = domain / OS interface
Thread = conversation surface
Hermes session = thread context
AGK Mission = durable unit of work
Hermes root Kanban task = mission execution root
```

## P8 — OSs are recursive and composable

An OS can contain other OSs.

Example:

```text
Life OS
├── Journal OS
├── Decision OS
├── Mindset OS
└── Relationship OS
```

Each child OS may be installable independently.

## P9 — Every serious domain can own a Nano Director

A Nano Director is the persistent authority for one operational subject.

It:
- understands the domain
- resolves mission intent
- plans
- decomposes work
- selects capabilities
- composes NanoTeams
- enforces policies
- verifies completion

## P10 — Linear and Kanban have different jobs

```text
Linear = human project visibility
Hermes Kanban = internal agent execution graph
```

Do not mirror every internal agent task to Linear.

## P11 — Memory, knowledge and data are different

```text
Memory Provider = machine recall
Notion = durable human-readable knowledge
Agentik Data = structured operational state
GitHub = code
Linear = human work
Hermes Kanban = execution lifecycle
Evidence = proof
Discord = interaction
```

## P12 — Credentials are scoped

Never create one global `.env` containing every client secret.

Credential resolution should consider:
- organization
- profile
- project
- environment
- capability

## P13 — Verification is part of execution

Engineering lifecycle:

```text
Plan
→ Graph
→ Worktree
→ Implement
→ Tests
→ Goal gates
→ QA
→ Security
→ Independent review
→ PR
→ CI
→ Staging
→ Live verify
→ Production
→ SRE verify
→ Evidence
```

## P14 — The VPS is not the source of truth

Source of truth:

```text
Agentik Node code
+
deployment config
+
agentik.lock
+
state backups
+
external secret source
```

## P15 — Production clients should move to dedicated Nodes

Operator can prototype multi-org on one Node.

Enterprise target:

```text
Operator Node
Example Client Node
Example Client B Node
Client A Node
...
```

## P16 — Production never blindly tracks latest

Use:
- stable
- candidate
- edge

Updates require compatibility tests and rollback.

## P17 — Every important manual server change must become code

If a command materially changes the Node and is needed after a rebuild, it belongs in:
- bootstrap
- installer
- migration
- config
- documentation

## P18 — Less permanent agents, more dynamic teams

Do not create 100 permanent profiles.

Prefer:
- durable Nano Directors
- optional Team Directors
- dynamic NanoAgents / subagents

## P19 — One universal metamodel, custom organizations

Agentik standardizes:
- hierarchy mechanics
- execution
- permissions
- memory
- evidence

Agentik does not dictate:
- client departments
- client processes
- client domain names

## P20 — Rebuildability is a product feature

A Node is not production-ready until disaster recovery has been tested.

## P21 — Discord is compiled desired state

Do not make manual Discord structure the source of truth.

```text
Organization + installed OS manifests
→ Discord compiler
→ roles/categories/channels/permissions/bindings
```

## P22 — Bootstrap privilege is temporary

The Discord bootstrap identity may receive Administrator during an approved initial provisioning window when narrower permissions are insufficient. The human server owner must remove that elevation after reconciliation; Station reads back the change and verifies least-privilege runtime permissions before acceptance.

## P23 — Provisioning is idempotent and non-destructive by default

Repeated bootstrap/apply operations must converge on desired state without duplicating channels/roles. Existing resources are adopted or preserved unless an explicit migration/deletion policy authorizes change.

## P24 — Bind by immutable IDs, not names

Human-readable names can change. Runtime routing must use Discord guild/category/channel/thread/role IDs stored in a binding registry.

## P25 — OS packages declare interaction surfaces

An OS that wants Discord exposure declares the surfaces it needs. The Discord Provisioner composes all installed OS declarations into one coherent server.

## P26 — Ponytail is canonical for engineering, not the kernel

DevOps/Builder/Engineering OSs install Ponytail as a Hermes plugin and use it in implementation/review. Agentik Kernel remains functional without it.

## P27 — Installation ends at OPERATIONAL, not package-installed

A production Node is not considered installed merely because services are running. It must pass bootstrap, routing, security downgrade, doctor and E2E.

## Engineering Harness principles (v6)

- Use Hermes primitives before adding Agentik runtime services.
- Models are replaceable; contracts, tools, graph state and evidence are canonical.
- No code completion without fresh verification evidence.
- The implementer is not the final judge.
- Parallel writers require isolated worktrees.
- Complex missions are bounded graphs, not endless prompts.
- Learning is continuous; promotion is governed.
- Raw runtime logs belong to Hermes; normalized proof belongs to AGK Evidence.


## Builder OS is mandatory

Every new OS and every material OS upgrade is produced through Builder OS. The locked 2026-08-31 OS Contract is an invariant. Builder compiles AGK intent onto Hermes-native primitives and must not create duplicate runtime engines when Hermes already supplies the capability.

## Dedicated OS bot rule

Every canonical OS has a dedicated Discord bot and dedicated channel. That bot is the Nano Director Hermes profile. Internal specialist profiles normally remain internal and do not require Discord applications.


## Orchestration intelligence

Station optimizes for leverage and truth, not activity theater. Plans expose intended work; observations expose running work; executor reports expose claims; verification and readback expose proof. Capability availability, source freshness, render quality, memory promotion and trust boundaries are first-class gates.
