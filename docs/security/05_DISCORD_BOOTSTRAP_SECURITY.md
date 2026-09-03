# Discord Bootstrap Security

## Administrator is bootstrap-only

Discord Administrator bypasses channel restrictions. Treat it like an installation privilege, not a normal runtime permission.

Lifecycle:

```text
DISCORD_BOUND
↓
bootstrap privilege enabled
↓
provision
↓
verify
↓
remove Administrator
↓
verify least privilege
↓
RUNTIME_SECURED
```

If demotion fails, bootstrap is **not** successful.

## Role hierarchy

Discord role hierarchy means an identity can only affect roles below its highest role. Provisioning must therefore:
- preflight role position
- create managed roles below the bot role
- never assume it can edit owner/admin roles above it
- verify runtime permissions after demotion

## Secret handling

Discord bot token:
- external secret source / protected environment
- never Git
- never generated into OS package
- never logged in evidence

## Provisioner mutation safety

Every mutation should contain:

```text
run_id
organization_id
guild_id
actor_profile
operation
resource_id
before_hash
after_hash
policy_decision
```

## Existing servers

Default policy:

```text
unknown resource = preserve
managed resource drift = plan
matching existing resource = adopt if safe
destructive change = approval required
```

## Runtime least privilege

After bootstrap, grant only capabilities needed for normal Agentik operation, e.g. messaging/thread/channel access actually used by the product. Do not keep broad server-administration rights for convenience.
