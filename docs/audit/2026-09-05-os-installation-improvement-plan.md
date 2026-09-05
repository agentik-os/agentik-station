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
- [x] Repository Doctor, release metadata, CI and final worktree hygiene pass.
- [x] VPS changes, if needed, use reviewed exact targets and preserve private state.
- [x] Final report distinguishes verified software from account/service/mission gates.

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
- Existing enrolled profiles must never be overwritten to make a new feature
  appear installed. The native/CI results below close the separate release-11.33
  gates; they do not certify future changed releases.

## Completed native acceptance for 11.33

The accepted source commit is `ae7e0c7615cb466c97ff401d2d3f0de81f51e76c`.
[All nine CI jobs passed](https://github.com/agentik-os/agentik-station/actions/runs/33981519787),
including a fresh packed Linux Workstation installation with 26 required checks,
native TUI/session smoke tests and an update lifecycle with unchanged upstream
pins and a synthetic successor label. The latter is not acceptance of unknown
future upstream releases. Fourteen protected Workstation files were unchanged.

The existing VPS activated immutable Station 11.33 without replaying full
bootstrap. Its still-pristine Stepper and Builder instances were retired through
six exact guarded, recoverable renames, followed by normal default-team
installation: Stepper 0.2.0 (3 profiles), Builder 11.14 (11 profiles) and preserved
Librarian 3.0.1 (15 profiles). All 29 profiles read back; all 14 Stepper/Builder
resource indexes and skills matched source and immutable distributions.
Librarian's complete trees and ledger remained unchanged.

Under the real Factory UID, the installed Stepper passed all 27 evaluations and
produced a handoff accepted by its checker. Installed Builder prepared three
synthetic task packets, bound their artifacts/evidence, and rejected a deliberately
altered fixture. Execute-only Linux ancestors were exercised successfully. This
tested deterministic native validators, not LLM role execution or a business mission.

The final full Doctor passed 192 checks with no issues. All 13 isolated version
checks passed; the software inventory remained 17/18 solely because of Ponytail.
All 17 protected files retained their bytes, ownership and modes; the four tracked
service activation states were unchanged. The service comparison is not a claim
that every unit-file byte or external service was audited.

Private evidence is retained on the Host under
`/var/backups/station/stepper-builder-11.33-20260905`; retired instances remain
recoverable under `/var/backups/station/os-defaults-11.32-to-11.33`.
No account enrollment, server-app activation or npm registry publication occurred.
