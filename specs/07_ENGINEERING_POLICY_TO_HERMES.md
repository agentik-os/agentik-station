# Engineering Policy → Hermes Compilation

`06_CONFIG/engineering.policy.example.yaml` is AGK desired state, not a example-projecttim Hermes config file.

The Node Controller compiles supported fields into the pinned Hermes runtime configuration.

## Core mapping

```text
AGK engineering.hermes.verify_on_stop
    → Hermes agent.verify_on_stop

AGK engineering.hermes.verify_guidance
    → Hermes agent.verify_guidance

AGK engineering.hermes.max_verify_nudges
    → Hermes agent.max_verify_nudges

AGK engineering.hermes.tool_loop_guardrails.*
    → Hermes tool_loop_guardrails.*

AGK engineering.delegation.max_concurrent_children
    → Hermes delegation.max_concurrent_children

AGK engineering.delegation.max_spawn_depth
    → Hermes delegation.max_spawn_depth

AGK engineering.delegation.orchestrator_enabled
    → Hermes delegation.orchestrator_enabled

AGK engineering.delegation.worktree_isolation
    → Hermes delegation.worktree_isolation
```

Model route aliases compile through Agentik/AGK route resolution into Hermes provider:model selections, API server model routes, profile defaults or per-request overrides depending on execution surface.

## Version safety

Before compilation:
1. read pinned Hermes version from `agentik.lock`,
2. validate supported config schema,
3. render desired Hermes config,
4. diff current vs desired,
5. apply,
6. restart only affected services,
7. run `agentik doctor`,
8. rollback on failed health/E2E.

Unknown Hermes fields fail closed instead of being guessed.
