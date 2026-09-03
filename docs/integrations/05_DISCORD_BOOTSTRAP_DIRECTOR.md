# Discord Bootstrap Director

## Objective

Once the user connects a Discord server, a privileged agent should be able to set up the server correctly and link it to the Agentik organization without hand-building every channel and permission.

## Bootstrap sequence

```text
User connects Discord bot/application
↓
Agentik detects target guild
↓
User authorizes bootstrap on this guild
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
Remove Administrator
↓
Verify runtime least privilege
↓
Emit evidence + final report
```

## Why temporary Administrator

Initial setup may need broad permissions to create and order roles, categories and channels. But `Administrator` bypasses channel restrictions, therefore it must be treated as bootstrap-only and removed after successful provisioning.

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
discord.bootstrap.demote
```

## Maintenance after install

When a new OS is installed:

```text
agentik os install sales
→ desired Discord state changes
→ drift detected
→ Discord Bootstrap Director plans reconciliation
→ safe apply / approval if required
→ new Sales surface becomes routable
```

## v3 Bot Mode provisioning

The Bootstrap Director also compiles installed OS Bot declarations into Discord virtual identities/aliases, channel-default bindings and Bot Group/team bindings. Reconciliation remains adopt-and-extend and idempotent.
