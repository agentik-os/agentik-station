# Code and Ship Safely

## Executor-neutral contract

Station specifies a coding owner by capability, not vendor:

```yaml
executor_requirement:
  capabilities:
    - repository_read
    - repository_write
    - test_execution
    - diff_report
  isolation: worktree
  model_policy: engineering-code
```

A resolved owner can be Hermes coding profile, Codex, Claude Code or another registered executor.

## Canonical evidence ladder

```text
PLAN · NOT RUN
  prepared intent only

CODE · RUNNING
  runtime observation exists

CODE · REPORTED DONE
  executor says implementation ended
  no correctness claim

TEST · VERIFIED
  required test/review/CI evidence observed

SHIP · READ BACK
  deployment/external state observed after release

ACCEPT · PASSED
  mission acceptance criteria satisfied
```

## Separation of duties

When policy requires independent verification, executor and verifier cannot be the same actor identity.

## Merge claims

Never say merge-ready merely because implementation is complete. Merge-ready requires the configured verification matrix: tests, static checks, review, security and CI as applicable.
