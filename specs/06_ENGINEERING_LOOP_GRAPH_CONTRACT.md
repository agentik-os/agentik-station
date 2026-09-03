# Engineering Loop-Graph Contract

## Required graph fields

```yaml
mission_graph:
  id: graph_...
  mission_id: mis_...
  nodes:
    - id: spec
      type: SPEC
      owner: atlas
      completion_contract: acceptance_criteria_approved
    - id: api
      type: IMPLEMENT
      owner: forge
      workspace: worktree
      depends_on: [spec]
    - id: api_verify
      type: VERIFY
      owner: qa
      depends_on: [api]
      on_fail: api
  gates:
    - id: integration
      requires: [api_verify]
  budgets:
    max_total_retries: 8
    max_node_retries: 3
```

## Runtime compilation

```text
AGK typed graph
  ↓
Hermes Kanban tasks + dependencies
  ↓
profile assignment
  ↓
workspace/worktree allocation
  ↓
verification hooks
  ↓
mission evidence events
```

## Safety requirements

- graph cycles must be explicit bounded retry loops,
- no hidden recursive spawning,
- every high-risk path contains approval where required,
- fan-out coding nodes receive isolated worktrees,
- fan-in nodes rerun integration verification,
- DONE is emitted only from a terminal gate.
