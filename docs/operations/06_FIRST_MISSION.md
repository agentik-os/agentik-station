# From a clean VPS to the first verified mission

This is the operating sequence for Station software **11.13**. It uses one execution
engine—Hermes—and explicit ownership at every step. Commands that change a Host
require the human's reviewed authorization. Examples use a synthetic development
Project; they do not authorize production deployment or active security scanning.

## 1. Establish the foundation

On supported Ubuntu/Debian with systemd and distribution Python 3.11+, start in a
normal non-root sudo user's workspace:

```bash
git clone --branch main --single-branch https://github.com/agentik-os/agentik-station.git
cd agentik-station
./station doctor --repo
./bootstrap.sh --mode full --with-ai-stack --plan
# Review the plan, then confirm the actual invocation:
sudo ./bootstrap.sh --mode full --with-ai-stack
sudo station setup --json
```

`--with-ai-stack` is optional staging of the larger resource set. The default still
installs Hermes, messaging/voice support and the two web-extraction resources.
Selected packages are not automatically authenticated or accepted. Review the
broad operator-sudo posture in [SECURITY.md](../../SECURITY.md).

The bootstrap records its own stages separately from the kernel's receipt. If a
stage fails, read the named repair action before another attempt. `--yes` cannot
silently bypass an incomplete attempt. `--acknowledge-incomplete <attempt-id>` is
an explicit reviewed restart, not automatic resume. See [INSTALL.md](../../INSTALL.md).

## 2. Choose a Zone and create its first Project

```bash
sudo station setup --json
```

Choose a reconciled local Zone from `choices.zones`. Full/core creates System,
Private, Agentik, Factory and LAB Zones, but does not guess their Projects. For
example, the default Agentik development Zone is `dev`:

```bash
sudo station project create --zone dev --id first-mission --plan
sudo station project create --zone dev --id first-mission
sudo station setup --zone dev --project first-mission --os devops-os
```

The new Project gets the canonical repositories, docs, knowledge, resources,
credentials, workspaces, worktrees, artifacts, evidence and operations directories,
plus Station rules for Hermes and coding executors. Runtime state belongs in its
Zone's `/var/lib/station` namespace. Existing Project roots are never replaced by
this command. A failed/interrupted partial creation needs inspection before repair.

The same command works for a System or Factory Zone; explicitly choose a suitable
Project name and OS. This does not give System responsibilities access to unrelated
Project secrets. One native OS team is currently bound to one Project per Zone;
installing that same OS for another Project is refused pending an explicit instance
or tenancy migration. Different roles in the same Zone share its Unix trust domain.

## 3. Install the owned OS team

```bash
sudo station os install --zone dev --project first-mission --id devops-os
sudo station setup --zone dev --project first-mission --os devops-os --json
```

Canonical `os/` source compiles into an immutable Hermes distribution. The trusted
root-owned ledger binds its digest, Director, entire specialist team and Project.
The installer records each profile and reads back native installed metadata,
distribution content and critical Project configuration. A zero exit code without
the expected files is not successful installation.

If a later profile fails, the same install command preserves/read-backs completed
profiles and installs missing ones. It never forces a profile replacement. Changed
source under the same OS version, untracked profiles, tombstones, unsafe paths and
cross-Project reuse require explicit repair/migration. Your credentials, sessions
and customized provider settings are not an installer's disposable scratch data.

## 4. Configure the Director's model account

```bash
sudo station os setup --zone dev --id devops-os --plan
sudo station os setup --zone dev --id devops-os
```

This opens **Hermes' own provider/setup wizard for Atlas**, not the operator's
global profile. The Unix identity and base Hermes home remain those of `dev`;
Hermes selects Atlas's native profile. Credentials stay within that ownership.
No API token is accepted as a Station command argument or stored in an OS bundle.

Use the account and least-privilege scope needed for this synthetic mission. A
binary, config file or completed wizard is not proof of a usable paid account.
The setup report keeps provider authorization unknown until separate live evidence.

## 5. Enroll the private connection and chat bot

The human owns the first Tailscale enrollment, creates the Discord application,
authorizes the bot to a test guild and retains control of token rotation. A bot
cannot mint its own platform identity or authorize its own privileges.

```bash
sudo tailscale up
sudo station platform setup --zone dev --os devops-os --platform discord --plan
sudo station platform setup --zone dev --os devops-os --platform discord
sudo station os verify --zone dev --id devops-os
sudo station platform install --zone dev --os devops-os
sudo station platform start --zone dev --os devops-os
sudo station setup --zone dev --os devops-os --probe --json
```

`--os devops-os` resolves Atlas through the trusted installation ledger. Omitting
`--os` intentionally selects the Zone's `default` profile; it never inherits a
sticky active profile. Configure the intended guild/channel and human allowlist,
then prove the actual route. Telegram/Slack use the same selection mechanism with
their own Hermes adapter and acceptance checks; Discord presentation is not
automatically identical on every platform.

`--probe` reads only the selected native systemd user service with a bounded
timeout. It does not invoke Hermes startup, authenticate, expose credentials, enable
linger, install or start a service. The report's integrity checks read native profile
configuration, not `.env`, authentication or session files. Native `station platform status/doctor` are
separate explicit commands: upstream Hermes startup can synchronize bundled Skills.

After initial enrollment, enable the private guided-setup broker as described in
[SETUP.md](../../SETUP.md). Its existing secret forms write **Zone-base** credentials;
they do not automatically provision every Director's private profile or bot token.
Use the selected native wizard for per-Director enrollment. Never paste secrets
into a Discord message, public link, repository or evidence report.

## 6. Run a complete synthetic mission

Ask Atlas, through the actual test channel:

> In the first-mission Project, prepare a tiny greeting function and a failing
> regression test. Show the plan. Have Forge fix the test, ask Sentinel to verify
> it independently, and report the evidence. Do not deploy or use production data.

Verify the following with fresh evidence:

1. The channel reaches **Atlas in `dev`**, not another profile or Zone.
2. The work appears only under the owning Project repository/worktree.
3. Forge's output is independently checked; failure returns a repair step.
4. Atlas links the test/artifact evidence without publishing credentials.
5. An unauthorized user and a wrong channel cannot initiate the mission.
6. After gateway restart, a fresh session repeats the workflow without hidden context.

Record the package, configuration, scoped account and artifact identities alongside
the observed result. Local `station os verify` is durable **profile Doctor evidence**,
not automatic acceptance of this live mission. The current setup report does not
claim or mint live mission acceptance records.

## 7. Grow only the capabilities you have accepted

Now configure the Project's required GitHub, Vercel, Composio, Convex, Clerk, Stripe
or other connections through their scoped native flows. Shared CLIs are tools;
framework packages, shadcn components, Lucide icons and lockfiles live in the Project
repository. Add memory/tracing only with explicit retention and data boundaries.

Voice needs its own OpenAI and Parakeet round trips. Fleet needs real remote identity
and readback. Strix needs an approved disposable LAB and target boundary. Production
needs explicit human authorization and verified recovery, including an off-Host
restore rehearsal. Success in the greeting mission does not accept these by extension.

## What persists—and what it means

| Record | Owner | Meaning |
| :--- | :--- | :--- |
| `/etc/station/…` | Station root authority | Desired Host/Zone state and policy |
| `/var/lib/station/bootstrap/attempts/…` | Station root authority | Reported stages of one bootstrap attempt, not an all-system transaction |
| `/var/lib/station/registry/os/<zone>/<os>.json` | Station root authority | Bound bundle/team/Project, per-profile installation and local Doctor evidence |
| Zone Hermes profile | Owning Zone Unix identity | Provider configuration, sessions, runtime state and bot identity |
| Project `artifacts/` and `evidence/` | Owning Project within its Zone | Mission outputs and observed verification/readback |
| `station setup --json` | Generated read model | Current local observations and ordered next actions; not another state store |

Keep those boundaries intact when changing a model, CLI, chat provider or application
stack. The Chief AI Officer coordinates work through Hermes; model text does not
grant additional Linux or production authority.
