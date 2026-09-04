# Discord Bootstrap Director

## Objective

Once the user connects a Discord server, a privileged agent should be able to set up the server correctly and link it to the Agentik organization without hand-building every channel and permission.

## Bootstrap sequence

```text
Server owner creates a Discord application/bot and obtains its token
↓
Server owner authorizes that application to the target guild through OAuth2
↓
Token is entered through the owning Zone's Hermes gateway setup
↓
Discord Bootstrap Director starts maintenance window
↓
Inventory current roles/categories/channels/overwrites
↓
Compile desired state from organization + OSs
↓
Generate human-readable plan/diff
↓
Apply safe changes
↓
Persist immutable bindings
↓
Run route/permission tests
↓
Ask server owner to remove temporary Administrator/elevation
↓
Read back the role change and verify runtime least privilege
↓
Emit evidence + final report
```

## Why temporary Administrator

Initial setup may need broad permissions to create and order roles, categories and channels. But `Administrator` bypasses channel restrictions, therefore it must be treated as bootstrap-only. Station cannot use a bot token to create independent Discord applications/tokens, and a bot must not be trusted to remove its own highest/equal managed role. The server owner performs and confirms the final privilege removal; Station reads the result back before acceptance. A narrower explicit permission set is preferred whenever it can create the desired topology.

## Role hierarchy rule

Discord role hierarchy constrains what a bot can manage. The bootstrap process must verify that the bot's highest role is placed high enough to manage the roles it creates/assigns. Runtime demotion must still leave enough role position/permissions for ordinary operations that are actually required.

## Non-destructive modes

```text
NEW_SERVER
  safe automatic create

EXISTING_SERVER
  adopt + extend
  no deletes by default

MIGRATION
  explicit plan + approval
  destructive operations possible only when policy allows
```

## Bootstrap capability

The Director does not receive a raw unrestricted shell if not needed. It invokes a typed Discord Provisioner capability.

```text
discord.bootstrap.plan
discord.bootstrap.apply
discord.bootstrap.verify
discord.bootstrap.verify_runtime_permissions
```

The names above are capability contracts. In release 11.12, Station has binding validation and Discord message create/edit/read transport, but the full guild topology provisioner has not passed external test-guild acceptance and is not `OPERATIONAL`.

## Maintenance after install

When a new OS is installed:

```text
station os install --id sales-os --zone <zone-id> --project <project-id>
→ desired Discord state changes
→ drift detected
→ Discord Bootstrap Director plans reconciliation
→ safe apply / approval if required
→ new Sales surface becomes routable
```

## v3 Bot Mode provisioning

The Bootstrap Director also compiles installed OS Bot declarations into Discord virtual identities/aliases, channel-default bindings and Bot Group/team bindings. Reconciliation remains adopt-and-extend and idempotent.

## Token and application boundary

The bootstrap application may create guild roles, categories, channels, overwrites and commands within permissions granted by the server owner. It cannot mint the separate applications and secret bot tokens required for durable per-OS public identities. Those applications/tokens remain human enrollment gates unless a separately approved control plane is introduced. Internal specialists normally stay behind the Nano Director and therefore need no public Discord application.
