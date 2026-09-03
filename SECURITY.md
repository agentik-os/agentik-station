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

## Credentials

- never commit provider tokens, Discord tokens, OAuth material, API secrets, private keys, client data, or production credentials;
- no global cross-organization `.env`;
- store references/manifests alongside the owning Zone/Project;
- use narrow credential delivery such as systemd credentials or provider-managed authentication;
- production credentials do not enter development by default;
- Control stores metadata and references, not a mirrored secret vault;
- remote Host secrets do not return to Gareth Control automatically;
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

Keep the repository and deployments private during alpha. Do not use a client production Host until:

1. fresh Ubuntu/Debian install is observed;
2. repository and installed Station Doctor pass;
3. security tests pass;
4. Hermes compiler/runtime passes Zone isolation;
5. Discord and Composio readback pass where required;
6. encrypted off-Host backup and destructive restore acceptance pass;
7. rollback and fresh-session acceptance pass.

The detailed audit response is under `docs/hardening/` and the original v10 professional audit is under `docs/audit/`.
