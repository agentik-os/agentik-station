# From a clean VPS to the first verified mission

This is the **11.14 client-owned instance workflow**. Hermes is the execution
engine; the client owns its environment Zones, OS instances and Projects. These
commands describe the operating sequence, not evidence that a live VPS or paid
integration has already passed acceptance. Use synthetic development data.

## 1. Establish the client's foundation

On a fresh supported Ubuntu/Debian systemd Host, use a normal non-root sudo user's
workspace. Choose one reviewed Host mode; this example creates the `acme-dev`
ORGANIZATIONS Zone, not a Project:

```bash
git clone --branch main --single-branch https://github.com/agentik-os/agentik-station.git
cd agentik-station
./station doctor --repo
./bootstrap.sh --mode team --organization acme --plan
# Review the plan, then confirm the actual invocation:
sudo ./bootstrap.sh --mode team --organization acme
sudo station setup --json
```

For an existing installation, select an already reconciled matching client Zone;
do not rerun bootstrap merely to create an instance or Project. Full/core mode
creates Operator/Agentik/System/Factory/LAB Zones, not an arbitrary client's Zone.
`--with-ai-stack` is optional staging, not authentication or acceptance.

If bootstrap fails, inspect the stage receipt, repair the named problem and check
surviving installer processes. `--yes` cannot bypass an incomplete attempt;
`--acknowledge-incomplete <attempt-id>` is a reviewed fresh run, not automatic
resume. See [INSTALL.md](../../INSTALL.md) and [SECURITY.md](../../SECURITY.md).

## 2. Register the Organization's existing Zone

```bash
sudo station organization register --id acme --zone acme-dev --plan
sudo station organization register --id acme --zone acme-dev
sudo station organization show --id acme
```

Registration validates existing canonical ownership; it cannot relabel a Zone,
create Unix isolation or import a remote environment. Declare every intended
binding together in the initial registration, repeating `--zone` only for another
matching environment already reconciled locally. A different binding set cannot
be appended by rerunning registration. Production and other clients keep separate
Zones and scoped credentials.

## 3. Install the client-owned OS instance

```bash
sudo station os instance install --zone acme-dev --instance engineering \
  --organization acme --id devops-os
sudo station os instance show --zone acme-dev --instance engineering
sudo station setup --organization acme --zone acme-dev --instance engineering --json
```

This explicit install creates the instance's own workspace and Hermes home. It
does not require a Project. Canonical roles map through `role_profile_map` to native
Zone/instance/role identifiers; Atlas is the Director role, not a shared bare
profile name. The root-owned schema-3 ledger binds the package, bundle, complete
team, runtime roots and declared scope.

If your first mission needs a code Project instead of domain-only work, create it
**before** the install above, then include `--allow-project app` in that install:

```bash
sudo station project create --zone acme-dev --id app --plan
sudo station project create --zone acme-dev --id app
# Add --allow-project app to the chosen instance install command above.
```

Repeat `--allow-project` for additional existing intended Projects. This is a
routing/policy list, **not a filesystem sandbox**: Projects and instances share
the Zone UID. Do not change a bound instance's identity/scope by editing its ledger
or forcing a profile replacement. Partial installs require the recorded repair
action and unchanged-input readback; credentials and sessions are not scratch data.

## 4. Configure the instance Director's model account

```bash
sudo station os instance setup --zone acme-dev --instance engineering --plan
sudo station os instance setup --zone acme-dev --instance engineering
```

This opens Hermes' native provider wizard for this instance's mapped Director,
under the owning Zone UID and instance Hermes home. Enter secrets only through
the private native flow, never chat, command arguments, Git or an immutable bundle.
A completed wizard does not prove the correct paid account or capability scope.

## 5. Enroll private connectivity and the Director bot

The human enrolls Tailscale, creates/authorizes the Discord application for a test
guild and retains token rotation authority. One Director bot/primary channel is
the default per instance; specialists remain internal unless an explicit topology
justifies another external identity. A bot cannot mint more bot tokens.

```bash
sudo tailscale up
sudo station platform setup --zone acme-dev --instance engineering --platform discord --plan
sudo station platform setup --zone acme-dev --instance engineering --platform discord
sudo station os instance verify --zone acme-dev --instance engineering
sudo station platform install --zone acme-dev --instance engineering
sudo station platform start --zone acme-dev --instance engineering
sudo station setup --organization acme --zone acme-dev --instance engineering --probe --json
```

Configure the intended guild/channel and human allowlist, remove temporary
elevation, then prove the actual route. The wizard is not an automatic guild
provisioner. Slack/Telegram use the same instance selection with their own platform
and live acceptance checks.

`station setup` is a read-only report; `--probe` adds a bounded observation of the
selected systemd user service, not login, installation or gateway startup. Native
platform `status/doctor` are separate commands and upstream startup may synchronize
Skills. Profile configuration integrity is not account authorization.

The existing guided-setup broker targets **Zone-base** credential forms, not every
instance. Use the instance-aware native wizard for this Director. Private links
are bearer capabilities: do not forward them or paste secrets into chat/evidence.

## 6. Prove a complete synthetic mission

For the no-Project path, ask the Director through the actual test channel:

> Prepare a synthetic service-readiness checklist in the engineering instance
> workspace. Show the plan, delegate a bounded review, verify the result, and link
> the evidence. Do not inspect real client data, change services or deploy.

If `app` was explicitly allowed, a separate coding mission may ask Forge to add a
tiny greeting function and test in that Project, with Sentinel's independent
verification. Project source stays in its repository/worktree, not the OS package
or instance's domain workspace.

Verify with fresh evidence:

1. The channel reaches engineering's mapped Director in `acme-dev`, not another instance.
2. Domain output belongs to the instance workspace; Project output belongs to the selected Project.
3. Independent review checks the execution report; failure returns a repair step.
4. Evidence links expose no credentials or unrelated client data.
5. Unauthorized-user/wrong-channel requests are denied in live tests.
6. Restart and a fresh session reproduce the workflow without hidden context.

Record package/configuration/account/artifact identities and observed results.
Local `os instance verify` is full-team profile Doctor evidence, not automatic
acceptance of this live workflow. The setup report does not mint acceptance.

## 7. Grow only accepted capabilities

The full OS contract includes domain state/schema, views, workflows, programs,
connected accounts, governance, evidence and recovery—not just the team. Profile
installation does not automatically materialize or prove each declared app,
database, migration, automation or enforcement mechanism. Implement/configure and
accept each selected capability separately.

Enroll GitHub, Vercel, Composio or other connections in the correct client and
environment. Shared CLIs are tools; application dependencies and lockfiles remain
Project-owned. Voice, memory, Fleet, paid providers, Strix's disposable LAB and
off-Host restore/recovery each need their own acceptance. A successful checklist
or greeting mission does not accept them by extension.

## Records and legacy boundaries

| Record | Meaning |
| :--- | :--- |
| `/etc/station/organizations.d/` | Root-owned client ownership metadata for existing canonical Zones |
| `/var/lib/station/bootstrap/attempts/` | Reported bootstrap stages, not an all-system transaction |
| `/var/lib/station/registry/os-instances/<zone>/<instance>.json` | Root-owned schema-3 instance identity, role map, bundle, scope and local evidence |
| `<zone>/os/instances/<instance>/workspace/` | Instance-owned domain workspace |
| `<zone-state>/os-instances/<instance>/hermes/` | Zone-UID-owned instance configuration, profiles and runtime |
| Project `artifacts/` and `evidence/` | Separate Project outputs and verification/readback |
| `station setup --json` | Generated local read model, not another authority store |

Older `station os install/setup/verify` and gateway `--os` commands continue to
address legacy schema-2 Project-bound runtimes. They are not automatically migrated
or adopted by instance commands. Preserve their profiles, credentials and ledgers;
inspect and design migration explicitly. See the
[instance contract](../organization/05_OS_INSTANCES.md).
