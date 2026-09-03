# Event Model

Everything important can produce an Event.

Examples:

```text
Discord mission created
Linear issue created
GitHub PR opened
PR merged
deployment completed
deployment failed
journal entry created
decision recorded
meeting completed
habit checked
invoice paid
```

## Event fields

```yaml
event_id:
organization_id:
project_id:
os_id:
mission_id:
type:
source:
timestamp:
actor:
payload_ref:
sensitivity:
```

## Consumers

Events may trigger:
- Hermes webhook / hook
- relevant OS
- memory candidate
- Notion update
- evidence
- metric
- Discord notification

This becomes a useful long-term AGK event layer.

Additional Discord lifecycle events:

```text
discord.connected
discord.bootstrap.started
discord.plan.generated
discord.resource.created
discord.resource.adopted
discord.resource.updated
discord.binding.written
discord.route.verified
discord.runtime.demoted
discord.bootstrap.completed
discord.drift.detected
discord.reconcile.completed
```
