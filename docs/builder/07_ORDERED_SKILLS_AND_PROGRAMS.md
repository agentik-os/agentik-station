# Ordered Skills + Deterministic Programs

Hermes supports skills, but AGK owns the **ordering contract**.

## Ordered skills

Every OS declares phase-aware skills, for example:

```yaml
skill_chain:
  intake:
    - mission-intake
    - scope-check
  plan:
    - domain-research
    - architecture
  execute:
    - domain-operation
  verify:
    - evidence-check
    - independent-review
  recover:
    - recovery-protocol
```

Builder validates that required skills exist in the installed profile distribution and that a fresh session can discover/use them.

## Deterministic-first rule

Before an LLM step, Builder asks whether the action can be deterministic.

Prefer a program when the operation is:

- parsing/validation
- transformations with stable rules
- schema checks
- package/hash generation
- migrations with explicit semantics
- doctor checks
- backups/restores
- command sync/readback
- release verification

Hermes no-agent cron is preferred for scheduled deterministic jobs that do not need reasoning.

Every deterministic program must define input schema, output schema, exit/error behavior, idempotency expectations and tests.
