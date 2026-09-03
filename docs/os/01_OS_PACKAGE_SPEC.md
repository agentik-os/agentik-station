# Operative System Package Specification v2

The package is the immutable definition of an OS. Live credentials, memory, connected accounts, sessions, logs and writable workspaces do not belong in it.

```text
os-name/
├── OS.yaml
├── MANIFEST.json
├── CONTRACT.json
├── README.md
│
├── 01_MASTER/                 # mission, outcomes, operating charter
├── 02_DIRECTOR/               # Nano Director profile/distribution intent
├── 03_NANOTEAM/               # persistent Bots, workers, ephemeral roles
├── 04_PROFILES/               # Hermes profile/distribution descriptors
├── 05_SKILLS/                 # ordered skill graph and skills
├── 06_PROGRAMS/               # deterministic programs / no-agent jobs
├── 07_CAPABILITIES/           # abstract capabilities + approvals
├── 08_INTEGRATIONS/           # Hermes/MCP/Composio/API adapter bindings
├── 09_KNOWLEDGE/              # canonical domain knowledge declarations
├── 10_MEMORY/                 # hot/long-term memory scope policy
├── 11_DATA/                   # schema, state/event model, migrations
├── 12_MISSIONS/               # mission types, SLAs, acceptance criteria
├── 13_WORKFLOWS/              # workflows + Loop-Graphs/Kanban semantics
├── 14_AUTOMATIONS/            # cron/webhook/Composio triggers; disabled until accepted
├── 15_PROVIDER_ROUTES/        # model-agnostic roles/fallback/budget policy
├── 16_HARNESS/                # engineering harness when applicable
├── 17_EVALS/                  # functional/quality/safety/regression evals
├── 18_EVIDENCE/               # evidence requirements and event mapping
├── 19_DISCORD/                # dedicated bot/channel/commands/how-to pin
├── 20_VIEWS/                  # Agentik/dashboard/graph/domain views
├── 21_DOCTOR/                 # deterministic health/contract checks
├── 22_UPDATE_MIGRATIONS/      # compatibility + migration lifecycle
├── 23_ROLLBACK/               # previous-known-good activation
├── 24_RECOVERY/               # recovery artifact + restore runbook
├── 25_GOVERNANCE/             # trust zones, permissions, approvals, budgets
├── 26_SELF_IMPROVEMENT/       # learning candidate -> promotion policy
├── 27_LIBRARIAN/              # sources + 15 inputs + Builder handoff
└── 28_DEPLOYMENT/              # install/upgrade/uninstall/fresh-session gates
```

## OS.yaml minimum intent

```yaml
schema_version: "2.0"
id: agk.devops
name: DevOps OS
version: 2.0.0

outcome:
  owns: software_delivery
  mission_types: [feature, fix, refactor, release, incident]

director:
  profile: devops-director
  persistent_bot: true
  discord_identity: dedicated

team:
  persistent_profiles: [architect, forge, sentinel]
  kanban_workers: [coder, qa, reviewer]
  ephemeral_roles: [researcher, code-explorer]

skills:
  graph: 05_SKILLS/skill-graph.yaml

execution:
  durable_missions: kanban
  parallel_writers: isolated_worktrees
  temporary_help: delegate_task

capabilities:
  contract: 07_CAPABILITIES/capabilities.yaml

integrations:
  adapters: 08_INTEGRATIONS/adapters.yaml

knowledge_memory:
  policy: scoped

data:
  schema: 11_DATA/schema.json
  state_model: 11_DATA/state-machine.yaml

views:
  registry: 20_VIEWS/views.yaml

verification:
  evals: required
  evidence: required
  gauntlet: risk_based

discord:
  dedicated_bot: true
  dedicated_primary_channel: true
  commands: 19_DISCORD/commands.yaml

lifecycle:
  doctor: required
  migration_contract: required
  rollback: required
  recovery: required
  fresh_session_acceptance: required
```

## Adapter selection rule

Builder selects the least-complex safe adapter that satisfies the capability:

```text
1. deterministic local program
2. Hermes native tool/toolset
3. Hermes plugin / MCP
4. Composio session adapter
5. explicit direct API adapter
```

This is a design heuristic, not a blind priority. Compliance, latency, data locality, account ownership and product constraints may select another declared adapter.

## Runtime ownership

Distribution-owned files can be versioned and replaced. User/runtime-owned data such as memories, sessions, auth, logs and workspaces remain outside the immutable package and must survive upgrades according to the lifecycle contract.
