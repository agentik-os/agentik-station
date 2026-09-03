# Agentik Station v11

Agentik Station is the Linux control plane and isolated execution foundation for Gareth's private systems, Agentik development, OS Factory, personal agentic projects, client development environments, and remote client/project Hosts.

**Release:** `0.2.0-alpha.11`  
**Posture:** safe-kernel alpha  
**Current verified claim:** the repository can compile a typed plan and reconcile the Station Linux foundation, immutable release, Zones, Projects, desired OS declarations, receipts, and Doctor state to `READY_FOR_SETUP` on the supported Ubuntu/Debian provider. It does **not** claim that Hermes, Discord, Composio, remote Fleet reconciliation, encrypted off-Host backup, or any OS package is already operational.

## One-repository direction

The target workflow is intentionally simple:

```text
Fresh Ubuntu/Debian VPS
    ↓
install a trusted coding agent
    ↓
git clone agentik-station
    ↓
agent reads AGENTS.md and the architecture/security contracts
    ↓
./station doctor --repo
    ↓
./station plan
    ↓
sudo ./install
    ↓
Linux foundation + Station safe kernel
    ↓
READY_FOR_SETUP
    ↓
operator-controlled external enrollment and acceptance gates
    ↓
OPERATIONAL
```

The repository is therefore both:

1. the canonical architecture and policy source;
2. the executable desired state for the supported Station Kernel;
3. the source used to build immutable Station releases;
4. the future compiler for Hermes profiles, OS packages, Discord surfaces, Composio bindings, and Fleet operations.

## Canonical model

```text
STATION
├── HOSTS
├── CONTROL PLANE
├── ZONES
├── PROJECTS
├── OPERATIVE SYSTEMS
├── WORKSPACES
└── FLEET
```

- **Host**: a Linux machine or VPS.
- **Control Plane**: desired state, policies, registries, bindings, release metadata, and evidence indexes.
- **Zone**: the canonical isolation and operational boundary placed on a Host.
- **Project**: all source, knowledge, integrations, credential references, state references, workspaces, artifacts, evidence, and operations for one product/client project.
- **Operative System**: a governed installable operational capability executed by Hermes.
- **Workspace**: a temporary mission environment such as a worktree or sandbox.
- **Fleet**: all Hosts and their Zone placements, controlled through explicit desired state and observed evidence.

Local and remote are placement decisions, never different project architectures:

```text
moonbase-dev   → host: gareth-core-01
moonbase-prod  → host: moonbase-prod-01
verba-dev      → host: gareth-core-01
verba-prod     → host: verba-prod-01
```

## Clean Linux layout

```text
/etc/station               canonical desired state and policies
/opt/station/releases      immutable Station releases
/opt/station/current       atomic active-release pointer
/srv/station               human-operational navigation and Zone assets
/var/lib/station           observed state, receipts, Hermes/runtime databases
/var/log/station           Station and per-Zone logs
/var/backups/station       local backup staging only
/run/station               ephemeral runtime state and locks
```

Human navigation stays small:

```text
/srv/station/
├── 1_CONTROL/             generated projection; never source of truth
├── 2_ZONES/
│   ├── 1_SYSTEM/
│   ├── 2_PRIVATE/
│   ├── 3_AGENTIK/
│   ├── 4_CLIENTS/
│   ├── 5_PROJECTS/
│   ├── 6_FACTORY/
│   └── 7_LAB/
├── 3_SHARED/              non-secret, read-only distributions/assets
└── 4_ARCHIVE/
```

## Safe-kernel guarantees in v11

- strict ASCII identifier validation before path or command construction;
- resolved paths confined to explicit Station roots;
- descriptor-based traversal and symlink refusal for privileged writes;
- atomic managed-file replacement;
- immutable versioned releases with an atomic `current` pointer;
- argument-array subprocess execution rather than reconstructed shell commands;
- remote bootstrap receives desired state as a validated JSON `InstallSpec`;
- strict SSH host-key checking by default;
- exact Zone Unix identity, group, home, state root, and ownership contracts;
- correct Project ownership under the parent Zone identity;
- no global `HERMES_HOME`, global cross-organization `.env`, or shared credential namespace;
- desired OS packages are declared as `NOT_INSTALLED` until a real runtime compiler and acceptance evidence exist;
- explicit module maturity and next repair actions;
- operation receipts and a `DEGRADED` state on failed reconciliation;
- repository and installed-Host Doctor checks;
- installed Doctor reconstructs Zone/Project roots and identities before inspecting their filesystems;
- the release manifest must match the exact packaged file inventory and verified claim;
- no unattended external network installer executed by the safe kernel.

## Evidence before claims

Station uses a strict evidence ladder:

```text
PREPARED
→ OBSERVED
→ REPORTED
→ VERIFIED
→ READ_BACK
→ ACCEPTED
```

Examples:

- a plan is not execution;
- an executor report is not verification;
- a copied OS package is not an installed OS;
- a present binary is not a configured connector;
- a deployment command is not successful readback;
- a cron definition is not enabled until fresh-session acceptance passes.

## Commands

```bash
./station doctor --repo
./station plan --host-id gareth-core-01 --role core
sudo ./install --host-id gareth-core-01 --role core
station doctor --full
station status
station module status
station provider status
```

A client Host example:

```bash
./station plan \
  --host-id moonbase-prod-01 \
  --role client \
  --seed-category CLIENTS \
  --seed-name moonbase \
  --seed-env production \
  --seed-organization moonbase \
  --seed-project platform
```

Read [`INSTALL.md`](INSTALL.md) before applying and [`SETUP.md`](SETUP.md) before enrolling external accounts or credentials.

## Current module truth

| Module | Design maturity | Runtime claim after base install |
|---|---|---|
| Station Kernel | INSTALLABLE | CONFIGURED after Doctor |
| Host foundation | INSTALLABLE | CONFIGURED after Doctor |
| Zone runtime layout | INSTALLABLE | CONFIGURED after Doctor |
| Hermes runtime/compiler | SCAFFOLDED | not configured |
| Discord Experience | SCAFFOLDED | not configured |
| Composio plane | SPECIFIED | not configured |
| Rootless per-Zone runtime | SPECIFIED | not configured |
| OS Factory | SCAFFOLDED | not configured |
| Fleet Control | SCAFFOLDED transport | not verified/accepted |
| Backup/recovery | SPECIFIED | not configured |

See [`modules/catalog.json`](modules/catalog.json) for machine-readable claims and next repair actions.

## Documentation map

- [`ARCHITECTURE.md`](ARCHITECTURE.md): complete final architecture.
- [`INSTALL.md`](INSTALL.md): typed plan/apply and Host-role workflows.
- [`SETUP.md`](SETUP.md): external enrollment and acceptance gates.
- [`SECURITY.md`](SECURITY.md): threat model and hardening rules.
- [`AGENTS.md`](AGENTS.md): mandatory behavior for coding agents.
- [`docs/hardening/`](docs/hardening/): v11 audit response and safe reconciler design.
- [`docs/history/v9/`](docs/history/v9/): preserved design provenance, never current runtime truth.
- [`docs/audit/`](docs/audit/): professional v10 audit and evidence bundle that drove v11.
