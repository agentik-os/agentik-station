# Observability

Track at minimum:

## Node
- uptime
- disk
- memory
- CPU
- container health
- backup health

## Hermes
- gateway health
- profile health
- provider failures
- fallback usage
- tool errors
- plugin errors
- session failures

## Missions
- active
- blocked
- failed
- completed
- retries
- time-to-review
- time-to-done

## Engineering
- tests
- review failures
- deployment failures
- rollback events

## Economics
- model usage
- token cost
- tool cost
- mission cost

## Security
- denied tool calls
- unresolved contexts
- approval events
- failed access attempts

## Discord provisioning
- target guild connectivity
- desired-state hash
- current-state hash
- pending diff count
- last bootstrap/reconcile status
- managed role/category/channel counts
- binding completeness
- routing test failures
- runtime Administrator retained (critical alert)
- drift age


## Engineering harness
- Hermes `agent`, `errors`, and `gateway` log health
- mission graph node latency / retry counts
- subagent fan-out size and collision rate
- worktree creation / preservation / prune health
- verify-on-stop nudges and unresolved verification failures
- Gauntlet pass count / critic failure categories
- integration fan-in failures
- model route resolved provider:model + fallback rate
- per-role cost and latency
- learning candidates created / promoted / rejected
- episode evidence completeness
