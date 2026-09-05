# Mandatory Agent Contract — Agentik Station

This repository is executable infrastructure. Architecture and security contracts are constraints, not suggestions.

Read and obey the canonical cross-provider rules in `rules/STATION_AGENT_RULES.md`. This file adds repository-specific constraints; where they overlap, apply the stricter rule.

## Source-of-truth order

1. `AGENTS.md`, `ARCHITECTURE.md`, `SECURITY.md`, `INSTALL.md`, `SETUP.md`;
2. current `docs/` sections excluding `docs/history/`;
3. typed `src/`, `config/`, `contracts/`, `specs/`, `runtime/`, `os/`, `modules/`, and tests;
4. `docs/history/` and `docs/history/` are provenance only and never current runtime truth.

## Mandatory mission protocol

For non-trivial work:

1. clarify objective, scope, constraints, assumptions, risks, and acceptance criteria;
2. probe real tool/connector/executor availability before depending on it;
3. create a Plan First mission graph before mutation;
4. use leverage in this order: existing code → Hermes native → platform/stdlib → installed dependency → MCP/Composio/API → smallest justified new implementation;
5. expose one owner and one verification owner for each parallel branch;
6. isolate mutable coding work in the owning Project worktree/workspace;
7. distinguish `prepared`, `observed`, `reported`, `verified`, `read_back`, and `accepted`;
8. run tests, Doctor, review, render inspection, CI, or external readback appropriate to the claim;
9. preserve evidence and provide the next repair action for any degraded state.

## Hard architecture invariants

- Station = Hosts + Control Plane + Zones + Projects + Operative Systems + Workspaces + Fleet.
- **Zone** is the only canonical operational/isolation boundary term.
- Runtime categories are `1_SYSTEM`, `2_PRIVATE`, `3_AGENTIK`, `4_ORGANIZATIONS`, `5_PROJECTS`, `6_FACTORY`, `7_LAB`.
- Do not append redundant `-zone`, `-client`, or `-project` suffixes when the parent already carries the category.
- Local/remote is Host placement, not a separate tree.
- Every Zone has an independent Unix identity, HERMES_HOME, state, log, credential, memory, and evidence namespace.
- A client Organization owns its environment Zones. Client-owned OS instances and Projects are siblings inside a Zone; a Project is not the container of the Organization or its OS.
- A reusable OS package is an immutable domain definition. An OS instance owns its configured domain runtime, workspace and evidence; Projects own bounded bodies of work. An instance may declare existing allowed Projects, but needs none for OS-owned work.
- Instance-specific Hermes homes and namespaced Director/team profiles avoid runtime/service collisions, but share the Zone Unix identity. An allowed-Project list is a routing/policy contract, not a filesystem sandbox.
- Instance gateways retain the canonical Zone `HOME`; other CLI authentication and caches there may be shared even though Hermes profiles/configuration/sessions use distinct `HERMES_HOME` roots. Never imply per-instance CLI/account isolation or copy authentication automatically.
- Every Project owns its repos, docs, knowledge, integrations, credentials, workspaces, worktrees, state references, artifacts, evidence, and operations.
- Control holds desired state/metadata and evidence indexes, not every Zone's secret material.
- Factory uses synthetic/sanitized fixtures and never consumes client raw data by default.
- Development does not receive production credentials by default.
- No project work under `/root`, random home directories, `/tmp`, `/var/www`, or arbitrary Docker volumes.

## Privileged-code rules

- validate identifiers before paths or commands;
- use `SafeFS` for Station-managed privileged paths;
- reject symlinks/special files;
- use atomic writes;
- use argv arrays, never reconstructed shell commands;
- remote desired state travels as validated JSON;
- do not add a network-installer pipeline to root execution;
- do not weaken Doctor to make a build green;
- add an adversarial regression test for every fixed security bug.

## Maturity and claims

A design/package and a live runtime are different.

```text
SPECIFIED → SCAFFOLDED → INSTALLABLE → CONFIGURED → VERIFIED → OPERATIONAL
```

`DEGRADED` is reserved for a failing previously configured/operational module and requires a repair action.

Never write `installed.yaml` merely because files were copied. Desired declarations
remain `NOT_INSTALLED`; only the trusted runtime ledger plus complete native team
readback can establish `CONFIGURED`. Full-team Doctor evidence establishes local
`VERIFIED`, not account or live mission acceptance. `OPERATIONAL` requires the
separate applicable external readback and acceptance gates.

For an existing Zone, create new Projects through `station project create`; do not
rerun Host installation or overwrite partial workspace state. Register client
ownership only against existing matching ORGANIZATIONS Zones. Prefer
`station os instance install` with explicit Zone, instance and Organization;
use `station os instance setup` and gateway `--instance` for its Director.
Legacy schema-2 Project-bound OS runtimes retain their `--os` commands and are
never automatically adopted or migrated. Never bypass ledger conflicts with
forced profile replacement or infer credentials from another instance/profile.
`station client --legacy …` is a separate shared-operator compatibility controller,
not canonical client Zone registration or instance enrollment. Preserve its data.
Bootstrap incomplete-attempt acknowledgement requires reviewed repair, not automatic retry.

## Hermes and OS rules

Hermes is the engine. Prefer native Profiles/Bot Mode, sessions, Kanban, delegation, worktrees, Skills, plugins, hooks, cron, logs, provider routes, memory providers, and learning loop.

Builder must use Librarian's multi-lane intelligence protocol: topic map, canonical books, current web research, expert/operator knowledge, source verification, contrarian/failure evidence, editorial `bestseller` synthesis, contradictions/limitations, and actionable inputs.

Each installed OS instance has one dedicated Discord Nano Director bot and primary channel by default. Specialists remain internal Hermes Profiles/Bots/workers unless a separate external identity is justified by an explicit topology. Installing profiles does not provision a guild, mint bot tokens or instantiate every domain database, view and automation in the full OS contract.

## Completion contract

A change is not complete until:

- relevant unit/security/contract/integration tests pass;
- `./station doctor --repo` passes;
- no generated caches or compiled artifacts remain in the release tree;
- documentation and machine-readable contracts agree;
- runtime claims match observed evidence;
- a limitation that was not exercised on a real external system is stated honestly.

## Canonical OS source

Canonical OS sources live only under `os/`. Generated Hermes distributions are artifacts and must not become parallel editable sources.
