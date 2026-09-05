# Stepper / Builder and installation acceptance mission

## Scope and acceptance

Improve confirmed execution/validation gaps in Stepper and Builder, and audit the
complete delivered Host dependency/resource set against the actual VPS. Keep
Hermes as the execution engine; do not build a parallel scheduler. Preserve
existing accounts, client isolation, immutable releases and configured profiles.
Software delivery, scoped integration and live account acceptance remain separate.

## Plan First graph

```text
contracts + clean main baseline (39f7508)
├── Stepper semantic/behavior audit → bounded fixes → regression/evaluation tests
├── Builder execution/handoff audit → bounded fixes → regression/evaluation tests
└── installer + actual VPS inventory → reproduce gaps → targeted source repair
    ↓
compiler/package integration → independent review → tests + repository Doctor
    ↓
versioned release + CI → scoped VPS readback → evidence and remaining gates
```

Ownership: Stepper branch owns `os/stepper/` and Stepper tests; Builder branch
owns `os/builder/` and its new tests; Host branch owns read-only inventory and
diagnosis. The main agent owns installer/compiler/global metadata integration and
verifies each branch. No branch may overwrite another's edits or change credentials.

## Validation checklist

- [x] Stepper outputs reject inconsistent or unusable plans with actionable errors.
- [x] Builder has a verifiable path from scoped inputs to reviewed deliverables.
- [x] Canonical sources, generated native profile payloads and npm contents agree.
- [x] Every required dependency/resource has observed software evidence or a
      named unmet requirement; an aggregate failure does not hide other results.
- [x] Existing native runtime/source compatibility is checked without account
      adoption, executing an updater, or bypassing a native security gate.
- [x] Relevant unit, adversarial, package and integration tests pass locally.
- [ ] Repository Doctor, release metadata, CI and final worktree hygiene pass.
- [ ] VPS changes, if needed, use reviewed exact targets and preserve private state.
- [ ] Final report distinguishes verified software from account/service/mission gates.

No claim of perfect operation is authorized by this checklist alone. Record real
results and the next repair action for each unmet gate before acceptance.

## Source verification

- Station/Factory: 2,115 passed; 23 Linux-only checks skipped on macOS.
- npm: 263 passed. AGK: 461 passed; two native-web library checks skipped locally.
- Stepper: 27 deterministic evaluations passed. Repository Doctor passed.
- The initial VPS software inventory verified 17/18 required groups and all 20
  server image references. Ponytail remains blocked by the retained native
  security rejection. The four server applications have no deployed containers;
  installed images do not constitute live service or account acceptance.
- Exact consumer package: 839 payload files matched the checkout; 29 native
  profiles installed/read back, six OS checks and three launcher checks passed.
  The installed Stepper/Builder programs passed handoff and changed-input checks.
  This reused clean pinned Hermes software, not a fresh full-dependency install.
- Native Linux, published-commit CI and targeted VPS migration still require
  their own evidence. Existing enrolled
  profiles must never be overwritten to make a new feature appear installed.
