# Doctor, Rollback and Recovery

## Composite doctor

An OS doctor must check at minimum:

- package/version/hash integrity
- Hermes version compatibility
- required profiles/distributions
- skills present
- programs executable and tests available
- MCP/tool contracts resolvable
- provider route resolution
- memory/knowledge scope availability
- Kanban/board bindings
- Discord dedicated bot/channel/commands/readback
- cron disabled/enabled state versus fresh-session evidence
- hooks/verification policy
- secret references without printing secret values
- rollback target availability
- recovery artifact checksum

Builder invokes Hermes-native diagnostics where available (`hermes doctor`, hooks doctor, profile/gateway checks) and adds OS-specific checks.

## Rollback

Rollback means activating the previous immutable package/version and restoring the compatible profile/config snapshot. It is tested before release.

## Recovery artifact

Recovery must be deterministic and contain no raw secrets. It should reconstruct:

1. required Hermes version
2. OS package/distributions
3. desired profile config
4. skills/programs/MCP declarations
5. Discord bindings/desired state
6. durable state restore references
7. doctor commands
8. E2E acceptance mission

A generated recovery ZIP that has never been rehearsed is not sufficient evidence.
