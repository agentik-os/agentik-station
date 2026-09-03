# Logs, Traces and Engineering Episodes

Hermes already stores native logs per profile and exposes them through `hermes logs`. Agentik must not create a competing raw logging subsystem.

## Native Hermes logs

Use Hermes logs for runtime truth:
- agent activity,
- errors/warnings,
- gateway activity,
- UI/runtime events,
- profile-specific logs.

## AGK normalization layer

AGK stores references and structured mission events around those logs:

```yaml
episode:
  organization_id: org_x
  mission_id: mis_184
  kanban_root_task: task_x
  profile_ids: [atlas, forge, sentinel]
  session_ids: [...]
  worktrees: [...]
  commits: [...]
  verification_runs: [...]
  critic_runs: [...]
  approvals: [...]
  deployments: [...]
  hermes_log_refs: [...]
  final_status: passed
```

## Episode package

A material engineering mission should be reconstructable from:
- spec/acceptance criteria,
- task graph,
- agent/profile/model routes used,
- relevant tool and execution events,
- diff/commits,
- verification evidence,
- critic findings and revisions,
- approvals,
- deployment/live checks,
- failure attribution,
- lessons promoted or rejected.

## Retention principle

Do not blindly duplicate every token or raw log into Convex/Postgres. Keep Hermes as the native runtime log source and promote only structured evidence, indexes and retention-required artifacts into AGK storage.
