## 11.12 — AGK-TUI integration

- Vendored AGK-TUI at `components/agk-tui` (pin in `config/versions.lock`).
- Bootstrap installs AGK-TUI for `agk-station` (`--skip-agk-tui` to skip).
- Commands: `agk` and `station tui` for live Hermes/Codex/Claude/terminal sessions.
- `scripts/station_agk_sync.py` writes `~/.agentik/station-sync.json` and best-effort reconcile.

# Agentik Station v11

**Product release:** `11.12`  
**Release posture:** final repository candidate  
**Maximum verified base-install claim:** `READY_FOR_SETUP`

v11 is the professional audit-response release. It keeps the complete Station, Hermes, Operative System, Builder, Librarian, Discord, Composio, engineering, orchestration, and Fleet design knowledge, while replacing the unsafe prototype installer with a typed and evidence-driven Station Kernel.

## 1. Canonical architecture

```text
Station
├── Hosts
├── Control Plane
├── Zones
│   ├── 1_SYSTEM
│   ├── 2_PRIVATE
│   ├── 3_AGENTIK
│   ├── 4_ORGANIZATIONS
│   ├── 5_PROJECTS
│   ├── 6_FACTORY
│   └── 7_LAB
├── Projects
├── Operative Systems
├── Workspaces
└── Fleet
```

Local and remote environments use the same Zone and Project contracts. Host placement changes; project architecture does not.

## 2. Safe Station Kernel

v11 implements:

- strict normalized identifiers before any privileged path, username, filename, or remote operation is built;
- typed `InstallSpec` input with strict JSON parsing and unknown-field rejection;
- one deterministic desired-state compiler for local plan, local apply, and remote bootstrap;
- descriptor-based filesystem traversal with explicit Station-root confinement;
- symlink and special-file refusal on privileged managed paths;
- atomic file replacement and immutable release activation;
- operation locking, receipts, exact step state, failure evidence, and best-effort filesystem rollback;
- exact Unix user/group/home/primary-group contracts for Station and every Zone;
- correct Zone and Project ownership;
- independent Zone runtime state, `HERMES_HOME`, logs, run state, and backup staging roots;
- exact Doctor validation of Zone/Project paths before filesystem traversal;
- strict desired OS records that cannot claim runtime installation;
- safe remote transport using a normalized release archive and a separate validated JSON specification;
- strict SSH host-key checking by default;
- no reconstructed shell commands for untrusted values;
- no unattended external installer execution in the privileged kernel.

## 3. Evidence before claims

The repository distinguishes:

```text
SPECIFIED
→ SCAFFOLDED
→ INSTALLABLE
→ CONFIGURED
→ VERIFIED
→ OPERATIONAL
```

Mission evidence remains:

```text
PREPARED
→ OBSERVED
→ REPORTED
→ VERIFIED
→ READ_BACK
→ ACCEPTED
```

A copied package is not an installed OS. A binary is not a configured connector. An executor report is not verification. A command is not external readback.

## 4. Honest module state

The base installer currently configures only:

- Station Kernel;
- Host Linux foundation;
- Zone and Project layouts;
- immutable Station release;
- desired state, observed state, receipts, and Doctor.

It does not claim that the following are operational:

- Hermes profile/distribution compiler;
- dedicated Discord OS bot transport and Components V2 interactions;
- Composio principals, connected accounts, sessions, MCP, or triggers;
- rootless per-Zone workload services;
- complete AGK OS v2 runtime installation;
- Station Node Agent and continuous Fleet reconciliation;
- encrypted off-Host backup and destructive restore acceptance.

## 5. Preserved system knowledge

The repository keeps the complete design work for:

- Hermes as the Station execution kernel;
- Bot Mode, profiles, Kanban, delegation, worktrees, cron, hooks, logs, and self-improvement governance;
- AGK Operative System v2;
- Builder OS and Librarian multi-source research;
- Ponytail and the DevOps engineering constitution;
- Plan First, Loop-Graph, Gauntlet, Verification Engineering, parallel agents, subagent contracts, and model-agnostic execution;
- Discord Mission Progress Cards and polished interaction design;
- Composio as a bounded connected-capability adapter;
- local organization/project development and remote production Hosts;
- Station update rings and Hermes compatibility tracking;
- recovery, Doctor, evidence, and fresh-session acceptance contracts.

Historical v9 material is retained as provenance and is explicitly non-canonical.

## 6. Release gate

v11 may be distributed as a private alpha repository and exercised in a disposable supported VPS. It must not be called production-ready until the external acceptance sequence succeeds:

```text
fresh supported VPS
→ clone
→ repository Doctor
→ plan
→ apply
→ reboot
→ installed Doctor
→ external setup
→ Hermes/Discord/Composio readback
→ first mission
→ backup
→ destroy
→ restore
→ fresh-session acceptance
```

## 11.12 — global/team bootstrap

- added dedicated `agk-station` sudo account bootstrap;
- added clean per-user Hermes/Codex installation and root-home refusal;
- renamed CLIENTS category to ORGANIZATIONS;
- added `full` and `team` bootstrap modes;
- added Organization member-scope contract and CLI;
- added `4_ORGANIZATIONS` filesystem category;
- kept local/remote placement host-independent.
