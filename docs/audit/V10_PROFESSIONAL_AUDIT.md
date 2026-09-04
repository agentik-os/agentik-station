# Agentik Station — Professional Architecture, Security and Readiness Audit

**Audit date:** 2026-09-03  
**Audited artifact:** `agentik-station` v0.1.0 candidate  
**Audit posture:** CTO / Principal Platform Engineer / SRE / Security review  
**Decision:** **NO-GO for installation with root privileges on a real VPS in the current state**

---

## 1. Executive verdict

Agentik Station has a strong product and systems vision. The vocabulary — **Host, Control Plane, Zone, Project, OS, Workspace, Fleet** — is coherent. The placement-independent Zone model is particularly good: the same contract can represent a organization development Zone on Operator's core VPS and a production Zone on a remote client VPS.

However, the current repository is not yet the installable Station described by its documentation. It is best classified as:

> **an executable architecture prototype and pre-alpha bootstrap scaffold**

It is **not yet**:

> **a production-safe, one-repository, one-command installer for Hermes, OSs, Discord, Composio, Fleet, backups and recovery**

The distinction matters because the root installer currently contains two confirmed critical injection classes, multiple permission/isolation defects, and several modules that are represented as installed even though only their design files exist.

### Overall scorecard

| Area | Score | Assessment |
|---|---:|---|
| Product vision and vocabulary | 9/10 | Strong and differentiating |
| High-level Station architecture | 8/10 | Correct direction; needs a stricter source-of-truth model |
| Linux/FHS model | 7/10 | Good intent; runtime/config/state responsibilities are still mixed |
| Installer correctness | 3/10 | Useful prototype; not safe for root execution yet |
| Installer security | 1/10 | Confirmed path traversal, shell injection and symlink-follow risks |
| Zone isolation implementation | 3/10 | Identities/directories exist; ownership, runtime and service isolation are incomplete |
| Hermes integration | 2/10 | Hermes binary installation exists; real profile/runtime compilation does not |
| OS package implementation | 2/10 | Most core OS packages fail the repository's own OS Doctor |
| Discord experience | 1/10 | Design and state scaffold only; no real Discord transport or interaction layer |
| Composio integration | 1/10 | CLI installation only; no principals, bindings, sessions or readiness lifecycle |
| Fleet / remote operations | 2/10 | SSH/rsync prototype, not a reconciled control plane |
| Backup / rollback / recovery | 1/10 | Contracts and folders exist; operational mechanisms do not |
| Tests and CI | 3/10 | Existing tests pass, but they validate shape more than behavior/security |
| Production readiness | 2/10 | Pre-alpha; private development only |

---

## 2. What should be preserved

The audit does **not** recommend discarding the project. The following decisions are valuable and should become the stable foundation.

### 2.1 Canonical model

```text
STATION
├── HOSTS
├── CONTROL PLANE
├── ZONES
├── SHARED DISTRIBUTIONS
├── ARCHIVE
└── FLEET
```

### 2.2 Placement-independent Zones

```text
organization-alpha-dev
  host: station-core-01

organization-alpha-prod
  host: organization-alpha-prod-01
```

The identity of the Zone does not change when its placement changes.

### 2.3 Explicit evidence semantics

```text
prepared
→ observed
→ reported
→ verified
→ read_back
→ accepted
```

This is one of the strongest parts of the system. It prevents an executor's claim from being confused with independently observed proof.

### 2.4 Hermes-native-first

Station should compile policy and organization into Hermes, not recreate Hermes sessions, profiles, Bot Mode, Kanban, delegation, worktrees, cron, logs or provider routing.

### 2.5 Factory separation

Builder/Librarian/DevOps belong in the Factory Zone and should operate on synthetic or explicitly sanitized fixtures, not raw client data.

### 2.6 Honest setup boundary

`READY_FOR_SETUP` is a useful state. A repository cannot legitimately claim that external credentials, Discord applications or connected SaaS accounts exist before enrollment and readback.

---

## 3. Confirmed release blockers — P0

These are not theoretical concerns. They were reproduced against the current repository.

### P0-1 — Root path traversal in Zone and Project creation

**Files:**

- `installer/install_station.py:97-142`
- CLI arguments at `installer/install_station.py:212-228`

`--seed-name` and `--seed-project` are concatenated directly into paths without identifier validation or containment checks.

A dry-run accepted:

```text
--seed-name ../../escape
--seed-project ../../pwn
```

and planned writes outside the intended client subtree.

**Impact:** arbitrary root-owned path creation/write when the installer runs through `sudo`.

**Required correction:**

1. strict identifier grammar, for example `^[a-z][a-z0-9-]{0,47}$`;
2. reject dots, slashes, whitespace, shell metacharacters and Unicode confusables;
3. resolve the target and assert `target.is_relative_to(expected_parent)`;
4. refuse symlinks in every managed path component;
5. add adversarial tests.

---

### P0-2 — Remote command injection

**File:** `station:73-88`

Remote installer arguments are joined into one shell string:

```python
remote_cmd = 'cd ' + remote_dir + ' && sudo ./install ' + ' '.join(install_args)
```

A dry-run with:

```text
--zone-name 'organization-alpha;touch /tmp/STATION_PWN'
```

produced a remote command containing the injected shell command.

**Impact:** arbitrary remote command execution as root on a target Host.

**Required correction:**

- validate every identifier;
- stop constructing shell strings from user input;
- use a remote helper that receives a versioned JSON desired-state document on stdin;
- when a shell is unavoidable, use strict argument quoting and a fixed command entrypoint;
- pin the transferred release and verify its provenance before execution.

---

### P0-3 — Root installer follows attacker-controlled symlinks

**File:** `installer/install_station.py:26-40`

`Runner.mkdir()` and `Runner.write()` call normal `mkdir`, `write_text` and `chmod` operations without checking whether a managed path or ancestor is a symlink.

A local reproduction confirmed that `Runner.write()` follows a symlink and overwrites the symlink target.

**Impact:** after a Zone user controls a writable path, a later root installer/update can be redirected outside the Zone.

**Required correction:**

- lstat every managed ancestor;
- reject symlinks and unexpected file types;
- use atomic temporary files in the same trusted directory, then `os.replace`;
- use `O_NOFOLLOW` where available;
- never recursively chmod/chown through untrusted directory trees;
- make updates transactional.

---

### P0-4 — Project ownership is wrong

**Files:**

- `installer/install_station.py:107-134` correctly applies Zone ownership;
- `installer/install_station.py:136-142` creates Projects later but never applies Zone ownership.

A reproduction with a non-root-owned Zone resulted in:

```text
zone owner:    non-root Zone identity
project owner: root:root
```

**Impact:** the Zone service user cannot reliably write its own Project, repos, worktrees, state or evidence.

**Required correction:** derive the Zone identity from `ZONE.yaml` or filesystem metadata and apply exact ownership to every newly created Project path without recursive traversal of untrusted symlinks.

---

### P0-5 — `station-system` cannot reliably traverse its own state root

**Files:**

- `installer/install_station.py:216` creates `station-system` with home `/var/lib/station/system`;
- `installer/install_station.py:145` sets `/var/lib/station` to `0750 root:root`.

A service running as `station-system` is not guaranteed to traverse `/var/lib/station`, even though the repository expects it to manage Station state.

**Impact:** timers and system services can fail immediately after install.

**Required correction:** define a deliberate control identity and group model, then set parent traversal and writable subtrees explicitly. Do not solve this with world-readable permissions.

---

### P0-6 — Unreviewed mutable network installers execute as root

**Files:** `installer/install_station.py:190-202`

The root installer executes mutable remote scripts through `curl | sh` for Tailscale, Hermes and Composio.

**Impact:** the Station installer delegates root execution to whatever those URLs return at install time; it also makes builds non-reproducible.

**Required correction:**

- separate host bootstrap from third-party runtime enrollment;
- download to a temporary file first;
- record source, version/ref and installation receipt;
- prefer vendor package repositories or versioned releases;
- require explicit approval for mutable upstream installers;
- test installations in LAB before stable/client rollout.

This does not require publishing archive hashes in user-facing output. It requires controlled provenance and reproducibility.

---

## 4. Major implementation gaps — P1

### P1-1 — `station plan` is not a real plan for the requested Host

**Files:** `station:11-12`, parser at `station:121-135`

`station plan` always invokes:

```text
install_station.py --plan
```

It cannot receive Host role, Host ID or seed Zone parameters. Documentation presents it as the installation dry-run, but organization/project planning requires bypassing the Station CLI and calling the installer directly.

**Required correction:** one shared typed `InstallSpec` must drive `plan`, `apply`, remote bootstrap and tests.

---

### P1-2 — Config is copied, not reconciled

**Files:**

- `config/station.yaml`
- hard-coded `BASE_ZONES` and package mapping in `installer/install_station.py:19-24, 218-239`

The YAML claims to be desired state, but the installer does not use it to select features, base Zones or policy. Python constants are the real source of truth.

**Required correction:** parse and validate one canonical desired-state schema; compile a plan from it; apply exactly that plan; persist the observed-state result separately.

---

### P1-3 — Hermes is installed, but Station does not compile Zones/OSs into Hermes

The installer creates empty `runtime/hermes` directories and installs the global Hermes binary, but it does not:

- create Hermes profiles for Nano Directors/workers;
- install profile distributions;
- configure `terminal.cwd` per Project;
- install/enable Station plugins;
- install Ponytail where required;
- create Kanban boards;
- create Bot Mode identities;
- install per-profile gateways;
- configure dedicated Discord tokens;
- apply managed policy;
- run Hermes/plugin Doctor and readback.

Hermes profiles are separate state homes, but profiles are not filesystem sandboxes. Station therefore must combine profiles with Unix identity/runtime boundaries, not treat profile creation as sufficient isolation.

---

### P1-4 — Core OS packages fail the repository's own OS Contract Doctor

The repository marks packages as installed in Zone `installed.yaml`, but running the included `agk_builder.py doctor` against `packages/os/*` shows that every core package is incomplete relative to the canonical OS v2 contract.

Examples:

| Package | Files | Current reality |
|---|---:|---|
| `devops-os` | 3 | descriptor and docs only |
| `discord-bootstrap-os` | 2 | descriptor and README only |
| `fleet-operator-os` | 2 | descriptor and README only |
| `station-maintainer-os` | 4 | partial contract, no complete package tree |
| `builder-os` | 39 | legacy/partial format, not current complete OS v2 |
| `librarian-os` | 42 | legacy/partial format, not current complete OS v2 |

**Required correction:** distinguish `available`, `declared`, `installed`, `configured`, `verified`, and `operational`. Never write `packages:` under `installed.yaml` until the package passes contract validation and Hermes runtime installation succeeds.

---

### P1-5 — Discord experience is a scaffold, not a working adapter

**Files:**

- `runtime/programs/discord_experience_worker.py:24-30`
- `runtime/hermes-station/hermes/plugins/station-discord-experience/README.md:7-12`

The worker only counts mission records and bindings, then states that the real transport is to be implemented elsewhere. There is no Discord message create/edit transport, rate-limit handling, component interaction router, authorization, replay/idempotency or E2E test.

The current plugin also diverges from the official Hermes hook contract:

- callback parameter is named/required as `params` instead of the documented `args` contract;
- the block directive is `{"block": true, "reason": ...}` instead of the documented `{"action": "block", "message": ...}`;
- the manifest does not declare the tools/hooks it registers;
- if `STATION_CURRENT_MISSION_ID` is absent, the plan-first gate allows mutations instead of failing closed.

**Required correction:** build and validate this as a genuine Hermes plugin and a separate host-owned Discord adapter. Run `hermes plugins doctor ... --ci` in CI and add a Discord test-guild acceptance suite.

---

### P1-6 — Hermes update watcher ignores failure and performs no Station adaptation

**File:** `runtime/systemd/station-hermes-watch.service:5-12`

Current command:

```text
command -v hermes >/dev/null && hermes update --check || true
```

Every failure is swallowed. No durable update receipt is ingested. No LAB plan, capability diff, compatibility test, candidate promotion, rollback or Fleet rollout exists.

Hermes already supplies a safe update plan, machine-readable receipts, gateway restart outcomes and version-matrix checks. Station should consume those primitives instead of reducing the update system to a silent timer.

---

### P1-7 — Duplicate, contradictory systemd definitions

Two unit trees exist:

```text
runtime/systemd/
runtime/hermes-station/systemd/
```

They reference different paths and commands. `systemd-analyze verify` reports missing executables for the repository-state units. Only one generated unit source should exist.

---

### P1-8 — Rootless runtime is installed but not provisioned

Podman and supporting packages are installed, but Station does not create:

- per-Zone container storage/config;
- per-Zone networks;
- rootless service lifecycle;
- lingering/user service policy where required;
- sandbox templates;
- egress policy;
- resource limits;
- verification that one Zone cannot access another runtime.

The subordinate UID/GID range formula also lacks a global overlap/collision audit.

---

### P1-9 — Composio is only a binary installation

The repository does not yet implement:

- Station principal → Composio user mapping;
- account/toolkit allowlists;
- connected-account binding;
- session creation/reuse lifecycle;
- MCP endpoint registration into Hermes profiles;
- trigger ingress validation;
- readiness probes;
- revocation/rotation;
- Zone and environment isolation tests.

Therefore Composio must currently be reported as `binary_available`, not `integration_ready`.

---

### P1-10 — Fleet is SSH/rsync, not a Control Plane

The remote path copies the repository to `/tmp` and runs an SSH command. It has no:

- remote Station node agent;
- desired-state reconciliation;
- signed/approved release manifest;
- drift detection;
- operation ID/idempotency key;
- remote execution receipt;
- rollback transaction;
- Tailscale identity verification;
- strict host-key strategy;
- health state machine.

This is a bootstrap prototype, not Fleet orchestration.

---

### P1-11 — Backup, rollback and recovery are claims, not operations

Folders and documentation exist, but there is no working:

- off-host encrypted backup;
- per-Zone backup policy;
- Hermes profile backup integration;
- database-consistent snapshot;
- retention/rotation;
- restore command;
- recovery rehearsal;
- measured recovery point/recovery time;
- evidence/readback gate.

A production Station cannot reach `OPERATIONAL` before a restore rehearsal succeeds.

---

### P1-12 — Doctor is shallow and `--full` is functionally ignored

**File:** `station:18-37`

The `--full` flag changes no behavior. Doctor mainly checks whether directories and binaries exist.

It does not check:

- ownership/permissions;
- symlinks/unexpected file types;
- Zone identity mapping;
- Hermes profiles/config/plugins/gateways;
- OS contract compliance;
- Discord readback;
- Composio principal readiness;
- Tailscale identity;
- firewall/fail2ban policy;
- systemd unit health;
- rootless runtime;
- backup freshness;
- recovery state;
- update receipts;
- evidence database;
- remote Fleet health.

A binary being present is not operational readiness.

---

## 5. Quality and maintainability problems — P2

### P2-1 — Duplicate sources of truth

Audit metrics found:

```text
929 files
170 duplicate-content groups
542 files participating in duplicate groups
50 cache artifacts
```

Builder/Librarian files are copied through `factory/`, `packages/os/`, `os-factory-toolchain/` and `source-packs/`. Copies will drift.

**Required correction:** one canonical source tree; generated distributions are build artifacts, not committed parallel source trees. Source packs and historical snapshots should be release attachments or a separate archive repository where possible.

### P2-2 — CI validates shape, not installation

Current CI passes 14 root tests, but tests mainly assert file presence, terminology, labels and basic pure functions. It does not execute a fresh installation in a VM/container or test adversarial inputs.

### P2-3 — Linux support is over-broad

Documentation says “supported Linux,” while implementation assumes `apt-get` and systemd. The honest current support target is **Ubuntu/Debian with systemd**, until provider modules exist.

### P2-4 — Package/repository hygiene

The candidate archive includes `__pycache__`, `.pyc` and `.pytest_cache` artifacts. A public/private Git repository should not include them. Root licensing and third-party notices also need a deliberate decision.

### P2-5 — FHS responsibility is still mixed

Documentation says `/etc/station` is desired configuration and `/var/lib/station` is machine state, but mutable Control structures are also created under `/srv/station/1_CONTROL`.

A clear rule is needed:

- `/etc/station`: approved desired state and policy;
- `/opt/station/releases`: immutable software releases;
- `/var/lib/station`: observed state, registries, receipts, databases;
- `/srv/station`: human-operational Zone/Project content;
- `/var/log/station`: logs;
- `/run/station`: ephemeral runtime data.

`/srv/station/1_CONTROL` should be a human-readable projection/index, not a competing canonical database.

---

## 6. Recommended target architecture

### 6.1 Core control loop

```text
Git repository
    ↓
validated Station release
    ↓
Desired State Compiler
    ↓
typed Install/Reconcile Plan
    ↓
transactional Reconciler
    ↓
Host + Zone runtime
    ↓
Observed State / Receipts
    ↓
Doctor + Acceptance
```

The same typed plan must power:

```text
station plan
station apply
station update
station host bootstrap
station reconcile
CI fixtures
recovery rehearsal
```

### 6.2 Installed FHS layout

```text
/etc/station/
├── station.yaml
├── hosts.d/
├── zones.d/
├── policies.d/
└── bindings.d/

/opt/station/
├── releases/
│   └── <version>/
├── current -> releases/<version>
└── tools/

/srv/station/
├── 1_CONTROL/       # human projection, not canonical mutable DB
├── 2_ZONES/
├── 3_SHARED/        # read-only distributions/assets only
└── 4_ARCHIVE/

/var/lib/station/
├── control.db
├── receipts/
├── zones/<zone-id>/
│   ├── hermes/
│   ├── runtime/
│   └── databases/
└── backups-index/

/var/log/station/
└── zones/<zone-id>/

/run/station/
└── zones/<zone-id>/
```

### 6.3 Zone split

The Zone's human-operational directory remains under `/srv`, while high-churn service state belongs under `/var/lib`.

```text
/srv/station/2_ZONES/4_ORGANIZATIONS/organization-alpha/dev/
├── ZONE.yaml
├── README.md
├── projects/
├── os/                  # instance declarations/references
├── integrations/        # declarations/references
├── credentials/         # encrypted artifacts/references only
├── evidence/            # human index/exports
└── ops/

/var/lib/station/zones/organization-alpha-dev/
├── hermes/
├── mission-state/
├── databases/
├── connector-state/
└── caches/
```

This keeps `/srv` clean and prevents sessions/cache/runtime databases from polluting project navigation.

### 6.4 Hermes compilation model

```text
AGK OS package
    ↓
Station OS compiler
    ↓
Hermes Profile Distribution(s)
    + profile configs
    + skills/plugins
    + Kanban board definitions
    + cron disabled by default
    + dedicated Discord bot binding
    + capability/credential references
    ↓
Zone-local installation
    ↓
Hermes Doctor + plugin Doctor
    ↓
Discord/connector readback
    ↓
Fresh-session acceptance
```

Hermes Profile Distributions should be the runtime distribution unit for persistent Bots. AGK OS remains the larger organizational package that can compile several profiles, schemas, workflows, views and policies.

---

## 7. Required module maturity model

Every module and OS must declare one of these states:

```text
SPECIFIED
SCAFFOLDED
INSTALLABLE
CONFIGURED
VERIFIED
OPERATIONAL
DEGRADED
```

Definitions:

| State | Meaning |
|---|---|
| `SPECIFIED` | Contract/design exists |
| `SCAFFOLDED` | Files/code skeleton exists |
| `INSTALLABLE` | Deterministic installer succeeds |
| `CONFIGURED` | Required local configuration/secrets references resolve |
| `VERIFIED` | Doctor and module tests pass |
| `OPERATIONAL` | External readback/fresh-session acceptance passes |
| `DEGRADED` | Was operational; now failing with a declared repair action |

The current repository incorrectly compresses several of these into “installed.” This must be corrected before trustworthy automation is possible.

---

## 8. Release gates before the first real VPS

### Gate 1 — Installer safety

- identifier validation;
- path containment;
- symlink refusal;
- atomic writes;
- safe remote invocation;
- transaction/lock;
- rollback on partial failure;
- adversarial test suite.

### Gate 2 — Fresh Ubuntu VM install

- install from a clean supported Ubuntu image;
- reboot;
- systemd units healthy;
- repeated install is idempotent;
- uninstall/rollback tested;
- no manual repair.

### Gate 3 — Zone isolation

- Unix identities and groups verified;
- Project ownership verified;
- cross-Zone filesystem negative tests;
- rootless runtime negative tests;
- no shared mutable Hermes home;
- no shared secrets.

### Gate 4 — Real Hermes runtime

- create profiles from distributions;
- install/validate Station plugin;
- install Ponytail for DevOps/Builder profiles;
- configure workspaces and boards;
- install gateways;
- Hermes Doctor and plugin Doctor pass;
- update plan and receipt ingestion work.

### Gate 5 — Discord test guild

- dedicated OS bot enrolled;
- bootstrap plan/diff/apply/readback;
- one editable progress message;
- buttons/selects/modals authorized;
- rate limit/retry/idempotency tested;
- fresh-session mission accepted;
- admin privilege removed.

### Gate 6 — Composio test account

- explicit principal;
- toolkit/account restrictions;
- session/MCP lifecycle;
- auth and revocation;
- trigger ingress validation;
- negative cross-Zone test;
- readback evidence.

### Gate 7 — Backup and recovery

- off-host encrypted backup;
- complete Zone restore;
- Hermes profile restore;
- database restore;
- credential rebind;
- Discord reconnect;
- recovery acceptance mission.

### Gate 8 — Remote Host / Fleet

- Tailscale identity verification;
- immutable release transfer;
- safe desired-state apply;
- operation receipt;
- drift detection;
- remote Doctor;
- remote rollback.

Only after all eight gates should the repository be called a **one-repo Station installer**.

---

## 9. Recommended repository refactor

```text
agentik-station/
├── README.md
├── AGENTS.md
├── ARCHITECTURE.md
├── SECURITY.md
├── pyproject.toml
│
├── contracts/                 # canonical schemas and invariants
│   ├── station/
│   ├── host/
│   ├── zone/
│   ├── project/
│   ├── os/
│   └── evidence/
│
├── station/                   # one Python package / CLI
│   ├── cli/
│   ├── planner/
│   ├── reconciler/
│   ├── state/
│   ├── security/
│   ├── doctor/
│   ├── fleet/
│   └── providers/
│       ├── linux_ubuntu/
│       ├── hermes/
│       ├── discord/
│       ├── composio/
│       └── tailscale/
│
├── modules/                   # installable Station modules
│   ├── host-foundation/
│   ├── hermes-runtime/
│   ├── discord-experience/
│   ├── composio-plane/
│   ├── backup-recovery/
│   └── observability/
│
├── os/                        # one canonical source per AGK OS
│   ├── station-maintainer/
│   ├── discord-bootstrap/
│   ├── fleet-operator/
│   ├── builder/
│   ├── librarian/
│   └── devops/
│
├── distributions/             # generated; normally ignored or release artifacts
├── docs/
├── tests/
│   ├── unit/
│   ├── contract/
│   ├── security/
│   ├── install/
│   ├── integration/
│   ├── recovery/
│   └── e2e/
└── archive/                   # optional; preferably external release artifacts
```

The crucial change is **one canonical implementation per concern**. Factory copies, package copies and source-pack copies must not all remain editable sources.

---

## 10. Proposed delivery sequence

### v0.2.0-alpha — Safe foundation

- replace script-like CLI with one typed Python package;
- fix every P0 installer issue;
- implement plan/apply parity;
- versioned `/opt/station/releases` installation;
- transactional receipts;
- real full Doctor for Linux/Zone ownership;
- fresh Ubuntu VM CI.

### v0.3.0-alpha — Hermes runtime compiler

- compile OS/profile declarations into Hermes Profile Distributions;
- create profiles per Zone;
- configure cwd, tools, skills, plugins and gateways;
- install Ponytail where required;
- validate with Hermes/plugin Doctor;
- consume Hermes update plans and receipts.

### v0.4.0-alpha — Discord experience

- real test-guild adapter;
- Components V2 mission card;
- plan/progress/final message edits;
- authorized interactions;
- bootstrap diff/apply/readback;
- dedicated OS bot lifecycle.

### v0.5.0-alpha — Builder/Librarian and OS Factory

- real multi-lane research executor;
- source freshness/quality ledger;
- complete canonical OS packages;
- OS Contract Doctor on every package;
- build → install → fresh-session acceptance pipeline.

### v0.6.0-alpha — Connected capability plane

- Composio principals, account bindings, sessions/MCP and triggers;
- readiness state machine;
- cross-Zone negative tests;
- capability evidence.

### v0.7.0-beta — Fleet and recovery

- remote node agent/reconciler;
- desired-state rollout;
- backup/restore;
- update rings;
- remote rollback;
- first client pilot.

### v1.0.0 — Operational Station

- all release gates passed on clean infrastructure;
- recovery rehearsal complete;
- stable upgrade path;
- no module represented above its proven maturity state.

---

## 11. Immediate decision

### What can happen now

- create a **private** GitHub repository;
- label the repository `0.1.0-pre-alpha`;
- use it as the canonical architecture and hardening workspace;
- protect `main` and require CI/review;
- start v0.2.0 on a branch/worktree.

### What should not happen now

- do not run the current `sudo ./install` on Operator's real VPS;
- do not bootstrap a remote team Host with the current CLI;
- do not call the Discord/Composio/Fleet modules operational;
- do not store real client credentials in this version;
- do not publish it as a production-ready installer.

---

## 12. Final assessment

The project has crossed an important threshold: the **architecture is valuable enough to keep**, but the repository must now stop accumulating conceptual layers and enter a hard engineering phase.

The next objective is not another larger blueprint. It is:

> **make the smallest safe Station kernel that can install, reconcile, verify and recover one Zone on one fresh Ubuntu VPS.**

Then add Hermes profiles. Then Discord. Then Composio. Then Fleet.

That sequence preserves the ambition while eliminating the current gap between documentation and observed behavior.
