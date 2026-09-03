# Ponytail Engineering Standard

Repository: `DietrichGebert/ponytail`

Ponytail is installed for DevOps/Builder/Engineering OSs as a Hermes plugin:

```bash
hermes plugins install DietrichGebert/ponytail --enable
```

Restart Hermes after install.

## Purpose

Ponytail enforces the engineering instinct to avoid unnecessary code while preserving validation, security, accessibility and error handling.

Canonical ladder:

```text
Understand the real system first
↓
Does this need to exist?
↓ no → do nothing
Already exists in codebase?
↓ yes → reuse
Stdlib?
↓ yes → use it
Native platform feature?
↓ yes → use it
Installed dependency?
↓ yes → use it
Can the change be extremely small?
↓ yes → keep it small
Only then write the minimum new code required
```

## DevOps lifecycle

```text
PLAN FIRST
→ inspect existing system
→ architecture / task graph
→ PONYTAIL LADDER
→ implement
→ deterministic tests
→ ponytail-review
→ QA
→ security / ponytail-audit where relevant
→ independent review
→ PR / CI
→ staging
→ live verification
→ production
→ evidence
```

## Profile mapping

```text
devops-director  → full
architect        → full
engineer         → full
frontend/backend → full
qa               → review
auditor/security → audit
reviewer         → review + debt
maintainer       → debt + gain
```

## Guardrail

Ponytail is not permission to skip required engineering work. Never remove:
- trust-boundary validation
- access control
- data-loss protections
- security checks
- tests required by acceptance criteria
- accessibility requirements
- observability required for production


## Position inside the v4 engineering harness

Ponytail is the simplification gate before implementation and again during review. It does not replace Verification Engineering, Gauntlet critics, security review or tests.

```text
Understand → Ponytail → Build → Verify → Gauntlet → Integrate → Live Verify
```
