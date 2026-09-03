# Decision Log

## D001 — Hermes is the kernel
Status: accepted

Do not rebuild core orchestration when Hermes already provides it.

## D002 — One session is not one client
Status: accepted

Sessions represent conversations only.

## D003 — Board is not profile
Status: accepted

Profile = identity/trust.
Project/board = work.

## D004 — Shared DevOps intelligence, isolated execution
Status: accepted

The methodology can be shared through:
- distributions
- skills
- OS packages

Client credentials/memory/state remain isolated.

## D005 — Subagent for cognition, profile for security
Status: accepted

Core identity rule.

## D006 — OS hierarchy is recursive
Status: accepted

OSs can contain OSs.

## D007 — Client organizational structure is custom
Status: accepted

Do not force Gareth's Business/Life taxonomy onto clients.

## D008 — Discord is a cockpit
Status: accepted

Channels expose OS interfaces.
Threads represent conversation/session surfaces; durable missions are Kanban-rooted.
Internal agents stay mostly invisible.

## D009 — Linear and Hermes Kanban remain separate
Status: accepted

Linear = human work.
Kanban = agent execution.

## D010 — Notion is not memory
Status: accepted

Notion = durable knowledge.
Memory Provider = machine recall.

## D011 — Client production should trend toward one Node per client
Status: accepted

Safer ownership and isolation model.

## D012 — Git should describe the desired Node
Status: accepted

The current VPS must be an instance created by code.

## D013 — Update via channels, never blind latest
Status: accepted

stable / candidate / edge.

## D014 — Voice is optional capability
Status: accepted

Parakeet and VoiceStudio are sidecars, not kernel dependencies.

## D015 — First OS to prove system = DevOps OS
Status: accepted

It exercises the most infrastructure:
- project
- board
- subagents
- worktrees
- tests
- review
- PR
- evidence

## D016 — Agentik Control should be a Hermes plugin first
Status: accepted

Avoid deep Hermes fork unless essential.

## D017 — Agentik Memory should use Memory Provider API
Status: accepted

Avoid core memory fork.

## D018 — Build manually once, automate second
Status: accepted

Do not build installer before proving full E2E manually.

## D019 — Ponytail is canonical in DevOps OS
Status: accepted

Install with Hermes plugin support and use it in implementation/review/audit. Do not make the Agentik kernel depend on it.

## D020 — Discord is generated from desired state
Status: accepted

Organization + OS manifests are the source of truth. Discord is a compiled human interface.

## D021 — Discord Bootstrap Director is privileged but temporary
Status: accepted

Bootstrap may use Administrator during initial provisioning. After successful apply + verify, remove Administrator and operate least-privilege.

## D022 — Provisioner is idempotent and non-destructive by default
Status: accepted

Plan before apply. Adopt matching existing resources. Never duplicate on rerun. Delete only with explicit migration policy.

## D023 — Runtime routing uses immutable Discord IDs
Status: accepted

Names are display values. Guild/channel/role IDs are persisted in a binding registry.

## D024 — OS packages can ship Discord surface manifests
Status: accepted

Installing an OS can automatically extend the Discord cockpit and bind its director/team/board.

## D025 — Node install state machine includes READY_UNBOUND and OPERATIONAL
Status: accepted

Services running is not equivalent to an operational organization. Discord bootstrap + doctor + E2E complete the installation lifecycle.
