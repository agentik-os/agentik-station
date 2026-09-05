# Agentik Station Security Contract

## Threat model

Station runs privileged installation code and will eventually mediate private projects, client environments, source control, model providers, Discord bots, Composio accounts, and deployment systems. Inputs may come from command arguments, JSON desired state, repository content, remote Hosts, agents, plugins, external tools, and Zone-owned files.

The primary threats are:

- path traversal or arbitrary root write;
- symlink/hardlink race against privileged reconciliation;
- command or SSH option injection;
- mixed client/private credentials or memory;
- over-privileged shared runtime/daemon sockets;
- false readiness claims that cause unsafe downstream work;
- supply-chain execution of mutable remote installers;
- unverified remote operations;
- a model approving its own privileged action;
- incomplete backup/recovery presented as protection.

## Desired-state records are not path authorities

Doctor and reconciliation derive canonical roots from validated Host, Zone, environment, and Project identifiers. A path string stored in a JSON record never authorizes filesystem traversal by itself. Invalid records fail closed before their supplied roots are inspected.

Mixed system/Zone FHS parents use mode `0711`: a Zone may traverse to its known
private child, but cannot list the parent. Zone state remains UID-owned `0700`;
control remains `0750`/`0640`. Root-owned, Zone-group-readable binding projections
live under `/var/lib/station/zone-bindings`; `/etc/station` is not opened to agents.
Compiled OS distributions are published under root-owned
`/opt/station/os-distributions/<zone>/<project>/<os>/<version>`, never by root inside
a Zone-writable parent. Cross-identity CLI launches clear the inherited environment.

New client-owned OS instances use root-owned schema-3 ledgers at
`/var/lib/station/registry/os-instances/<zone>/<instance>.json`. A ledger binds
Organization/Zone/instance, the exact compiled distribution, full native role map,
workspace and declared allowed Projects. Organization registration under
`/etc/station/organizations.d` may reference only existing matching ORGANIZATIONS
Zones; it cannot relabel a Zone, transfer its owner or create a new Unix boundary.
Legacy schema-2 ledgers under `/var/lib/station/registry/os` remain Project-bound
and are not automatically migrated or adopted. Zone-writable profile files are
read back, not accepted as an authoritative installation record.
New standalone Projects reserve previously absent human/runtime roots before
writing; existing or substituted roots fail closed. Partial creation is reported
for deliberate repair rather than broad deletion.

Strix execution requires a separately accepted disposable LAB Host. Docker access
is host-root-equivalent; a root-owned approval file cannot contain a malicious
Docker administrator. Do not enroll that capability on a shared/core/production
Host. See [the Strix boundary](resources/strix/README.md) for source disclosure,
network acceptance, cost limitations and cleanup requirements.

## v11 privileged-write rules

- validate every identifier before constructing a path, Unix identity, filename, or operation;
- permit lowercase ASCII identifiers only, with strict length and boundary rules;
- confine every managed path to an explicit FHS root;
- traverse managed directories with directory descriptors and `O_NOFOLLOW` where supported;
- reject symlinks and special files in managed destinations and release sources;
- use atomic same-directory writes and `os.replace`;
- refuse to overwrite an immutable release version with different content;
- never recursively follow links for ownership, deletion, or freezing;
- record filesystem changes for best-effort rollback and operation evidence.

## Process-execution rules

- execute subprocesses with argument arrays;
- never interpolate desired-state values into a shell command;
- remote bootstrap sends desired state as JSON;
- strict SSH host-key checking is the default;
- `accept-new` requires explicit operator intent;
- no unreviewed network script is piped to a privileged shell by the safe kernel;
- exact external versions/sources and acceptance receipts belong to the future module setup workflow.

## Zone boundaries

Each Zone receives:

- its own Unix user and same-name primary group;
- audited non-interactive shell and exact home;
- its own subordinate UID/GID range for future rootless runtime;
- its own `/srv` human root;
- its own `/var/lib` state root and `HERMES_HOME`;
- its own logs, run state, and backup staging root;
- mode `0700` credential directories;
- default-deny cross-Zone filesystem, credentials, and memory.

A Hermes Profile is not treated as a filesystem sandbox. Linux/Zone isolation remains mandatory.

An OS instance has its own workspace and Hermes home beneath its Zone. Native
Director and specialist identifiers are namespaced by Zone, instance and role so
gateway/service selection cannot collide merely because two packages use the same
role name. This is runtime naming and state separation, **not separate Unix
authority**: instances, members and Projects inside one Zone share its UID. The
allowed-Project list is a routing/policy declaration, not an enforced filesystem
allowlist. Isolate different clients and sensitive environments with separate
Zones; do not copy tokens, provider logins, sessions or raw memory across them.

Instance `HERMES_HOME` separates Hermes profiles, configuration and sessions, but
gateway processes retain the canonical Zone `HOME`. Other CLI authentication and
caches under that home may be shared within the Zone. This is not per-instance
CLI/account isolation; enrollment must not automatically copy authentication.
Instance runtime roots are inode-bound. A copied/restored replacement is not
automatically trusted; it requires reviewed repair or re-enrollment. No automatic
instance restore or migration is provided in 11.14.

Instance setup opens the selected Director's native wizard. The existing guided
setup broker's Zone-base credential forms do not automatically enroll an instance.
Dedicated bot applications/tokens remain human-owned. Specialist external bots
require justified topology and independent permission/readback acceptance.

The opt-in `station client --legacy …` and direct bundled `agk client …` controller
use the operator's `~/workspace/clients` and `~/.hermes` profiles. They do not
register canonical Station client Zones or enforce separate client Unix identities.
Treat them as a distinct shared-operator compatibility workflow, not an isolation
or instance-enrollment mechanism. Existing legacy data is preserved, not migrated.

The bootstrap operator currently receives broad passwordless sudo by default.
`--sudo-mode password` changes the account's authentication requirement; it is not
an action-policy enforcement service. Same-Zone roles share one Unix trust domain,
and prompts/tool descriptions do not constitute complete runtime ACL enforcement.
Do not expose an unrestricted operator shell to incoming chat or untrusted tools.

Bootstrap locking and stage receipts improve coordination and diagnosis; they do
not make apt, external installers or services one atomic transaction. A killed
shell can leave sudo children running. Inspect those processes and the named
repair action before acknowledging an incomplete attempt. Reported completion is
not live system acceptance or proof of recovery.

## Credentials

- never commit provider tokens, Discord tokens, OAuth material, API secrets, private keys, client data, or production credentials;
- no global cross-organization `.env`;
- store references/manifests alongside the owning Zone/Project;
- use narrow credential delivery such as systemd credentials or provider-managed authentication;
- production credentials do not enter development by default;
- Control stores metadata and references, not a mirrored secret vault;
- remote Host secrets do not return to Operator Control automatically;
- resolve principal, organization, account, environment, capability, and approval before use.

## Evidence and authorization

- a config file is not a working connector;
- a binary is not an authenticated integration;
- an executor report is not verification;
- a model-generated “approved” message is not authorization;
- Discord interactions resolve user identity and policy outside the model;
- production mutation requires explicit policy and evidence;
- every `DEGRADED` state includes a next repair action.

## Release posture

Keep the repository and deployments private during alpha. Do not use a organization production Host until:

1. fresh Ubuntu/Debian install is observed;
2. repository and installed Station Doctor pass;
3. security tests pass;
4. Hermes compiler/runtime passes Zone isolation;
5. Discord and Composio readback pass where required;
6. encrypted off-Host backup and destructive restore acceptance pass;
7. rollback and fresh-session acceptance pass.

The detailed audit response is under `docs/hardening/` and the original v10 professional audit is under `docs/audit/`.
