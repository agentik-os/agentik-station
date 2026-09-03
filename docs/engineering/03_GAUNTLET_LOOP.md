# AGK Gauntlet Loop

The Gauntlet Loop is an evidence-driven worker/critic revision pattern for important artifacts.

AGK implements it using Hermes profiles, delegation, Kanban tasks, worktrees and verification evidence. It does not require a separate orchestration engine.

## Core rule

**The implementer must not be the final judge of its own work.**

## Canonical loop

```text
Orchestrator defines bar
        ↓
Implementer produces artifact
        ↓
Deterministic verification
        ↓
Fresh independent critic
        ↓
PASS? ───── yes ───→ integration gate
  │
  no
  ↓
critic emits ranked failures + evidence
        ↓
implementer fixes highest-value failures
        ↓
new verification evidence
        ↓
fresh critic
```

## Rules

- The quality bar must be concrete: tests, acceptance criteria, reference behavior, security rules or measurable output.
- Critics receive fresh context whenever practical.
- Critics judge artifacts and evidence, not implementer self-assessment.
- Review loops are bounded. Default max: 3 passes per workstream.
- Unresolved failures escalate to the Director/Human rather than silently passing.
- Final integration gets its own critic after parallel streams are merged.

## Role separation

```text
Director / Orchestrator
├── owns mission graph
├── owns acceptance bar
└── integrates results

Implementer
├── owns code/artifact
└── does not approve itself

Critic
├── independently evaluates
├── cites evidence
└── cannot modify acceptance criteria to make work pass
```

## Risk profiles

```text
low risk    → deterministic verification + one independent review
medium      → Gauntlet up to 2 passes
high        → Gauntlet up to 3 passes + security/architecture critics + human gate
production  → integration critic + live verification required
```
