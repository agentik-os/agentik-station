# Bots and NanoTeams in the Agentik OS Standard

## OS package extension

An OS may declare persistent Bots, Bot Groups and ephemeral worker classes.

```text
<os>/
├── os.yaml
├── bots/
│   ├── director/
│   │   ├── profile.yaml
│   │   ├── SOUL.md
│   │   ├── skills/
│   │   └── routines.yaml
│   └── specialists/...
├── groups/
│   └── core-team.yaml
├── workers/
├── skills/
├── capabilities/
├── policies/
├── evals/
├── discord/
│   ├── surfaces.yaml
│   └── virtual-bots.yaml
└── ui/
```

## Required Director

Every executable OS has exactly one primary Director Bot unless the OS is explicitly declared `headless`.

The Director owns:

- outcome routing;
- human escalation;
- mission creation;
- delegation to Bot Groups or Kanban;
- final synthesis;
- evidence completion.

The Director must not perform every task itself. It chooses between direct response, bot-to-bot request, Kanban mission and ephemeral delegation.

## NanoTeam

A NanoTeam is an AGK semantic abstraction compiled to a Hermes Bot Group plus optional Kanban workers.

```text
NanoTeam
├── persistent members -> Bot Group
└── temporary members  -> delegate_task / Kanban workers
```

## Example: DevOps OS

```text
DevOps OS
├── Atlas       DevOps Director Bot
├── Archimedes  Architecture Bot
├── Forge       Senior Developer Bot
├── Sentinel    QA/Security Bot
├── Engineering Core Bot Group
├── Engineering Kanban Board
└── ephemeral workers
    ├── researcher
    ├── code-explorer
    └── test-runner
```

Ponytail is enabled for code-producing/reviewing DevOps profiles according to the DevOps policy.
