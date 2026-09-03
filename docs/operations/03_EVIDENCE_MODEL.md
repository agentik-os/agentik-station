# Evidence Model

A mission should not complete with only:

> "Done."

It should produce proof.

## Evidence examples

Engineering:
- test output
- CI URL/ref
- PR
- commit
- deployment result
- production health check

Research:
- source list
- extracted facts
- confidence

Operations:
- updated Linear issue
- Notion page
- database record ID
- sent message ID

## Evidence object

```yaml
evidence_id:
organization_id:
project_id:
mission_id:
task_id:
type:
source:
created_at:
actor:
verification_status:
artifact_ref:
```

## Completion

```text
Result
+
Verification
+
Evidence
=
Done
```

## Engineering Episode v4

Code-modifying missions attach an Engineering Episode index containing graph version, profiles/model routes, worktrees, commits, verification runs, Gauntlet critics, approvals, deployment/live checks and references to Hermes native logs. Raw logs remain in Hermes unless retention policy requires export.
