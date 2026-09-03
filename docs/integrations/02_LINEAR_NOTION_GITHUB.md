# Linear, Notion and GitHub

## GitHub

Source of truth for:
- code
- PRs
- branches
- CI
- technical artifacts

## Linear

Source of truth for:
- human-visible projects
- initiatives
- issues
- roadmap
- priority
- stakeholder status

Mapping:

```text
1 Linear issue
→ 1 Hermes mission
→ N internal Kanban tasks
```

## Notion

Source of truth for:
- PRDs
- SOPs
- meeting notes
- architecture
- decisions
- runbooks
- research
- durable knowledge

## Notion is not

- runtime task graph
- secret store
- agent memory backend
- Git repository

## Sync

Use hooks/event logic:

```text
mission completed
→ update Linear
→ write/update Notion
→ record evidence
→ Discord report
```
