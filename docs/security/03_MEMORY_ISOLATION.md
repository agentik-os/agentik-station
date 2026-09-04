# Memory Isolation

## Boundaries

At minimum:
- personal
- organization
- project
- OS
- mission

## Private Life vs Business

Business may receive high-level signals from Life.

Example allowed:
```text
energy low
schedule overloaded
```

Example not automatically allowed:
```text
full raw private journal
```

## Client to Operator

Operator Business OS may receive:
- status
- invoice state
- next action
- high-level delivery metrics

It should not automatically ingest:
- client private memory
- internal documents
- confidential datasets

## Test

Create two namespaces with distinctive canary data.

Cross-query must fail by architecture.
