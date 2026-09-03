# Dedicated Discord Bot Contract

The locked OS contract takes precedence over the general internal specialist routing optimization.

## Required surface per OS

```text
Dedicated Discord Application/Bot
        =
Nano Director Hermes Profile
        +
Dedicated OS Channel
        +
Slash Command Set
        +
How-to Pin
        +
Thread/Session Routing
```

## Wake path

```text
User in dedicated OS channel
  -> thread (new or existing work conversation)
  -> @OSBot
  -> Hermes gateway for Nano Director profile
  -> Hermes session
  -> answer OR AGK Mission
  -> Kanban root task/DAG when durable work is needed
```

A Discord thread is a conversation/session boundary, not automatically a mission and not automatically a Git worktree.

## Bootstrap

The Discord Bootstrap Director may receive temporary Administrator permission to provision application roles/channels/commands. It must:

1. inventory existing guild state;
2. plan diff;
3. create/adopt dedicated OS channel;
4. bind application/bot to OS Director profile;
5. sync slash commands;
6. create how-to pin;
7. perform command readback;
8. verify mention -> correct profile -> correct OS route;
9. remove temporary Administrator;
10. refuse `OPERATIONAL` if least-privilege demotion fails.

## Virtual specialists

Internal specialist Bots/profiles may be represented virtually or only through Bot Groups. A separate Discord application is required only when the specialist itself needs a durable public identity/permission boundary.
