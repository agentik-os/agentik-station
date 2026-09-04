# Mandatory Agent Contract — Agentik Station

This repository is executable infrastructure. Architecture and security contracts are constraints, not suggestions.

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
- Local/remote is Host placement, not a Separate tree.
- Every Zone has an independent Unix identity, HERMES_HOME, state, log, credential, memory, and evidence namespace.
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

Never write `installed.yaml` merely because files were copied. OS runtime state stays `NOT_INSTALLED` until Hermes profiles/distributions, bindings, Doctor, readback, and acceptance exist.

## Hermes and OS rules

Hermes is the engine. Prefer native Profiles/Bot Mode, sessions, Kanban, delegation, worktrees, Skills, plugins, hooks, cron, logs, provider routes, memory providers, and learning loop.

Builder must use Librarian's multi-lane intelligence protocol: topic map, canonical books, current web research, expert/operator knowledge, source verification, contrarian/failure evidence, editorial `bestseller` synthesis, contradictions/limitations, and actionable inputs.

Each installed OS has one dedicated Discord Nano Director bot and primary channel. Specialists remain internal Hermes Profiles/Bots/workers unless a separate external identity is justified.

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
