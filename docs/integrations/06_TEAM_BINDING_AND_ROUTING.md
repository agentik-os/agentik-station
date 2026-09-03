# Team Binding and Routing

## Core idea

Discord should know *which AI team owns each surface* without exposing every internal agent as a bot.

## Binding object

```yaml
binding_id: discord:example:engineering:devops
organization_id: example
os_id: agk.devops
surface_key: devops

discord:
  guild_id: "<guild-id>"
  category_id: "<category-id>"
  channel_id: "<channel-id>"

runtime:
  director_profile: devops-director
  project_id: agentik-platform
  board_id: engineering
  default_capability_policy: devops-standard

session:
  thread_mode: per-conversation
  mission_creation: director-decision
```

## Routing chain

```text
Discord message
↓ channel_id
Binding Registry
↓
organization_id
os_id
director_profile
project_id
board_id
↓
Hermes Gateway
↓
correct Director session
↓
answer / delegate_task / durable Mission
```

## Cross-team collaboration

If DevOps needs Research:

```text
DevOps Director
↓
AGK capability / team registry
↓
Research OS contract
↓
Research Director / delegated subagent
↓
result + evidence
↓
DevOps mission continues
```

The user does not need to manually move messages between Discord channels for internal OS collaboration.

## Human-visible team links

Discord may expose:
- channel topic with owning OS/team
- pinned `/team` or `/status` command
- mission thread header/status
- cross-links to Linear/GitHub/Agentik UI

But runtime binding is stored by IDs, not parsed from topic text.

## Conflict handling

If two OSs request the same surface:
1. merge when compatibility contract allows
2. namespace when they are distinct
3. fail plan with an explicit conflict when unsafe to infer

Never silently route one channel to two privileged Directors without a declared router policy.
