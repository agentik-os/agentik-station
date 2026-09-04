# Agentik Station 11.12

Agentik Station is the Linux control plane and isolated execution foundation for Operator's private systems, Agentik development, OS Factory, personal agentic projects, organization development environments, and remote organization/project Hosts.

**Release:** `11.12`  
**Posture:** final repository candidate  
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


## One-command host bootstrap

For a fresh supported Ubuntu/Debian VPS, clone the repository once, then run:

```bash
sudo ./bootstrap.sh --mode full
```

For a company/team installation:

```bash
sudo ./bootstrap.sh --mode team --organization organization-alpha --project platform
```

The bootstrap creates the dedicated sudo account `agk-station`, relocates the working checkout to `/home/agk-station/repos/agentik-station`, installs host dependencies, installs Hermes and Codex under that account, and invokes the same typed Station plan/apply workflow. It deliberately keeps source and user tooling out of `/root`. External authentication remains an explicit setup gate.

`full` maps to the complete Agentik Station (operator Host). `team` is the company install: shared System foundation + one Organization Zone; Discord/Composio/memory/credentials are member-scoped principals so several people share the Host without a single global Private Zone. There is no separate client-branded mode — pass your organization/project ids at bootstrap time.

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
organization-alpha-dev   → host: station-core-01
organization-alpha-prod  → host: organization-alpha-prod-01
example-project-dev      → host: station-core-01
example-project-prod     → host: example-project-prod-01
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
│   ├── 4_ORGANIZATIONS/
│   ├── 5_PROJECTS/
│   ├── 6_FACTORY/
│   └── 7_LAB/
├── 3_SHARED/              non-secret, read-only distributions/assets
└── 4_ARCHIVE/
```

## Station 11.12 verified foundation

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
- desired OS packages remain `NOT_INSTALLED` until explicitly installed; Station 11.12 includes the OS→Hermes Profile Distribution compiler, while live runtime acceptance remains evidence-gated;
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
./station plan --host-id station-core-01 --role core
sudo ./install --host-id station-core-01 --role core
station doctor --full
station status
station module status
station provider status
```

A team Host example:

```bash
./station plan \
  --host-id organization-alpha-prod-01 \
  --role team \
  --seed-category ORGANIZATIONS \
  --seed-name organization-alpha \
  --seed-env production \
  --seed-organization organization-alpha \
  --seed-project platform
```

Read [`INSTALL.md`](INSTALL.md) before applying and [`SETUP.md`](SETUP.md) before enrolling external accounts or credentials.

## Current module truth

| Module | Repository maturity | External acceptance |
|---|---|---|
| Station Kernel | VERIFIED | base Host readback still required on a fresh VPS |
| Host foundation | VERIFIED | reboot/system-service gate required on real Host |
| Zone runtime | VERIFIED | rootless negative-isolation runtime gate pending |
| Hermes runtime/compiler | INSTALLABLE | profile/gateway/plugin/fresh-session gate pending |
| Discord Experience | INSTALLABLE | dedicated test-guild create/edit/interactions/readback pending |
| Composio plane | INSTALLABLE | OAuth/session/MCP/trigger/revocation gate pending |
| Rootless runtime | INSTALLABLE | live Podman negative-isolation gate pending |
| OS Factory | INSTALLABLE | real Librarian→Builder→Hermes→recovery acceptance pending |
| Fleet Control | INSTALLABLE | remote disposable-Host drift/rollback gate pending |
| Backup/recovery | INSTALLABLE | off-Host backup + destructive restore rehearsal pending |
| Observability | INSTALLABLE | production alert/readback/retention gate pending |

See [`modules/catalog.json`](modules/catalog.json) for machine-readable claims and repair actions.

## Documentation map

- [`ARCHITECTURE.md`](ARCHITECTURE.md): complete final architecture.
- [`INSTALL.md`](INSTALL.md): typed plan/apply and Host-role workflows.
- [`SETUP.md`](SETUP.md): external enrollment and acceptance gates.
- [`SECURITY.md`](SECURITY.md): threat model and hardening rules.
- [`AGENTS.md`](AGENTS.md): mandatory behavior for coding agents.
- [`docs/hardening/`](docs/hardening/): 11.12 audit response and safe reconciler design.
- [`docs/history/v9/`](docs/history/v9/): preserved design provenance, never current runtime truth.
- [`docs/audit/`](docs/audit/): professional v10 audit and evidence bundle that drove the 11.x hardening program.

## One-command orchestration wrapper

For operators who want one safe entry point, the repository ships `station.sh`. It is a Bash orchestration wrapper around the typed Python Station kernel; it does **not** duplicate installer logic.

```bash
./station.sh bootstrap --host-id station-core-01 --role core
```

The wrapper performs, in order:

```text
Repository Doctor
→ create one validated InstallSpec
→ Plan • not run
→ explicit confirmation (or --yes in controlled automation)
→ sudo apply using the exact same InstallSpec
→ full recorded Host Doctor
→ status
→ remaining external setup gates
```

Generic client and project examples use only `organization-alpha` and `example-project`. No real client or personal project identity belongs in the canonical repository.

## AGK-TUI (live sessions)

After bootstrap, open Hermes / Codex / Claude Code / terminal sessions with `agk` or `station tui`.
Vendored at `components/agk-tui` (pin in `config/versions.lock`). See `INTEGRATION_AGK_TUI.md`.


## Hermes platforms + optional deps

- Update Hermes: `./scripts/station_hermes_update.sh update` (pin in `config/versions.lock`)
- Weekly auto-update (opt-in): `sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update`
- Multi-platform bots: `hermes gateway setup` then `hermes gateway start`
- Optional stack (Langfuse, Honcho, Hindsight, Ponytail, Crawl4AI, TigerVNC): `docs/dependencies/STACK.md`
