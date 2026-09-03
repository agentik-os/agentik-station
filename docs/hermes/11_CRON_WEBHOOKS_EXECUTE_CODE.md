# Cron, Webhooks and Deterministic Programs

## Cron

Use Hermes Cron for recurring OS behavior.

Examples:

```text
Morning brief
Weekly review
Pipeline review
Memory cleanup
Backup verification
System audit
Journal prompt
Relationship follow-up scan
```

Prefer fresh sessions for scheduled jobs.

## Webhooks

Use webhooks for external activation.

Examples:

```text
GitHub PR opened
→ QA / Reviewer

Linear issue created
→ relevant Nano Director

CRM opportunity changed
→ Sales OS

Deployment failed
→ DevOps / Incident OS
```

Avoid unnecessary polling.

## execute_code

Use deterministic programs when reasoning is not required.

Principle:

> Reason when necessary. Program when deterministic.

Good uses:
- batch tool calls
- data transformations
- repeated API operations
- validation
- metric calculation
- deterministic orchestration helpers

An OS can therefore combine:
- probabilistic agents
- deterministic programs
- event triggers
- human approvals
