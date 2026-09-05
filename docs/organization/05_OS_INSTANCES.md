# Client-owned OS instances

This is the 11.14 instance contract. It extends the runtime mapping of the
[locked OS contract](../builder/02_OS_CONTRACT_LOCKED.md); it does not reduce an OS
to its profiles or claim that all domain capabilities are implemented.

## Three objects, three owners

| Object | Owns | Does not contain |
| :--- | :--- | :--- |
| Reusable OS definition | Versioned domain expertise, outcomes, Director/team roles, Skills, programs, schemas, workflows, views, capability contracts, evals and recovery definitions | Client credentials, connected accounts, sessions or raw memory |
| Client-owned OS instance | Configured operating capability in one environment Zone: workspace, Hermes home, role mapping, domain runtime and evidence | The client Organization itself or every Project by default |
| Project | A bounded body of work: repositories, knowledge, integrations, worktrees, artifacts and evidence | The Organization's complete domain hierarchy |

The business model is **Organization → Macro Domain → Domain → OS**. The placement
model is **Organization → environment Zones → OS instances and Projects**. An
engineering instance can serve declared Projects; a finance or research instance
can perform domain work without inventing an application Project.

## Register ownership without relabeling a Zone

First reconcile the intended ORGANIZATIONS Zone through the reviewed Host workflow.
For a fresh client Host, for example, `bootstrap.sh --mode team --organization acme`
creates `acme-dev`. Organization registration does not create that Zone.

```bash
sudo station organization register --id acme --zone acme-dev --plan
sudo station organization register --id acme --zone acme-dev
sudo station organization show --id acme
```

Repeat `--zone` in the **initial registration command** for every already
reconciled matching environment on this Host, such as `--zone acme-prod`.
An existing registration cannot be extended by replaying a different binding set.
Do not imply that a remote Zone exists locally.
Registration is protected metadata at `/etc/station/organizations.d`; it validates
the existing canonical owner, category and identity. It cannot adopt a foreign
Zone, rename an ID, change a Unix user or move credentials. A conflict requires
inspection and an explicit migration design, not metadata editing to make it pass.

## Install and enroll an instance

```bash
sudo station os instance install --zone acme-dev --instance engineering \
  --organization acme --id devops-os
sudo station os instance show --zone acme-dev --instance engineering
sudo station os instance setup --zone acme-dev --instance engineering --plan
sudo station os instance setup --zone acme-dev --instance engineering
sudo station os instance verify --zone acme-dev --instance engineering
sudo station setup --organization acme --zone acme-dev --instance engineering --json
```

`install` is an explicit mutating operation, not a plan. If engineering work must
target existing Project `app`, declare `--allow-project app` at installation;
repeat the option for each intended Project. This list is declared routing/policy
scope, **not a filesystem ACL or sandbox**. Do not treat reinstalling an existing
instance with different scope as a migration procedure.

The definition's stable role IDs remain meaningful. `role_profile_map` records
each role's generated native profile ID, namespaced by **Zone + instance + role**.
For example, canonical `atlas` is the Director role; the running profile is the
mapped instance-specific ID, not a shared bare `atlas`. The whole persistent team,
not only the Director, receives this mapping. Use `show` and the explicit instance
selector rather than constructing names by hand.

Configure a worker's provider account through its canonical role selector:

```bash
sudo station os instance setup --zone acme-dev --instance engineering --role forge --plan
sudo station os instance setup --zone acme-dev --instance engineering --role forge
```

This selects the trusted mapped Forge profile, not a new OS or a copied login.

| Record or path | Authority and purpose |
| :--- | :--- |
| `os/` in the reviewed release | Only canonical editable package source; reusable and client-secret-free |
| `/opt/station/os-instance-distributions/<zone>/<instance>/<os>/<version>/` | Immutable compiled instance distribution |
| `/var/lib/station/registry/os-instances/<zone>/<instance>.json` | Root-owned schema-3 ledger: Organization, package/bundle, role map, runtime roots, allowed Projects and local verification |
| `<zone>/os/instances/<instance>/workspace/` | OS-owned human/domain workspace; not a second editable package source |
| `<zone-state>/os-instances/<instance>/hermes/` | Instance's Hermes runtime, native profiles, account configuration and sessions |
| `<zone>/projects/<project>/` | Separate Project-owned assets used only under explicit mission scope |

These paths separate lifecycle and naming, not Unix authority. Instances, members
and Projects inside a Zone share its UID. Hard client/environment isolation requires
separate Zones; dedicated production Hosts may further strengthen placement policy.
`HERMES_HOME` namespaces Hermes profiles, configuration and sessions, but gateway
processes retain the canonical Zone `HOME`. Other CLI authentication and caches
under that Unix home may therefore be shared by instances in the same Zone. Do
not claim per-instance CLI/account isolation or automatically copy authentication.

## One default Director surface per instance

```bash
sudo station platform setup --zone acme-dev --instance engineering --platform discord --plan
sudo station platform setup --zone acme-dev --instance engineering --platform discord
sudo station os instance verify --zone acme-dev --instance engineering
sudo station platform install --zone acme-dev --instance engineering
sudo station platform start --zone acme-dev --instance engineering
sudo station setup --organization acme --zone acme-dev --instance engineering --probe --json
```

The native platform wizard targets the mapped Director in this instance's Hermes
home. The human creates/authorizes the application and enters its token privately.
The default topology is one Director bot and primary channel per instance;
specialists are internal profiles/workers unless a justified topology grants a
separate external identity. Neither profile installation nor the wizard is an
automatic guild provisioner or token-minting service.

Only for an explicitly justified specialist surface, select its mapped role:

```bash
sudo station platform setup --zone acme-dev --instance engineering --role forge --platform discord --plan
sudo station platform setup --zone acme-dev --instance engineering --role forge --platform discord
```

The human must provide a separately authorized bot identity, least-privilege scopes
and channel permissions. Do not reuse a token concurrently with the Director's
gateway. Selecting `--role forge` is not topology or live-routing acceptance;
verify that worker's own service, authorized-user path and reply readback.

Provider and chat configuration are separate from acceptance. The existing private
setup broker's forms target Zone-base credentials; do not assume they enroll an
instance. Test the exact instance, account, authorized user/channel and restart path.

## The full AIOS and Builder's job

An OS includes durable domain objects and state transitions, useful views, processes,
workflows, connected capabilities, missions, governance, evidence, learning and
recovery—not merely a bot team. Its Director owns outcomes; persistent specialists,
Kanban workers and temporary delegates implement bounded responsibilities.

Builder's factory sequence remains: clarify domain/outcome → Librarian's multi-lane
research and provenance → contract/schema/views → Director/team and Skills/programs
→ capabilities/accounts/permissions → workflows and disabled automations → evals,
Doctor and recovery → implementation → independent verification → install in the
client's instance → private enrollment → live readback/fresh-session/recovery
acceptance → approved release. Reusable definitions may be shared; raw client
inputs, memory and credentials do not flow back into Factory by default.

The instance installer establishes the runtime envelope, compiled team and local
evidence. It does **not** automatically materialize or accept every domain database,
migration, dashboard, workflow, connector, permission enforcement mechanism or
automation declared by the full OS contract. Keep unimplemented capabilities
explicit and unaccepted. Local `verify` is not paid-provider, chat or business
workflow acceptance.

## Legacy is preserved, not silently migrated

`station os install/setup/verify` with `--id`, and gateway `--os`, address the older
schema-2 `(Zone, OS)` runtime bound to a Project. Those ledgers remain at
`/var/lib/station/registry/os/<zone>/<os>.json`; their compiled bundles remain under
`/opt/station/os-distributions/<zone>/<project>/<os>/<version>/`.

New instance commands do not adopt those profiles, move their secrets or reinterpret
their receipts. Back up and inspect legacy deployments before designing migration;
do not force-install over an occupied native profile, edit the ledger by hand or
reuse one bot token concurrently. A failed/partial instance needs its recorded
repair action and readback before retry. Neither old nor new commands promise a
transaction across external installers, accounts, services and live data.
Runtime authority is bound to the recorded filesystem identities. Copying or
restoring an instance's runtime to replacement inodes requires reviewed repair or
re-enrollment; 11.14 does not provide automatic instance restore/migration.

The separate bundled AGK client controller is also legacy compatibility:
`station client --legacy …` explicitly opts into its operator-home workflow
(`~/workspace/clients` and `~/.hermes`). Direct `agk client …` has that same legacy
model. Neither registers Station Organizations nor installs canonical Zone OS
instances, and neither provides separate client Zone identities. Preserve existing
data; do not use it as a shortcut for the instance workflow above.
