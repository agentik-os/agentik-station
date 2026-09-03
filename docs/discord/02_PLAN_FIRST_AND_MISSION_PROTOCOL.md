# Plan-First Mission Protocol

## Rule

Every agent that begins operative work must create a structured plan before execution.

This is not permission to invent a giant plan. A plan can be small for a small task, but it must exist.

## First action

For a mission-capable request the first structured action is:

```text
station_mission_plan(...)
```

The plan includes:

- mission objective;
- acceptance criteria;
- assumptions / constraints;
- ordered graph nodes;
- dependencies;
- parallelizable branches;
- verification nodes;
- expected evidence;
- rollback/recovery concern when relevant.

## Tool gate

Before plan creation:

```text
allowed:
- plan creation
- context/skill loading required by the host

denied:
- mutating external actions
- code writes
- deployments
- outbound messages
- destructive tools
```

If limited read-only reconnaissance is required, the agent first creates a provisional plan containing an explicit `inspect-current-state` node, then may revise the plan after inspection.

## Plan revisions

Plans are living contracts, not theater. When reality differs:

```text
station_plan_update(reason, graph_delta)
```

The Discord card shows the change and the final report records material deviations.

## Completion

A mission cannot be marked complete until all required verification nodes have passed or an explicitly authorized exception is recorded.


## Evidence status is separate from plan status

A plan node may visually be complete while its result is still only executor-reported. Discord therefore renders a separate semantic evidence headline such as:

```text
Plan • not run
Code • running
Code • reported done
Test • verified
Ship • read back
```

Plan progress answers “where are we in the declared graph?” Evidence status answers “what has actually been proven?” They must never be conflated.
