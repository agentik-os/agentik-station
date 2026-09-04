# Agentik Station Atlas

This is the operator's end-to-end map of Agentik Station: what every major part is, where it lives, who controls it, how Hermes connects it, how an Operative System is built and installed, how Discord becomes the human cockpit, and how the DevOps team executes work safely.

The Atlas describes release `11.12`. It separates implemented repository behavior from external setup that still needs real credentials and readback. Start here, then use `ARCHITECTURE.md`, `SECURITY.md`, `INSTALL.md` and `SETUP.md` for the normative details.

## 1. The system in one sentence

Station is the governed Linux control plane; Hermes is the Zone-isolated agent execution brain; an OS is the installable operating contract Hermes runs; model providers supply replaceable cognition; tools perform bounded actions; Discord and Agentik UI are human surfaces; evidence decides whether the result is truly done.

```text
Human intent
  │
  ├── Discord / Agentik UI / CLI / API
  │
  ▼
Station policy + identity + desired state
  │  resolves Host → Zone → Project → OS → mission → capabilities
  ▼
Hermes central execution fabric (one isolated HERMES_HOME per Zone)
  ├── Nano Director profile
  ├── specialist profiles / Bot Mode / delegated workers
  ├── sessions + Kanban + mission graph
  ├── Skills + plugins + hooks + cron
  ├── model-provider routes
  ├── MCP / Composio / native tools / direct APIs
  ├── workspaces + Git worktrees
  └── memory + logs + learning candidates
  │
  ▼
Real systems and Project code
  ├── GitHub / repositories / CI
  ├── Vercel / Convex / Clerk / Stripe
  ├── Discord and other messaging platforms
  ├── Langfuse / Honcho / Hindsight / Crawl4AI
  └── Hosts / containers / services / TigerVNC
  │
  ▼
Observed result → verification → external readback → evidence → acceptance
```

## 2. Who is in control

The phrase “Hermes is the central brain” means Hermes coordinates runtime execution. It does not mean one global, all-powerful bot owns every secret.

| Layer | Owns | Must not own |
|---|---|---|
| Station | constitution, desired state, isolation, placement, capability policy, releases, receipts and evidence gates | free-form model reasoning or every provider's implementation |
| Zone | one operational/security boundary, Unix identity, HERMES_HOME, credentials, memory, logs and runtime state | another Zone's data or accounts |
| Project | repos, docs, knowledge, resources, workspaces, worktrees, artifacts and evidence | global Station policy or unrelated Project data |
| Hermes | sessions, profiles, Bot Mode, delegation, Skills, plugins, tools, provider routing, gateway, memory and mission execution | self-authorized privilege or Station's source of truth |
| Nano Director | one OS outcome and its mission graph | unlimited Host access or automatic production approval |
| LLM provider | cognition for a routed task | identity, authority, durable truth, secret storage or deployment ownership |
| Capability/tool | one typed action against a declared target | policy decisions outside its input contract |
| Discord | human interaction and semantic status projection | canonical state, secrets or recursive bot-to-bot orchestration |
| Evidence | proof of what was observed and accepted | credentials or unverifiable claims |

The power comes from this split. Hermes can use many providers and tools without giving any one provider the keys to the whole Station. A provider can change while the Zone, mission, permissions, state and audit trail remain stable.

## 3. Canonical vocabulary

- **Station** — the complete governed environment across one or more Hosts.
- **Host** — one Linux machine or VPS running the Station kernel.
- **Control Plane** — desired state, registries, bindings, placement, releases and evidence indexes.
- **Zone** — the only canonical operational/isolation boundary. Each Zone has its own Unix identity and HERMES_HOME.
- **Project** — the owner of one body of source, knowledge, resources, integrations, credentials, execution spaces and evidence.
- **Operative System (OS)** — a versioned domain operating capability compiled into a Hermes team. It is not a computer operating system.
- **Nano Director** — the persistent Hermes profile accountable for one OS outcome.
- **NanoTeam** — the persistent specialists and bounded workers coordinated by the Nano Director.
- **Mission** — durable work with an objective, graph, owners, gates, state and evidence.
- **Skill** — reusable procedural expertise invoked by Hermes/profile policy.
- **Program/workflow** — deterministic or graph-based execution logic.
- **Capability** — an allowlisted action such as repository read, Discord plan, staging deploy or evidence write.
- **Connector/provider** — the adapter to an external model, app, platform or API.
- **Workspace/worktree** — a temporary, isolated execution area for a mission branch.
- **Resource** — a reviewed reusable dependency, component source, icon library, recipe or asset.
- **Evidence** — durable proof attached to a claim.
- **Fleet** — all Station Hosts and their Zone placements.

## 4. The clean `station` filesystem

Everything belongs to the Station namespace, but it is deliberately not placed in one physical directory. Linux code, configuration, mutable state, logs, secrets and backups have different permissions and lifecycle needs. `/srv/station` is the clean human entry point; the other roots are its governed backing layers.

```text
/etc/station/                    desired state and approved policy
├── station.json
├── station.yaml
├── hosts.d/
├── zones.d/
├── policies.d/
└── bindings.d/

/opt/station/                    immutable software
├── releases/<version>/          exact repository release
├── current -> releases/<version>
├── .staging/<operation>/
└── tools/hermes/current/        shared Hermes executable code

/srv/station/                    human-operational entry point
├── README.md
├── 1_CONTROL/                   generated navigation, never canonical state
├── 2_ZONES/
│   ├── 1_SYSTEM/
│   ├── 2_PRIVATE/
│   ├── 3_AGENTIK/
│   ├── 4_ORGANIZATIONS/
│   ├── 5_PROJECTS/
│   ├── 6_FACTORY/
│   └── 7_LAB/
├── 3_SHARED/
│   ├── packages/
│   ├── schemas/
│   ├── assets/
│   ├── cache/
│   └── resources/               pointer to reviewed release resources
└── 4_ARCHIVE/

/var/lib/station/                durable mutable machine/runtime state
├── system/
├── receipts/
├── observed/
├── registry/
├── doctor/
└── zones/<zone-id>/
    ├── home/
    ├── hermes/                  this Zone's HERMES_HOME
    ├── mission-state/
    ├── databases/
    ├── connector-state/
    ├── caches/
    └── projects/

/var/log/station/                system and Zone logs
/var/backups/station/            local recovery staging
/run/station/                    ephemeral locks, sockets and runtime files
```

Source-of-truth rules:

1. `/etc/station` says what should exist.
2. `/var/lib/station` records what exists and what happened.
3. `/opt/station/releases` contains immutable executable history.
4. `/srv/station` is the operator-friendly view and contains human Project assets.
5. Secrets never enter Git, `1_CONTROL`, Discord messages, evidence or shared release code.

## 5. Zone and Project anatomy

A Zone is the security envelope:

```text
Zone
├── declared owner, organization, environment and Host placement
├── dedicated Unix user/group
├── dedicated HERMES_HOME
├── dedicated credentials, memory, logs, state, run and backup roots
├── Projects
├── installed OS instances
├── integrations and connector bindings
└── Doctor, evidence and recovery contract
```

A Project is the work envelope:

```text
<zone>/projects/<project-id>/
├── PROJECT.json / PROJECT.yaml
├── README.md
├── .station/STATION_AGENT_RULES.md
├── AGENTS.md / CLAUDE.md / GEMINI.md
├── repos/                       Git repositories only
├── docs/                        Project documentation
├── knowledge/                   approved domain knowledge
├── resources/                   selected catalog resources/decisions
├── integrations/                non-secret integration declarations
├── credentials/                 scoped references/material, mode 0700
├── workspaces/                  temporary mission environments
├── worktrees/                   parallel Git worktrees
├── state/                       human-facing state references
├── artifacts/                   build and generated deliverables
├── evidence/                    Project evidence
└── ops/                         runbooks and operational controls
```

Local and remote are only placement. `organization-alpha-dev` can run on the core Host while `organization-alpha-prod` runs on a dedicated Host; both keep the same Zone contract.

## 6. Universal rules for Hermes and every LLM CLI

The canonical rules are `rules/STATION_AGENT_RULES.md`; `config/agent-runtime-policy.json` is the machine-readable routing policy.

Entry points:

| Executor | Instruction entry point |
|---|---|
| Hermes profile | rules embedded in generated `SOUL.md` plus `STATION_RULES.md` |
| Codex | root/project `AGENTS.md` |
| Claude Code | `CLAUDE.md` → canonical rules |
| Gemini CLI | `GEMINI.md` → canonical rules |
| GitHub Copilot | `.github/copilot-instructions.md` → canonical rules |
| Other CLI/agent | `.station/STATION_AGENT_RULES.md` |

Install the same managed rules into an existing Project repository without deleting its local instructions:

```bash
station rules install --repo /srv/station/2_ZONES/<category>/<zone>/<env>/projects/<project>/repos/<repo> --plan
station rules install --repo /srv/station/2_ZONES/<category>/<zone>/<env>/projects/<project>/repos/<repo>
```

The installer appends one marked, idempotent adapter block and preserves existing agent instructions. Run the write command as the owning Zone/Project user, never root.

Every executor follows the same order:

```text
resolve Host/Zone/Project/repo/environment/principal
→ inspect current state
→ Plan First
→ select allowlisted capabilities
→ create/use the owning workspace or worktree
→ implement
→ test + Doctor + independent review as required
→ external readback when a real system changed
→ record evidence and repair action
→ accept only after all gates pass
```

These rules follow the standard repository instruction hierarchy used by Codex; see the official [AGENTS.md guidance](https://learn.chatgpt.com/docs/agent-configuration/agents-md).

## 7. Hermes as the central execution brain

Station installs one reviewed Hermes codebase in `/opt/station/tools/hermes/current` and exposes `/usr/local/bin/hermes`. It never gives all organizations one global Hermes home. Every Zone invokes the same engine with different identity and state:

```text
runuser --user <zone-unix-user> --
  HOME=<zone-state-root>/home
  HERMES_HOME=<zone-state-root>/hermes
  XDG_RUNTIME_DIR=/run/user/<zone-uid>
  /usr/local/bin/hermes <action>
```

That design provides:

- one engine to maintain and update;
- isolated credentials, profiles, sessions, memory and bot state;
- stable missions even when an LLM provider changes;
- a common bot protocol across Discord, Slack, Telegram and other surfaces;
- native delegation between OS teams without public bots talking in loops;
- consistent Skills, tool filtering, logging, Doctor and evidence hooks.

Hermes maps Station concepts this way:

| Station concept | Hermes runtime primitive |
|---|---|
| Nano Director | persistent profile/Bot |
| NanoTeam specialist | persistent profile or delegated worker |
| mission | session + durable mission/graph state |
| task queue | Kanban/work items |
| ordered expertise | Skills |
| deterministic action | Program/tool/plugin |
| provider choice | model/provider route |
| app connector | native tool, MCP, Composio or typed API adapter |
| schedule | cron/automation |
| coding branch | Project worktree/workspace |
| public bot surface | Hermes Messaging Gateway |
| memory | Zone/profile-scoped memory provider |
| improvement | reviewed learning candidate, never silent policy mutation |

## 8. How an Operative System is built

Canonical editable OS source lives only in `os/<os-id>/`. A generated Hermes distribution is a disposable artifact, never a second source tree.

Every AGK OS v2 defines:

```text
outcome contract
+ Nano Director
+ NanoTeam profiles
+ ordered Skills
+ deterministic programs
+ capabilities and integrations
+ knowledge and memory scope
+ data and mission schemas
+ provider routes
+ workflows and automations
+ governance and engineering harness
+ evaluations and evidence
+ Discord surface and views
+ Doctor
+ update, rollback and recovery
+ self-improvement policy
+ Librarian handoff
+ deployment and orchestration
+ Hermes distribution template
```

The build path is:

```text
Request for a new/updated OS
  ↓
Librarian OS
  ├── maps the topic and terminology
  ├── reads canonical books/reference material
  ├── checks current primary web sources
  ├── gathers expert/operator knowledge
  ├── finds contrarian/failure evidence
  ├── scores provenance and contradictions
  └── produces the structured Builder handoff
  ↓
Builder OS
  ├── locks outcome and boundaries
  ├── designs director/team/topology
  ├── orders Skills and capabilities
  ├── defines workflows/data/evidence
  ├── defines Discord/Doctor/recovery
  ├── implements contracts and source
  ├── runs tests, Gauntlet and independent review
  └── publishes a versioned canonical package
  ↓
Station OS compiler
  ├── validates AGK OS v2 source
  ├── compiles every profile distribution
  ├── injects Project root and universal rules
  └── emits COMPILED_NOT_INSTALLED
  ↓
Zone installation
  ├── Hermes profile install in that Zone's HERMES_HOME
  ├── provider/credential enrollment
  ├── Discord/connector binding
  ├── Hermes and plugin Doctor
  └── fresh-session + external readback acceptance
```

Repository OS packages currently include Station Maintainer, Discord Bootstrap, Fleet Operator, Builder, Librarian and DevOps. Query them with:

```bash
station os catalog
station os doctor --all
station os compile --id devops-os --project-root /absolute/project --output /new/output
sudo station os install --id devops-os --zone <zone-id> --project <project-id>
station os verify --id devops-os --zone <zone-id>
```

Compile is not install; install is not external acceptance; profile Doctor is not Discord/deployment readback.

## 9. End-to-end mission flow

Example: “deploy the application” arrives in the DevOps Discord channel.

1. The Hermes gateway receives the Discord event inside the owning Zone.
2. Immutable guild/channel/user bindings resolve the Zone, Project, OS and `atlas` profile.
3. Authorization checks the human principal, channel and requested capability.
4. Atlas creates or resumes the Hermes session and durable Station mission.
5. Atlas clarifies target environment and acceptance; production is denied unless explicitly approved.
6. Atlas writes a Plan First graph and projects a semantic Mission Progress Card to Discord.
7. Architect inspects architecture and defines the change/recovery contract.
8. Forge works in the Project repository/worktree, implements and tests.
9. Sentinel independently reviews security, quality, negative paths and claim accuracy.
10. Release Engineer verifies pins, locks, CI and reproducible artifacts; it deploys staging or an approved production release.
11. SRE verifies service and user-path readback, observes health and records rollback coordinates.
12. Atlas accepts only if every required gate passed; otherwise it reports `BLOCKED`/`DEGRADED` with a next action.
13. Discord receives the concise result; detailed evidence remains in Station/Project evidence, not in public chat.

This flow is the same if the initial surface is Slack, Telegram, browser chat, Agentik UI, API or CLI. The platform is an ingress/egress adapter; Hermes and Station retain orchestration and truth.

## 10. Capability and tool resolution

Hermes selects the smallest approved mechanism in this order:

1. existing Project/Station code;
2. Hermes-native profile, Skill, plugin, hook, gateway, memory or worktree capability;
3. operating system or standard-library function;
4. reviewed installed dependency;
5. MCP or Composio connected capability;
6. typed direct API adapter;
7. the smallest justified new implementation.

Each capability has a scope, principal, input contract, output contract, permission policy, timeout/retry behavior, evidence and failure state. “The model knows how” never grants permission.

Optional AI components have distinct jobs:

| Component | Job in Station | Control boundary |
|---|---|---|
| Ponytail | Hermes/engineering plugin for focused YAGNI coding | pinned plugin; enabled only for suitable profiles |
| Langfuse | LLM traces, observability and evaluations | self-host/cloud enrollment, keys, retention and trace readback required |
| Honcho | stateful agent memory SDK | isolated Python environment and Zone-scoped store/account |
| Hindsight | learning/recall memory provider | bind per Zone/profile; verify recall and cross-Zone denial |
| Crawl4AI | agent-friendly crawling/scraping | isolated tool, allowlisted domains/egress and evidence |
| TigerVNC | private remote graphical session when needed | private network, authentication, firewall and viewer readback |
| Composio | scoped connected-account capability plane | stable principal plus explicit toolkit/account allowlist |

Use `station deps list` and install only declared components. `--with-ai-stack` stages all of them but does not authenticate, expose or accept them.

## 11. Resource catalog and the preferred product stack

The source catalog is `resources/CATALOG.json`. In an installed release its canonical read-only location is `/opt/station/current/resources`; `/srv/station/3_SHARED/resources` points operators there. A Project's `resources/` directory records what that Project selected.

```bash
station resource list
station resource show --id shadcn-ui
station resource show --id lucide
station resource stack-plan --id web-product
```

The preferred `web-product` stack is:

| Resource | Role |
|---|---|
| Next.js + React | application, rendering and route/runtime structure |
| Convex | reactive backend, durable application state and server functions |
| Clerk | user identity, sessions and application authorization integration |
| Stripe | payments, subscriptions and billing events |
| Vercel | build/deployment/preview delivery |
| Tailwind CSS | styling primitives |
| shadcn/ui | accessible, Project-owned component source |
| Lucide | default semantic React icons |

The `shadcn` CLI is installed in the pinned operator toolchain. shadcn components and `lucide-react` remain Project dependencies: they are added inside the owning repository, reviewed and committed there. A global CLI is not Project configuration.

The stack is open. Python services, mobile apps, Rust, Go, another database, another identity provider or another deploy target are allowed when the Project declares exact versions, data/secret ownership, verification, operations and rollback. The catalog is a reviewed default, not vendor lock-in.

External setup remains explicit:

- Vercel project/team link and least-privilege login;
- Convex deployment/project enrollment and keys;
- Clerk application, environment keys and webhook verification;
- Stripe test/live separation, webhook signing secret and event readback.

Never put these keys in the resource catalog, repository or Discord.

## 12. Discord architecture

Discord is the organization cockpit. Hermes supplies the gateway/session primitive; Station supplies Zone isolation, identity bindings, desired topology, capability policy, mission semantics and evidence gates.

### Safe bootstrap boundary

A bot token is a secret and the Discord server owner controls guild authorization. The safe base flow is:

```text
1. Human owner creates the Discord application and bot in the Developer Portal.
2. Human owner configures required intents and obtains/rotates the token.
3. Human owner authorizes the application to the target guild with OAuth2.
4. Prefer explicit create/manage/view/send permissions.
5. If initial topology truly needs it, owner grants temporary Administrator
   for a declared maintenance window.
6. Operator runs the owning Zone's Hermes setup and enters the token there.
7. Bootstrap Director inventories the existing guild.
8. It compiles desired state from organization + installed OS declarations.
9. It shows an adopt-and-extend plan; deletes are denied by default.
10. It creates/updates roles, categories, channels, overwrites and commands.
11. It stores immutable Discord IDs in Zone connector state.
12. It verifies routes, commands and message/interactions readback.
13. Human owner removes temporary Administrator/elevated role.
14. Station reads back the new role state and tests runtime least privilege.
15. Evidence is recorded; only then may the surface be accepted.
```

Use the Zone-isolated wizard:

```bash
sudo station platform setup --zone <zone-id> --platform discord --plan
sudo station platform setup --zone <zone-id> --platform discord
sudo station platform install --zone <zone-id>
sudo station platform start --zone <zone-id>
sudo station platform status --zone <zone-id>
sudo station platform doctor --zone <zone-id>
```

Tokens are entered only through Hermes' interactive setup, never as a command argument. Discord's official documentation treats bot tokens like passwords and applies permissions at guild authorization; it also documents role hierarchy limits. See [OAuth2 and permissions](https://docs.discord.com/developers/platform/oauth2-and-permissions) and [server/channel management](https://docs.discord.com/developers/platform/server-and-channel-management).

Important limitation: a guild bot token cannot safely mint all the separate Discord applications and secret tokens required by a strict “one public bot per OS” topology. Humans create and authorize those applications/tokens unless a separately governed control plane is introduced. Internal specialist profiles normally stay behind the OS Nano Director, so they do not each need public bots.

### Base desired server structure

```text
00_CONTROL
├── command-center             operator entry and routing
├── approvals                  explicit human gates
└── system-status              concise health/readiness

<OS categories generated from installed manifests>
├── <os-primary-channel>       dedicated Nano Director surface
└── optional mission threads   conversation/session boundaries

40_ENGINEERING
├── devops                     Atlas / DevOps OS
├── qa                         verification summaries
└── deployments                release and readback summaries

90_SYSTEM
├── evidence                   sanitized evidence links
├── incidents                  SRE/incident coordination
└── node-health                Host/Fleet observations
```

One channel maps to stable guild/category/channel/role/application/bot IDs in:

```text
/var/lib/station/zones/<zone-id>/connector-state/discord/bindings.yaml
```

Names may change; IDs drive routing. Existing servers use adopt-and-extend. Unknown roles/channels are not deleted or renamed by default.

### Current implementation truth

Release 11.12 has a Zone-aware Hermes gateway wrapper, Discord binding validation, a host-owned message create/edit/read transport and a plan-first Discord Experience plugin. The full role/category/channel/command provisioner has not yet passed real test-guild create/edit/interaction/permission/readback acceptance. It is `INSTALLABLE`, not `OPERATIONAL`. The desired bootstrap workflow above is the acceptance target, not a false claim that every step already ran.

## 13. Hermes multi-platform bot protocol

Discord is one adapter. The same Zone-isolated Hermes Messaging Gateway can connect Telegram, Slack, WhatsApp, Signal, SMS, Email, Home Assistant, Mattermost, Matrix, DingTalk, Feishu/Lark, WeCom, Weixin, BlueBubbles/iMessage, QQ, Yuanbao, Microsoft Teams, LINE, ntfy and browser chat.

For any supported platform:

```bash
sudo station platform setup --zone <zone-id> --platform <platform>
sudo station platform install --zone <zone-id>
sudo station platform start --zone <zone-id>
sudo station platform status --zone <zone-id>
sudo station platform doctor --zone <zone-id>
```

Each connector still needs its own human/account enrollment, allowed users/channels and bidirectional message readback. Hermes makes platforms easy to attach; it does not erase each platform's security model.

## 14. DevOps OS team map

The DevOps OS uses Hermes as its coordination fabric and exposes Atlas as its public Nano Director.

| Member | Owns | Typical outputs | Cannot self-authorize |
|---|---|---|---|
| Atlas, Nano Director | scope, Plan First graph, capability routing, mission truth, evidence and acceptance | mission plan, assignments, status card, final decision | production/destructive authority, failed-gate waiver |
| Architect | architecture, interfaces, ADRs, dependency/recovery design | design, risks, contracts, migration/rollback plan | production apply or self-certification |
| Forge | implementation, migrations and local tests in the owning worktree | focused diff, tests, implementation handoff | accepting its own work or default production access |
| Sentinel | independent security, quality, negative/adversarial verification | findings, gate decision, regression requirements | silent threshold changes or hidden waivers |
| Release Engineer | pins, locks, manifests, CI, artifacts, staging, approved promotion | reproducible release, CI/deploy receipts, rollback coordinate | inferred production approval |
| SRE | runtime health, external readback, incidents, runbooks and recovery | health/readback evidence, incident timeline, recovery result | silent destructive recovery or health from process presence alone |

The normal graph is:

```text
Atlas clarify
  → Architect design
  → Atlas plan/authorize capabilities
  → Forge implement/test
  → Sentinel independent gate
  → Release Engineer package/CI/stage/approved promote
  → SRE runtime and user-path readback
  → Atlas evidence-backed acceptance
```

Safe non-overlapping research, test and implementation branches may run in parallel, but each branch has an owner and verification owner. Shared mutable code uses separate Project worktrees and an explicit integration gate.

Provider routing is role-based and model-agnostic: high-reasoning routes for Atlas/Architect, task-fit coding for Forge, an independent review route for Sentinel, release-task-fit for Release Engineer and operations-task-fit for SRE. If an approved provider fails, Hermes routes to another approved provider or marks the node blocked; it never silently expands permissions.

## 15. GitHub, Vercel, Composio and external tools

Tool installation, authentication, authorization and successful action are separate states.

```text
binary present
→ correct pinned version
→ correct account/principal authenticated
→ required repository/project/account selected
→ least-privilege scope verified
→ safe probe observed
→ real action read back
→ accepted for that Zone/Project
```

- **GitHub CLI** — repository and CI operations; `gh auth login` and `gh auth status` are operator-owned. Repositories stay under Project `repos/`.
- **Vercel CLI** — project/team deployment; `vercel login` and `vercel whoami` do not replace Project link and deploy readback.
- **Composio CLI** — connected capability setup; use stable Station principals and explicit toolkit/account allowlists. No generic global production principal.
- **Codex/Claude/Gemini** — coding cognition/execution clients governed by repository rules; they do not become Station authority.
- **Model APIs** — provider routes are scoped per profile/mission. Keys remain in Zone/Project credential mechanisms.

Check the toolchain:

```bash
station deps toolchain-plan
sudo station deps toolchain-install
station deps toolchain-check
station provider status
```

## 16. Fresh Host installation: exact path

### A. Prepare and inspect

On a supported fresh Ubuntu/Debian systemd Host:

```bash
git clone https://github.com/agentik-os/agentik-station.git
cd agentik-station
./station doctor --repo
./station plan --host-id station-core-01 --role core
```

### B. Install

Full Operator Station:

```bash
sudo ./bootstrap.sh --mode full
```

Full Operator Station plus all optional AI components:

```bash
sudo ./bootstrap.sh --mode full --with-ai-stack
```

Organization/team Host:

```bash
sudo ./bootstrap.sh --mode team --organization organization-alpha --project platform
```

Bootstrap creates the dedicated `agk-station` operator, relocates source outside `/root`, installs pinned Python runtimes, Node/npm, GitHub CLI, Vercel CLI, Codex CLI, Composio CLI and shadcn CLI, installs the reviewed Hermes version, reconciles the Station FHS layout and creates declared Zones/Projects.

### C. Verify base state

```bash
station doctor --full
station status
station module status
station deps toolchain-check
```

The correct base result is `READY_FOR_SETUP`, not `OPERATIONAL`.

### D. Configure Project repositories and rules

Clone only under the owning Project `repos/`, then install the common rules as that Zone user:

```bash
station rules install --repo <absolute-project-repository> --plan
station rules install --repo <absolute-project-repository>
station resource stack-plan --id web-product
```

Review and apply the stack plan inside that repository if the Project chose it.

### E. Enroll external systems

1. authenticate only required GitHub/Vercel/Composio/model principals;
2. create and separate development/staging/production provider projects;
3. configure scoped credential references in the owning Zone/Project;
4. install selected OS packages into the correct Zone and Project;
5. configure the Hermes platform gateway, including Discord if used;
6. run provider-specific Doctor and safe read/write probes;
7. verify live message/deployment/connector readback.

### F. Enable persistent automation last

Every cron, trigger or persistent bot starts disabled. Run a fresh session using only deployed configuration and durable state. Enable automation only after it passes, trigger it once and verify delivery/readback.

## 17. Hermes and dependency updates

Hermes is pinned to a reviewed release/commit. The updater is backup- and Doctor-gated:

```bash
station hermes check
station hermes update
sudo station deps enable-auto-update
```

The weekly timer is enabled by bootstrap unless explicitly skipped. Update flow:

```text
check upstream
→ record candidate
→ pre-update backup
→ apply reviewed update
→ Hermes Doctor and gateway observation
→ receipt
→ keep candidate or request restore on failure
```

Automatic update does not automatically promote every OS or dependency. OS migrations, plugins, messaging platforms and external applications keep their own compatibility/readback gates. Version changes belong in `config/versions.lock` and resource recipes only after review.

Station releases themselves are immutable:

```text
/opt/station/releases/<version>
/opt/station/current -> releases/<version>
```

Rollback selects an already installed release, then requires full Doctor and runtime compatibility checks:

```bash
sudo station release rollback --to <version>
station doctor --full
```

## 18. Evidence, maturity and honest completion

Station uses two related truth systems.

Evidence ladder:

```text
PREPARED → OBSERVED → REPORTED → VERIFIED → READ_BACK → ACCEPTED
```

Maturity/readiness ladder:

```text
SPECIFIED → SCAFFOLDED → INSTALLABLE → CONFIGURED → VERIFIED → OPERATIONAL
                                                                    │
                                                                    └→ DEGRADED if it later fails
```

Examples:

- a generated command is `PREPARED`, not run;
- exit code zero is `OBSERVED`, not external readback;
- an agent report is `REPORTED`, not independent verification;
- local tests may make code `VERIFIED`, not a remote integration operational;
- a message ID alone is not bidirectional Discord acceptance;
- a deployment upload is not application/user-path readback;
- an installed memory client is not a Zone-isolated memory round-trip;
- copied OS source remains `NOT_INSTALLED` until compiled and installed;
- profile Doctor still does not prove Discord or provider acceptance.

Every failed or incomplete gate keeps the lower truthful state and records a concrete next repair action.

## 19. Recovery and incident behavior

On failure:

1. stop unsafe dependent nodes;
2. preserve the observed error and partial-operation receipt;
3. never pretend an external API sequence was transactional;
4. re-inventory current state instead of replaying assumptions;
5. use the documented rollback/recovery capability within its scope;
6. require a new Doctor and readback;
7. keep the module `DEGRADED` until the failed accepted behavior is restored.

Backups are useful only after a destructive restore rehearsal. Off-Host repository, encryption, retention, Zone inclusions/exclusions, credential rebinding and fresh-session acceptance are setup gates.

## 20. What is ready now and what still needs the real world

Repository-verified or implemented:

- typed plan/apply and SafeFS-based privileged reconciliation;
- immutable releases, receipts, Doctor and Zone/Project layouts;
- reviewed/pinned operator toolchain installer including shadcn CLI;
- reviewed Hermes install/update path with isolated Zone homes;
- canonical OS sources, source Doctor and Hermes profile compiler;
- universal provider/CLI rule distribution;
- resource catalog and exact web-product stack plan;
- Hermes multi-platform gateway lifecycle wrapper;
- Composio binding policy and Discord message/binding foundations;
- DevOps team ownership and mission graph.

External acceptance still required:

- a real fresh-VPS install/reboot and service readback;
- real Hermes profile/plugin/fresh-session acceptance;
- GitHub/Vercel/Composio/model-provider account/scoping probes;
- full Discord topology provisioning and interaction/permission readback in a test guild;
- each dedicated OS Discord application/token human enrollment;
- Langfuse/Honcho/Hindsight/Crawl4AI/TigerVNC runtime setup as selected;
- rootless cross-Zone negative tests;
- remote Fleet drift/rollback acceptance;
- encrypted off-Host destructive restore rehearsal.

No document may promote those items to `OPERATIONAL` before their evidence exists.

## 21. Operator acceptance checklist

- [ ] Repository Doctor passes.
- [ ] Plan was reviewed before apply.
- [ ] Full Host Doctor passes after install/reboot.
- [ ] Every Zone has the expected Unix owner and independent HERMES_HOME.
- [ ] Every Project lives inside its Zone and every repo under `repos/`.
- [ ] Common Station rules are present in every executor entry point.
- [ ] Dependencies match the Project contract and reviewed pins.
- [ ] GitHub/Vercel/Convex/Clerk/Stripe/Composio principals are least-privilege and environment-specific.
- [ ] Each installed OS compiles, installs and passes Hermes/plugin Doctor.
- [ ] Discord applications/tokens were created and authorized by the owner.
- [ ] Temporary Discord elevation was removed by the owner and read back.
- [ ] Messaging passes inbound, outbound, unauthorized-user and restart tests.
- [ ] DevOps work passes Architect → Forge → Sentinel → Release → SRE gates as applicable.
- [ ] Production actions have named human approval.
- [ ] Logs/evidence contain no secrets.
- [ ] Backup restore and rollback coordinates are known and tested.
- [ ] Persistent automations pass fresh-session acceptance before enablement.
- [ ] Module status and claims match observed evidence.

## 22. Canonical source map

- `AGENTS.md` — mandatory repository engineering contract.
- `rules/STATION_AGENT_RULES.md` — universal Hermes/LLM/executor rules.
- `config/agent-runtime-policy.json` — machine-readable executor/provider policy.
- `ARCHITECTURE.md` — normative system and filesystem architecture.
- `SECURITY.md` — threat model and security constraints.
- `INSTALL.md` — Host plan/apply contract.
- `SETUP.md` — external enrollment and acceptance gates.
- `config/versions.lock` — reviewed tool/dependency pins.
- `config/deps/stack.yaml` — optional AI dependency roles and maturity.
- `resources/CATALOG.json` — reusable resources and preferred stack recipe.
- `modules/catalog.json` — module maturity claims and next actions.
- `os/CATALOG.json` — canonical OS packages.
- `os/librarian/` — research/intelligence OS.
- `os/builder/` — OS factory/compiler-design OS.
- `os/devops/` — engineering/release/operations team.
- `os/discord-bootstrap/` — Discord desired topology/bootstrap contract.
- `src/agentik_station/` — safe Station kernel and runtime adapters.
- `runtime/hermes-station/` — Station-owned Hermes integration/plugin source.
- `tests/` and `factory/tests/` — contract, security, installer and Factory verification.
- `docs/history/` — provenance only; never current runtime truth.

When documents disagree, use this precedence: repository agent/security contracts, current canonical architecture/setup docs, machine-readable contracts and active code/tests; history comes last and cannot override current behavior.
