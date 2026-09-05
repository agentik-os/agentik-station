<p align="center">
  <a href="https://discord.gg/agentik-os"><img src="https://img.shields.io/badge/JOIN_DISCORD-AGENTIK_OS-c5f277?style=for-the-badge&amp;logo=discord&amp;logoColor=c5f277&amp;labelColor=10161c" alt="Join the Agentik OS Discord"></a>
  <a href="atlas.md"><img src="https://img.shields.io/badge/EXPLORE-THE_ATLAS-e6edf3?style=for-the-badge&amp;labelColor=10161c" alt="Explore the Station atlas"></a>
  <a href="https://github.com/agentik-os/agentik-station/actions/workflows/ci.yml"><img src="https://github.com/agentik-os/agentik-station/actions/workflows/ci.yml/badge.svg?branch=main" height="28" alt="Station CI status on main"></a>
</p>

<a href="#the-mission-circuit">
  <img src="docs/assets/readme/station-mission-control.svg" width="100%" alt="Agentik Station. Your AI teams. Your infrastructure. Mission circuit: human intent enters Station policy, Hermes orchestrates teams and tools, and evidence returns for review and acceptance. Illustrated architecture, not live telemetry.">
</a>

# Agentik Station

### AI teams deserve an operating system.

**Chief AI Officer AIOS — a governed agentic environment for your VPS.** Station provides the Linux foundation, policy, Zones and evidence. **Hermes is the central execution brain.** Installable Operative Systems give it specialized teams; Discord and other Hermes chat platforms give you a place to direct the work.

Bring your projects, models and tools. Give every mission an owner, a workspace and a verification gate.

**[System map](#the-whole-system)** · **[Install](#quickstart)** · **[OS factory](#operative-systems)** · **[Tools](#the-toolchain)** · **[Discord](#discord-is-the-cockpit)** · **[Filesystem](#clean-by-construction)** · **[Atlas](atlas.md)**

> [!IMPORTANT]
> **Current posture: alpha / repository candidate, release line 11.12.** The supported foundation targets `READY_FOR_SETUP`, not a fully operational AI workforce. External accounts, live chat, OS execution, recovery and provider acceptance need their own evidence. See [readiness](#readiness-without-the-fine-print) and the [deep audit](docs/audit/2026-09-05-station-deep-audit.md). Source is publicly readable; **[all rights reserved](LICENSE.md)**, not an open-source license.

## Why Station

An agent can run a command. An operational system also needs to know **whose project it is, which identity may act, where the work belongs, and what proves it succeeded.**

- **A place for everything.** Hosts run Zones; Zones own identities and runtime state; Projects own repos, knowledge, worktrees, credentials and evidence.
- **One execution engine.** Hermes provides profiles, sessions, delegation, Skills, Kanban, hooks and tools. Station builds around it, not a competing scheduler.
- **AI departments, not loose prompts.** Each OS packages a Director, specialists, workflows, provider routes, evaluations and recovery instructions.
- **Chat as the cockpit.** Direct work through Hermes messaging, with Station's Discord progress cards and protected setup flows. Chat is the interface, not the source of truth.
- **Evidence before “done.”** Plans, execution reports, tests, Doctor and external readback have different meanings. Acceptance is a gate, not a confident sentence.

These are the architecture and workflow contracts. They are **not** a claim that every declared permission or live integration is already enforced; the [audit](docs/audit/2026-09-05-station-deep-audit.md) tracks those gaps.

## The whole system

<p align="center">
  <img src="docs/assets/readme/station-system-map.svg" width="800" alt="Human intent is governed by Station's configuration and placement contracts. Fleet places Zones on Hosts. Each Zone owns a Unix identity and Hermes runtime. Hermes runs OS teams using selected tools on Project-owned work. Evidence returns to Station. Other Hosts retain independent Zones.">
</p>

**Read the map from the outside in:** a **Host** is the machine; a **Zone** is its operational identity and isolation boundary; a **Project** owns the work; an **OS** supplies a team; **Hermes** runs it. **Fleet** describes the placement of those Zones across Hosts. **Station Control** records desired state, policies and evidence indexes.

| Piece | What it owns | What it does not replace |
| :--- | :--- | :--- |
| **Station kernel & Control** | Typed installation, layout, desired state, reconciliation and Doctor | Hermes reasoning, human authorization or external-provider truth |
| **Host & Fleet** | Linux machines, inventory and declared Zone placement | Zone identity or Project ownership |
| **Zone** | Unix identity, `HOME`, `HERMES_HOME`, credentials, memory and logs | A per-profile sandbox; profiles in one Zone share a trust domain |
| **Project & Workspaces** | Repositories, knowledge, task worktrees, resources, artifacts and evidence | A global dumping ground for all clients' data |
| **OS & Hermes** | Director, specialists, sessions, delegation, Skills and tools | A second Linux distribution or another competing scheduler |
| **Discord / other chat / AGK-TUI** | Human interaction and progress projections | The canonical state, permission or secret store |
| **Providers & integrations** | Model inference, CLIs, APIs, MCP and connected capabilities | Permission to change scope, read another Zone or bypass review |

### Why Hermes is the central brain

Hermes turns a scoped brief into executable work: it loads the OS profile, uses the selected model provider, delegates to specialists, calls available tools, maintains sessions and returns results. Station supplies the surrounding operating contracts: **where execution belongs, which identity owns it, what requires approval, and what evidence must survive it.**

“Central” means **one execution model**, not one omnipotent process holding every client's secrets. Each Zone gets its own Hermes home and runtime context. A model or CLI change must preserve the same [agent rules](rules/STATION_AGENT_RULES.md), Project paths and verification gates.

<details>
<summary><strong>A concrete example: a billing feature from Discord to deployment.</strong></summary>

You ask the DevOps Director for a billing feature in the development Project. Atlas scopes the mission; Architect defines the change; Forge works in the Project worktree; SRE checks runtime configuration; Sentinel verifies behavior; Release Engineer prepares the approved promotion. Hermes provides their execution and tool access. GitHub stores the code; the selected Convex, Clerk, Stripe and Vercel accounts provide application services. The Project retains the evidence. Discord shows progress and the result.

Production credentials do not enter development automatically. A passing test is not permission to deploy. This is the **intended accepted workflow**, not a claim that a fresh install has already performed it.

</details>

## Quickstart

Start on a **fresh Ubuntu/Debian VPS** with systemd, `apt-get`, network/DNS access, Git, and distribution Python **3.11+**. Use a **non-root user with sudo**; run your coding agent as that user. Review [installation](INSTALL.md) and [security](SECURITY.md) first. Other operating systems are not supported Host targets by this installer.

```bash
git clone --branch main --single-branch https://github.com/agentik-os/agentik-station.git
cd agentik-station

# Inspect the repository before touching the Host.
./station doctor --repo

# Read-only eligibility checks + kernel plan + selected bootstrap operations.
./bootstrap.sh --mode full --with-ai-stack --plan

# Revalidate, review the plan again, then explicitly confirm installation.
sudo ./bootstrap.sh --mode full --with-ai-stack
```

**What happens next:** the bootstrap prepares the operator account, pinned toolchain, Hermes, selected dependencies, Station filesystem, Zones, desired OS declarations and Doctor receipts. A successful foundation stops at `READY_FOR_SETUP`. Continue through **[SETUP.md](SETUP.md)** to enroll accounts and verify real workflows.

Do not add `--yes` before reviewing the plan. `--with-ai-stack` installs or stages optional components; it does not authenticate services, activate every OS or run security scans.

### From a clean VPS to a verified mission

<p align="center">
  <img src="docs/assets/readme/station-install-flow.svg" width="800" alt="Fresh VPS installation proceeds through read-only preflight, review and confirmation, bootstrap dependencies, exact-spec kernel apply, and READY_FOR_SETUP. The human then enrolls providers and chat; installed OS profiles and a real fresh-session mission require separate verification.">
</p>

| Gate | What actually happens | What unlocks the next step |
| :--- | :--- | :--- |
| **01 · Inspect** | Check supported Linux/CPU, repository integrity, existing operator identity and managed targets; compile a typed InstallSpec | A valid plan; no conflicting checkout, symlink target or changed same-version release |
| **02 · Approve** | Show the kernel plan and selected account, dependency and service operations | Your confirmation; the apply invocation uses its exact reviewed InstallSpec |
| **03 · Prepare** | Create `agk-station`; prepare Tailscale, pinned tools, Hermes and selected resources | Successful selected tool stages—not just a copied repository |
| **04 · Apply** | Apply the reviewed InstallSpec: Station layout, identities, Zones and desired state | Full Doctor and a kernel `READY_FOR_SETUP` receipt |
| **05 · Private setup** | Enroll the human-owned Tailnet and verify the private setup route | Correct Tailnet identity and protected access; no public fallback |
| **06 · Accounts & OS** | Connect providers and the first bot; install an OS, reconcile profiles and bind its Director | Scoped account readback, profile Doctor and the intended chat route |
| **07 · Accept** | Run a real mission; inspect artifacts, permissions, fresh-session/restart behavior and applicable recovery checks | Evidence for the specific capability you intend to use |

An unenrolled Tailnet leaves the local setup broker waiting for enrollment; it must not be presented as a working private URL. A failed later bootstrap stage also does not become successful merely because the kernel previously emitted `READY_FOR_SETUP`.

<details>
<summary><strong>Prefer to hand this to your coding agent? Copy this brief.</strong></summary>

```text
Install and set up Agentik Station from:
https://github.com/agentik-os/agentik-station

Work as my non-root sudo user. Clone main with --single-branch.
Read AGENTS.md, atlas.md, SECURITY.md, INSTALL.md, SETUP.md and AI_INSTALL_PROMPT.md.
Inspect the VPS and run repository Doctor. Show the plan before mutation.
Run: ./bootstrap.sh --mode full --with-ai-stack --plan
After my approval, run: sudo ./bootstrap.sh --mode full --with-ai-stack
Run full Doctor, status, module status and toolchain checks.
Continue through external setup one gate at a time using secure provider flows.
Never request secrets in chat, command arguments or Git.
Report what is verified, what remains untested and exactly what I must do next.
Do not label the system OPERATIONAL without the applicable acceptance evidence.
```

The canonical, more detailed handoff is **[AI_INSTALL_PROMPT.md](AI_INSTALL_PROMPT.md)**. A coding agent can automate installation steps; it cannot invent your accounts, grant itself consent or create Discord bot tokens on your behalf.

</details>

<details>
<summary><strong>Choose a smaller install, a team Host or an explicit plan/apply workflow.</strong></summary>

Choose **one** bootstrap mode for a fresh Host:

```bash
# Operator / Agentik Host; optional AI services are not all staged.
sudo ./bootstrap.sh --mode full

# Company Host; System foundation + an Organization Zone.
sudo ./bootstrap.sh --mode team --organization organization-alpha --project platform
```

Default bootstrap still includes the Hermes voice/messaging layer, Parakeet, ScrapeGraphAI and Crawl4AI. Deliberate opt-outs are documented in [INSTALL.md](INSTALL.md).

For lower-level control, `./station plan` and `sudo ./install` expose the typed kernel; `./station.sh bootstrap` wraps plan/confirmation/apply with one shared InstallSpec. These are not substitutes for the full dependency bootstrap. See the [installation workflows](INSTALL.md).

**Existing Host?** Do not overwrite an immutable release with different content under the same version. Read the [post-audit migration instructions](INSTALL.md#security-assessment-resource-and-post-audit-migration); OS profile upgrades currently require supervised configuration reconciliation.

</details>

## The mission circuit

**Intent in. Evidence out.** The animated circuit above is an architecture illustration, not a live status display. Follow a representative mission below; each stage expands into the corresponding ownership and verification contract.

> **Example brief:** “Build the billing flow for this Project, prepare a preview, and show me the evidence before production.”

**[01 Scope](#mission-01)** → **[02 Plan](#mission-02)** → **[03 Execute](#mission-03)** → **[04 Verify](#mission-04)** → **[05 Accept](#mission-05)**

<a id="mission-01"></a>
<details>
<summary><strong>01 / Scope — a message becomes owned work.</strong></summary>

Resolve the human principal, Host, Zone, Project, environment and requested capability. The OS Director receives the brief through the owning Hermes profile. An unresolved account or production target is a reason to stop, not guess.

**Contract:** [Zone and credential boundaries](SECURITY.md#zone-boundaries). **Expected output:** explicit scope and acceptance criteria. Discord remains a projection of the mission, not its authority store.

</details>

<a id="mission-02"></a>
<details>
<summary><strong>02 / Plan — Hermes gives the work a graph and an owner.</strong></summary>

Probe available tools and scoped accounts. The Director selects specialists; the team defines dependencies, the workspace, the verification owner and human approval gates. Reuse existing code and Hermes-native capabilities before adding another dependency.

**Contract:** [universal agent rules](rules/STATION_AGENT_RULES.md). **Expected output:** a reviewed Plan First graph, not execution disguised as a plan.

</details>

<a id="mission-03"></a>
<details>
<summary><strong>03 / Execute — specialists work inside the owning Project.</strong></summary>

Hermes runs persistent profiles or delegates bounded work. Forge works in a Project worktree; selected CLIs, APIs, MCP or Composio connections supply capabilities. Development uses its own credentials. A prepared preview or patch is an executor result, not proof of success.

**Contract:** [DevOps OS](os/devops/README.md). **Expected output:** artifacts, logs and an execution report linked to the mission. Profiles in one Zone share a Unix trust domain; separate roles alone do not create a security sandbox.

</details>

<a id="mission-04"></a>
<details>
<summary><strong>04 / Verify — “the command succeeded” is not the finish line.</strong></summary>

Run the relevant tests, Doctor, review and actual external readback. A preview needs its rendered behavior checked; a provider action needs the correct account and observed result. Sentinel's review is a workflow separation, not automatically an isolated security principal.

**Contract:** [verification engineering](docs/engineering/02_VERIFICATION_ENGINEERING.md). **Expected output:** evidence that agrees with the claimed outcome, or a precise failure and next repair action.

</details>

<a id="mission-05"></a>
<details>
<summary><strong>05 / Accept — authority stays outside the model.</strong></summary>

Production or destructive actions require the policy-defined human authorization. After the applicable gates pass, record acceptance and report the result through the human interface. Learning candidates are reviewed before promotion; a chat message cannot authorize itself.

**Contract:** [setup and fresh-session acceptance](SETUP.md). **Expected output:** an accepted outcome, or an honest lower readiness state. This walkthrough is a contract illustration, not a recorded production run.

</details>

**The whole model in one line:** Station governs → Hermes orchestrates → OS teams work → Projects retain the assets → verification feeds the next decision.

## Operative Systems

An **Operative System (OS)** is an installable AI department, not another Linux distribution. It bundles a Nano Director, a specialist NanoTeam, knowledge, ordered Skills, tools, workflows, memory policy, evaluations and recovery contracts.

<p align="center">
  <img src="docs/assets/readme/station-os-map.svg" width="800" alt="Canonical OS source compiles into a versioned Hermes distribution. Inside the owning Zone, a Nano Director coordinates specialist Hermes profiles using the team's skills, tools, knowledge, evaluations and recovery contract. Their work belongs to the assigned Project.">
</p>

### Inside an OS

| Contract | Purpose | Hermes connection |
| :--- | :--- | :--- |
| **Director & NanoTeam** | One accountable lead; bounded specialist responsibilities | Native profiles, sessions and delegation |
| **Knowledge & ordered Skills** | Domain context and reusable operating procedures | Profile context and Skills; canonical source stays in `os/` |
| **Workflows & programs** | Plan First graph, deterministic operations and handoff rules | Tools, hooks and native task mechanisms |
| **Integration & provider routes** | Which model, CLI, MCP, API or connected account serves a capability | Explicit configuration and scoped credentials; never secrets baked into a package |
| **Memory policy** | What can persist, where, for whom and how long | Zone-owned runtime state and selected memory services |
| **Evaluations & recovery** | What proves success; how to detect and repair failure | Tests, Doctor, readback and fresh-session acceptance |
| **Human interface** | Director bot, primary channel, commands and progress | Hermes messaging; Station-specific presentation where supported |

### How Builder makes one

**Brief → Librarian research → OS design → canonical package → Hermes distribution → installation → acceptance.** Librarian gathers verified sources, operator knowledge and contrary evidence. Builder's Director delegates domain scoping, architecture, programs, integrations, tests, evaluations, Discord experience, security and recovery. Independent review checks the complete package before it is treated as installable.

The compiler translates those contracts into Hermes-native distributions; it does not start a new orchestrator. Published artifacts live at `/opt/station/os-distributions/<zone>/<project>/<os>/<version>/`. They are immutable outputs—not a second editable OS source. See [Builder](os/builder/README.md) and the [native mapping](docs/builder/03_HERMES_NATIVE_MAPPING.md).

| OS source | Its job |
| :--- | :--- |
| [Station Maintainer](os/station-maintainer/README.md) | Inspect Station and Hermes changes; prepare maintenance and compatibility work. |
| [Discord Bootstrap](os/discord-bootstrap/README.md) | Define and prepare the guild, channels, bot bindings and human-facing control surface. |
| [Fleet Operator](os/fleet-operator/README.md) | Coordinate Host placement, remote bootstrap and observed infrastructure state. |
| [Librarian](os/librarian/README.md) | Turn sources, operator knowledge and contrary evidence into verified working knowledge. |
| [Builder](os/builder/README.md) | Turn a capability brief and Librarian research into a versioned OS package for Hermes. |
| [DevOps](os/devops/README.md) | Organize architecture, implementation, operations, verification and release work. |

Canonical source lives only in `os/`. The compiler produces Hermes Profile Distributions; installation, bindings, profile Doctor and fresh-session acceptance are separate steps. The [catalog](os/CATALOG.json) currently marks these packages **`INSTALLABLE` / `NOT_INSTALLED`**, not running teams.

> [!IMPORTANT]
> **Current activation limits:** Project-scoped OS artifacts currently meet Zone-scoped profile names, so repeating the same OS across Projects can collide. Generic platform setup selects the Zone gateway, not automatically the intended OS Director. Profile installation retries and durable runtime acceptance also need hardening. Do not infer multi-Project or multi-bot readiness from the diagrams; see the [VPS workflow review](docs/audit/2026-09-05-vps-workflow-review.md).

### Meet the DevOps team

```mermaid
flowchart LR
    Atlas[Atlas · Director] --> Architect[Architect · Scope and design]
    Architect --> Forge[Forge · Implementation]
    Architect --> SRE[SRE · Runtime and operations]
    Forge --> Sentinel[Sentinel · Verification]
    SRE --> Sentinel
    Sentinel --> Release[Release Engineer · Promotion gates]
    Sentinel -. repair loop .-> Forge
    Release --> Evidence[Evidence and readback]
    Evidence --> Atlas
```

For a **Strix mission**, Architect scopes sanitized source, a human approves disclosure and the disposable LAB, SRE runs the approved job, Sentinel triages, Forge fixes, and independent retesting precedes release. Strix is a tool under Hermes—not a second Station Director. Read the [team and LAB boundary](resources/strix/README.md) before enabling it.

## The toolchain

**One catalog. Explicit ownership. No “installed means connected” shortcuts.** Exact reviewed versions live in [versions.lock](config/versions.lock), with resources in [CATALOG.json](resources/CATALOG.json) and optional components in [stack.yaml](config/deps/stack.yaml).

| Layer | Components | Installation / activation boundary |
| :--- | :--- | :--- |
| **Execution** | Hermes; Python, AI Python, Node.js, npm, uv | Pinned runtimes; Hermes configuration and sessions belong to each Zone. |
| **Operator tools** | GitHub CLI, Vercel CLI, Codex CLI, Composio CLI, shadcn CLI, AGK-TUI | Bootstrap installs tools; account login and scoped readback are separate. |
| **Chat & voice** | Hermes messaging, Discord, discord.js, OpenAI audio, local Parakeet | Default voice layer and isolated SDK; bot tokens, audio keys and live round trips need setup. |
| **Web extraction** | [Crawl4AI](resources/crawl4ai/README.md), [ScrapeGraphAI](resources/scrapegraphai/README.md), Playwright | Default web resources. Station adapters fetch public HTML **without JavaScript**; Crawl4AI yields Markdown, ScrapeGraphAI uses a Zone key for structured extraction. |
| **Security assessment** | [Strix](resources/strix/README.md) | Optional CLI, included with `--with-ai-stack`. No automatic scans or Docker grants; execution needs an accepted disposable LAB and human approval. |
| **Memory & observability** | Honcho, Hindsight, Langfuse | Optional packages or source are staged; service configuration, retention and isolation need acceptance. |
| **Engineering & desktop** | Ponytail, TigerVNC | Optional capability setup; installed source is not a running or publicly exposed service. |
| **Private enrollment** | Tailscale and Station's guided setup broker | Human Tailnet enrollment first; private setup links afterwards. No public fallback. |

Explore the [dependency guide](docs/dependencies/STACK.md) for each component's role and activation gate. Hermes remains the only messaging gateway; Composio and discord.js extend capabilities rather than owning chat sessions.

### A preferred stack, not a required stack

**Next.js · React · Convex · Vercel · Clerk · Stripe · Tailwind CSS · shadcn/ui · Lucide**

The [web-product recipe](resources/stacks/web-product/README.md) provides the default. Other stacks are welcome when the Project records the choice, ownership and verification. Shared CLIs live in the operator toolchain; UI components, icons, framework dependencies and lockfiles live in the **owning Project repository**, never a global application dependency dump.

## Discord is the cockpit

**[Join the Agentik OS community → discord.gg/agentik-os](https://discord.gg/agentik-os)**

The community server is separate from your private Station deployment. Your own guild, accounts, tokens and permissions remain under your control.

<p align="center">
  <img src="docs/assets/readme/station-chat-map.svg" width="800" alt="A human uses Discord or another Hermes transport. Identity, Zone and Director bindings lead to the Hermes OS team and Project work. For account enrollment, the bot provides a short-lived private Tailscale link to a one-use setup form or allowlisted provider flow. Secrets do not belong in chat.">
</p>

The intended topology is **one installed OS → one Nano Director → one dedicated bot identity and primary channel**. Specialists collaborate inside Hermes; public bots should not create recursive bot-to-bot conversations.

1. **Enroll the first bot and Tailnet as the human owner.** A bot token cannot create more Discord applications or mint their tokens.
2. **Bind the bot to its Zone and OS.** Verify channel permissions, commands and message readback in a test guild. Remove any temporary bootstrap administrator elevation.
3. **Use guided setup for subsequent accounts.** After enrollment, short-lived, one-use private Tailnet links can open secret forms or allowlisted OAuth/device flows. Never paste credentials into Discord.
4. **Follow semantic mission progress.** Station's Discord experience is designed around editable progress cards, actions and linked evidence rather than raw tool chatter.

Prefer Telegram, Slack or another supported platform? Use the [Hermes platform setup](docs/dependencies/HERMES_PLATFORMS.md). Transport support does not imply identical Station card rendering; each surface needs its own live acceptance. [Voice and protected setup guide →](docs/dependencies/VOICE_AND_GUIDED_SETUP.md)

### Voice follows the same ownership rules

The default setup installs Hermes voice/messaging support, configures OpenAI audio defaults and prepares local Parakeet. Transcription becomes input to the same scoped Hermes session; text-to-speech turns its response into audio. OpenAI keys, local service health, actual Discord audio delivery and the return trip remain separate setup checks. Installing the libraries is not evidence that a bot can hear and speak in your guild.

The first human enrollment remains unavoidable. Afterwards, guided links and provider-native authentication can make routine setup chat-led. **An administrator bot is not an unrestricted sudo endpoint**; broad operator sudo is a current security concern, not a model permission to execute any incoming message.

## Clean by construction

One **Station namespace**, with Linux responsibilities kept in their proper places. `/srv/station` is the human navigation root—not a replacement for the filesystem hierarchy.

<p align="center">
  <img src="docs/assets/readme/station-filesystem-map.svg" width="800" alt="Station uses Linux filesystem responsibilities: etc for desired state, opt for immutable software, srv for human navigation and Projects, var/lib for runtime state, var/log for logs, var/backups for recovery staging and run for ephemeral files. Each Zone owns its Projects and each Project owns its work.">
</p>

```text
/etc/station          Desired state and approved policy
/opt/station          Immutable releases, OS distributions and shared tools
/srv/station          Human navigation, Zones, Projects and shared resources
/var/lib/station      Hermes state, connector state, memory and receipts
/var/log/station      System and per-Zone logs
/var/backups/station  Local recovery staging; not proof of off-Host backup
/run/station          Ephemeral runtime files and locks
```

Each Zone has its own Unix identity and `HERMES_HOME`. Each Project owns `repos/`, `docs/`, `knowledge/`, `resources/`, `worktrees/`, `credentials/`, `artifacts/` and `evidence/`. Local versus remote is Host placement, not a different tree.

<details>
<summary><strong>Open the full navigation tree and source-code map.</strong></summary>

The human-facing tree groups responsibility; authoritative configuration and runtime data remain at the FHS paths above.

```text
/srv/station/
└── 2_ZONES/
    ├── 1_SYSTEM/          Station services and control responsibilities
    ├── 2_PRIVATE/         Operator-private work
    ├── 3_AGENTIK/         Agentik-owned development
    ├── 4_ORGANIZATIONS/   Organization environments and Projects
    ├── 5_PROJECTS/        Independent Project environments
    ├── 6_FACTORY/         OS/package creation with sanitized fixtures
    └── 7_LAB/             Explicit experimental/security boundaries
```

An owning Project contains these responsibilities (not a second global filesystem):

```text
Project/
├── repos/                 Source repositories and their dependency lockfiles
├── docs/ + knowledge/     Decisions, specifications and verified context
├── resources/             Selected recipes, assets and capability references
├── integrations/          Non-secret connector definitions and account scope
├── credentials/           Zone-protected, Project-scoped credential material
├── workspaces/ + worktrees/ Isolated task working areas
├── state/                 Project state and runtime references
├── artifacts/ + evidence/ Outputs, checks, acceptance and external readback
└── ops/                   Operations and recovery instructions
```

| Repository source | Responsibility |
| :--- | :--- |
| `src/agentik_station/` | Typed CLI, installer, filesystem safety, Doctor and lifecycle logic |
| `bootstrap.sh` + `scripts/` | VPS dependency bootstrap, operator tools and service setup |
| `config/` + `contracts/` + `specs/` | Reviewed pins, desired defaults, schemas and machine-readable contracts |
| `os/` | The only canonical OS package sources |
| `resources/` | Reusable tools, SDK recipes and preferred-stack guidance |
| `components/agk-tui/` | Terminal control surface and Station's Hermes integration |
| `runtime/` + `modules/` | Runtime templates and explicit module maturity |
| `tests/` + `.github/workflows/` | Contract, security, integration and acceptance checks |
| `docs/` + `atlas.md` | Architecture explanations, operating guides and known gaps |

No Project work under `/root`, arbitrary home folders or shared credential dumps. Temporary test fixtures may use a temporary directory; production work still belongs to its Project. Shared shadcn CLI is a tool; generated shadcn components, Lucide icons and application packages belong in the Project repository.

</details>

Hermes, coding CLIs, providers and humans share the same **[Station agent rules](rules/STATION_AGENT_RULES.md)**. A model provider supplies cognition—not permission to bypass ownership, filesystem layout or approval. See the [full architecture](ARCHITECTURE.md) and [atlas](atlas.md).

<details>
<summary><strong>Everyday operator commands after installation.</strong></summary>

```bash
station status                  # Observed Host state
station doctor --full           # Installed-Host checks
station module status           # Maturity and next repair actions
station deps toolchain-check    # Observed tools versus reviewed pins
station resource list           # Reusable resource catalog
station resource stack-plan     # Inspect the preferred Project stack
station tui                     # Open AGK-TUI (also available as agk)
```

AGK-TUI opens Hermes, Codex, Claude Code and terminal sessions; it is a control
surface, not a replacement execution engine. See [the AGK-TUI integration guide](INTEGRATION_AGK_TUI.md).
Account enrollment and external actions still follow [SETUP.md](SETUP.md).

</details>

## Readiness without the fine print

<p align="center">
  <img src="docs/assets/readme/station-evidence-loop.svg" width="800" alt="An executor reports a result, an independent verification step checks it, external readback confirms the actual target, and an authorized acceptance gate records the outcome. Failed checks return a precise repair action. Repository CI is not VPS health; installation is not operational acceptance.">
</p>

The CI badge reports **repository checks**, not the health of your VPS. The [module catalog](modules/catalog.json) records maturity and next repair actions; deployed readiness requires observed evidence.

| What the repository provides | What you still need to prove on a deployment |
| :--- | :--- |
| Typed installer, Linux layout, Zone identities, immutable releases and Doctor | Fresh supported-Host installation, real UID isolation, reboot and service readback. |
| OS compiler, profiles, platform and provider setup paths | Live Hermes execution, correct account scope, bot interactions and fresh-session acceptance. |
| Web, voice, memory, observability and security integrations | The selected service's real behavior, data boundaries, credentials, costs and failure recovery. |
| Release metadata, update tooling and recovery contracts | Compatible upgrades, code/state rollback and a destructive off-Host restore rehearsal. |

> [!WARNING]
> The bootstrap operator currently has broad passwordless sudo. A Hermes profile is **not** a filesystem sandbox, and role descriptions are **not** complete tool ACL enforcement. Strix's Docker-capable worker belongs on a separate disposable LAB Host. Review [SECURITY.md](SECURITY.md) and the [remaining audit decisions](docs/audit/2026-09-05-station-deep-audit.md#remaining-findings-and-decisions--not-silently-implemented) before granting access to real data or production.

**Updates are explicit about their limits.** Bootstrap enables a weekly Hermes updater by default, with backup, Doctor and gateway observations; `--skip-hermes-auto-update` opts out. This is not yet the complete canary/ring-promotion or verified code-and-state rollback workflow. Existing-profile upgrades remain supervised. See [INSTALL.md](INSTALL.md#optional-dependency-stack--hermes-auto-update).

### What these diagrams promise

Every map is a **repository-owned, self-contained SVG** with a text equivalent nearby. The signal animation is decorative, runs briefly and respects reduced-motion preferences; the complete architecture remains visible without motion. GitHub clients may display a static frame. These are architecture explanations, **not live telemetry**, permission enforcement proofs or deployment acceptance receipts.

The [VPS workflow review](docs/audit/2026-09-05-vps-workflow-review.md) separates the repaired installer defects from the remaining OS-instance, routing, resumability and live-acceptance work. That distinction is part of the product, not fine print.

## Find your next step

| I want to… | Start here |
| :--- | :--- |
| Understand the entire system | [The atlas](atlas.md) |
| Install a fresh VPS | [Installation](INSTALL.md) · [AI operator brief](AI_INSTALL_PROMPT.md) |
| Connect accounts, chat and voice | [Setup gates](SETUP.md) · [Voice & guided setup](docs/dependencies/VOICE_AND_GUIDED_SETUP.md) |
| Build or understand an OS | [Builder](os/builder/README.md) · [Hermes-native mapping](docs/builder/03_HERMES_NATIVE_MAPPING.md) |
| Inspect the DevOps workflow | [DevOps OS](os/devops/README.md) · [Strix team](resources/strix/README.md) |
| Evaluate security and maturity | [Security contract](SECURITY.md) · [Deep audit](docs/audit/2026-09-05-station-deep-audit.md) |
| Browse the source and verification rules | [Documentation index](docs/README.md) · [Agent contract](AGENTS.md) · [Changelog](CHANGELOG.md) |

## Community and development

Bring architecture questions, workflow ideas and reproducible feedback to **[Discord](https://discord.gg/agentik-os)** or the repository's [issues](https://github.com/agentik-os/agentik-station/issues). Keep tokens, private source, client data and security-sensitive details out of public channels. Coordinate privately with the maintainers before sharing sensitive findings.

`main` is the only canonical, distributable branch. Any approved temporary implementation branches are removed after merge; there is no long-lived `develop`, release or vendor branch.

For authorized development, read [AGENTS.md](AGENTS.md) and run the relevant checks plus repository Doctor. GitHub Actions, Station tests and Builder/Librarian gates are the verification system. **CodeRabbit or any other third-party review bot is optional** and is never a runtime or installation dependency.

### Built on excellent foundations

Station builds around [Hermes Agent](https://github.com/NousResearch/hermes-agent) and integrates projects including [Crawl4AI](https://github.com/unclecode/crawl4ai), [ScrapeGraphAI](https://github.com/ScrapeGraphAI/Scrapegraph-ai) and [Strix](https://github.com/usestrix/strix). See [THIRD_PARTY.md](THIRD_PARTY.md) for upstream acknowledgments and license boundaries. Mentioning a project does not imply endorsement or affiliation.

**License:** [publicly readable source, all rights reserved](LICENSE.md). Obtain a separate written license before copying, modifying, distributing or operating Station; installation instructions do not themselves grant that permission. Third-party components retain their own licenses.

---

<p align="center">
  <strong>Your infrastructure. Your teams. Evidence before done.</strong><br>
  <a href="https://discord.gg/agentik-os">Join Discord</a> · <a href="atlas.md">Explore the atlas</a> · <a href="#agentik-station">Back to top</a>
</p>
