# Discord Architecture

## Principle

**Discord is the generated human cockpit for an organization and each OS has a dedicated Nano Director bot identity.**

The source of truth is Organization desired state + installed OS packages + dedicated bot bindings + permission policy, not the manually observed channel tree.

## Canonical OS surface

```text
OS package
 -> Nano Director Hermes profile/Bot
 -> dedicated Discord application/bot
 -> dedicated primary channel
 -> commands/how-to
 -> thread = Hermes session surface
 -> mission = durable work object
```

Internal NanoTeam specialists stay behind Hermes unless an OS contract explicitly exposes another durable identity.

The human server owner creates/authorizes every Discord application, controls its token and removes any temporary bootstrap elevation. Station/Hermes store the token only in the owning Zone, compile guild desired state and require permission/message readback before acceptance.

## Provisioning layers

1. Organization topology.
2. OS surface manifests.
3. Dedicated OS bot enrollment/bindings.
4. Human role policy.
5. Runtime team/project/board bindings.
6. Discord Experience Layer for plan/progress/interactions.
7. Discord compiler for roles/categories/channels/overwrites/commands.

## Runtime UX

Raw Hermes tool progress is logged, not spammed into the human channel. Operative requests create a plan-first mission and one editable Mission Progress Card. The card is a projection of durable mission/Kanban/Loop-Graph state.

## Thread rule

```text
channel = OS interaction surface
thread = conversation/session surface
mission = explicit durable work object
progress card = human projection of mission state
```

The Nano Director decides whether a conversational request becomes operative work, but any operative work is plan-first.
