# Canonical Agentik Station Architecture

## 1. Architectural objective

Station must host and control private work, Agentik development, OS creation, personal projects, local client development, and remote client/project production without mixing filesystem access, identities, credentials, memory, connected accounts, or runtime evidence.

The architecture combines:

- **Universal Zones**: every operational boundary follows the same contract;
- **Control Plane + Workers**: Control declares and observes; isolated Zones execute;
- **Host-independent placement**: the same Zone can be local or remote without changing its internal structure;
- **Hermes-first execution**: Station governs and compiles; Hermes runs profiles, Bots, sessions, Kanban, delegation, Skills, tools, cron, worktrees, memory, logs, and learning;
- **evidence before claims**: maturity and runtime readiness are distinct and observable.

## 2. Top-level system

```text
Agentik product / UI / marketplace
                │
                ▼
AGK contracts and governance
                │
                ▼
Station Control Plane
├── desired state
├── Host / Zone / Project / OS registries
├── policy and capability contracts
├── bindings and placement
├── release/update metadata
├── evidence indexes
└── Fleet operations
                │
                ▼
Hosts
├── Gareth core Host
├── client production Hosts
├── personal project Hosts
└── laboratory/worker Hosts
                │
                ▼
Zones
├── isolated Unix identity
├── isolated Hermes/runtime state
├── Projects
├── desired/installed OS instances
├── integrations and credential references
├── evidence
└── operations/recovery
```

## 3. Seven primitives

| Primitive | Contract |
|---|---|
| Station | complete governed environment across one or more Hosts |
| Host | one Linux machine/VPS with one Station Kernel |
| Control Plane | canonical desired state, policy, registry, placement, receipts, evidence index |
| Zone | isolated operational boundary placed on a Host |
| Project | complete project-owned human assets and runtime references inside a Zone |
| Operative System | versioned governed operational capability executed through Hermes |
| Workspace | temporary mission execution boundary, worktree, sandbox, or scratch space |

## 4. Host-independent placement

Placement does not alter identity or structure.

```text
Organization: Moonbase
├── moonbase-dev
│   ├── category: CLIENTS
│   ├── environment: development
│   └── host: gareth-core-01
├── moonbase-staging
│   └── host: moonbase-staging-01 (optional)
└── moonbase-prod
    ├── category: CLIENTS
    ├── environment: production
    └── host: moonbase-prod-01
```

A local client is not stored under a special `LOCAL_CLIENTS` tree. A remote project is not stored under a special `REMOTE_PROJECTS` tree. Host placement belongs in desired state.

## 5. Host roles

### Core Host

Runs the base System Zones plus Gareth private, Agentik development, OS Factory, LAB, and selected local client/project Zones.

### Client Host

Runs only the base System Zones and explicitly requested client Zones. It does not install Gareth Private, Agentik Development, Factory, or unrelated clients.

### Project Host

Runs only the base System Zones and explicitly requested personal Project Zones.

### Lab Host

Runs System Zones and experimental LAB Zones with no production credentials.

### Worker Host

Runs the minimum system control/worker Zones required for future Fleet execution.

## 6. Linux/FHS foundation

```text
/etc/station/
├── station.json
├── station.yaml
├── hosts.d/
├── zones.d/
├── policies.d/
└── bindings.d/

/opt/station/
├── releases/<version>/       immutable repository release
├── current -> releases/<version>
└── .staging/<operation>/

/srv/station/
├── README.md
├── 1_CONTROL/                generated human projection
├── 2_ZONES/
│   ├── 1_SYSTEM/
│   ├── 2_PRIVATE/
│   ├── 3_AGENTIK/
│   ├── 4_CLIENTS/
│   ├── 5_PROJECTS/
│   ├── 6_FACTORY/
│   └── 7_LAB/
├── 3_SHARED/
└── 4_ARCHIVE/

/var/lib/station/
├── system/
├── receipts/
├── observed/
├── registry/
├── doctor/
└── zones/<zone-id>/
    ├── home/
    ├── hermes/
    ├── mission-state/
    ├── databases/
    ├── connector-state/
    ├── caches/
    └── projects/

/var/log/station/
├── system/
└── zones/<zone-id>/

/var/backups/station/zones/<zone-id>/
/run/station/zones/<zone-id>/
```

### Source-of-truth rule

- `/etc/station`: desired state and approved policy;
- `/var/lib/station`: observed state and durable machine/runtime state;
- `/srv/station/1_CONTROL`: generated navigation projection only;
- `/opt/station/releases`: immutable software history;
- no secret may be copied into the Control projection.

## 7. Zone contract

```text
ZONE =
  identity
+ owner and organization
+ environment
+ Host placement
+ dedicated Unix user/group
+ dedicated human root
+ dedicated runtime state root
+ dedicated HERMES_HOME
+ dedicated log/run/backup staging roots
+ Projects
+ desired OS instances
+ integrations
+ credential references/material under exact scope
+ evidence and operations
+ network/capability policy
+ Doctor and recovery contract
```

Human Zone layout:

```text
<zone>/
├── ZONE.json
├── ZONE.yaml
├── README.md
├── projects/
├── os/
├── integrations/
├── credentials/
├── evidence/
└── ops/
```

High-churn runtime state never pollutes the human Project tree; it belongs in `/var/lib/station/zones/<zone-id>`.

## 8. Project contract

```text
projects/<project-id>/
├── PROJECT.json
├── PROJECT.yaml
├── README.md
├── repos/
├── docs/
├── knowledge/
├── integrations/
├── credentials/
├── workspaces/
├── worktrees/
├── state/
├── artifacts/
├── evidence/
└── ops/
```

Rules:

- every repo belongs under `repos/`;
- parallel code agents use `worktrees/` or an explicitly declared sandbox;
- credential plaintext is never committed to Git;
- credential references and encrypted material remain Project/Zone-scoped;
- runtime databases/cache are mapped to the Zone runtime state root;
- no Project work under `/root`, random `/home` paths, `/tmp`, or `/var/www`.

## 9. Control and execution separation

```text
Control Plane
    │ declares desired state
    │ resolves Host + Zone + Project + OS + profile + environment
    │ issues explicit operation
    ▼
System/Worker Zone
    │ executes constrained reconciliation
    ▼
Target Zone
    │ owns runtime, Project, credentials, memory, evidence
    ▼
Observed state + receipt + Doctor
```

Control never mounts every remote filesystem and never imports all remote secrets. Remote operations exchange typed desired state and receipts.

## 10. Operative System runtime mapping

```text
AGK OS abstraction                Hermes implementation
────────────────────────────────────────────────────────
Nano Director                     persistent Profile / Bot
NanoTeam persistent specialist    Profile / Bot
Durable work                      Kanban root task + DAG
Temporary specialist              delegate_task
Conversation                      session
Ordered competence                Skills + AGK ordering contract
Automation                        cron (disabled until acceptance)
Capabilities                      native tools / plugins / MCP / Composio / APIs
Parallel coding                   worker profiles + worktrees
Logs                              Hermes logs/events
Learning                          Hermes learning + AGK promotion governance
```

The v11 Kernel declares desired OS packages but does not falsely install them. A future Hermes compiler must create profiles/distributions, boards, plugins, gateways, capability bindings, and acceptance evidence before changing runtime state.

## 11. Credentials and connected accounts

Credential boundaries are structural:

```text
Station Host credential
Zone credential
Project credential
OS/Profile capability grant
Mission-scoped delivery
```

- no global cross-organization `.env`;
- no development access to production credentials by default;
- systemd credential delivery or provider-managed authentication is preferred;
- Composio principal IDs map to stable Station principals and explicit Zone/organization/account scopes;
- Control stores references/readiness metadata, not copies of every token;
- unresolved principal, organization, environment, or account blocks sensitive execution.

## 12. Remote Fleet direction

v11 includes a hardened **bootstrap transport**, not a completed Fleet Control Plane:

```text
local trusted repo
    ↓ normalized release.tar + validated InstallSpec JSON
strict SSH/SCP argv transport
    ↓
remote private staging directory
    ↓
remote Station reconciler
    ↓
reported status
```

It does not yet claim drift reconciliation, Node Agent attestation, remote rollback, or accepted readback. Those require the future Station Node Agent and operation receipts ingested by Control.

## 13. Release and update model

```text
repository candidate
→ repository Doctor
→ security/contract tests
→ temp-root integration install
→ immutable release
→ LAB / Hermes edge
→ compatibility and recovery gates
→ candidate Host
→ stable
→ controlled Fleet rollout
```

Hermes upstream changes are checked and planned, never blindly applied to stable/client Hosts. Station Maintainer must classify each change as native replacement, native extension, schema change, behavior change, security change, or no action.

## 14. Mission orchestration

Every non-trivial mission follows:

```text
Clarify
→ explicit objective/constraints/acceptance
→ capability readiness probe
→ leverage scan
→ Plan First
→ owner-visible Loop-Graph
→ observed execution
→ executor report
→ independent verification
→ external readback/render inspection
→ acceptance
→ memory review
→ next operational action
```

Discord projects this semantic state through one editable Mission Progress Card. Raw tool/reasoning telemetry belongs in logs/evidence, not the human-facing channel.

## 15. Security invariants

- strict validated IDs before paths, usernames, filenames, and remote operations;
- no symlink following in privileged managed paths;
- no reconstructed shell command for untrusted values;
- one Unix identity and runtime namespace per Zone;
- cross-Zone filesystem, credentials, and memory denied by default;
- no client raw data in Factory;
- LAB has no production tokens;
- privileged actions require explicit authorization outside model output;
- failed reconciliation records `DEGRADED` and a next repair action;
- present binary/config file never raises a module to operational readiness;
- backup is not trusted until a destructive restore rehearsal passes.
