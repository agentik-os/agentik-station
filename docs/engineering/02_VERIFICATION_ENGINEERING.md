# Verification Engineering

Verification Engineering is the discipline of designing proof of correctness into the mission before implementation starts.

Hermes already provides a native `verify_on_stop` mechanism that can reject a coding turn that edited code without fresh verification evidence. AGK uses this primitive as the lowest verification layer, not as the entire quality system.

## Verification stack

```text
V0 — Change evidence
     diff / files changed / generated artifacts

V1 — Static verification
     format / lint / typecheck / schema checks

V2 — Deterministic behavior
     unit / integration / contract tests

V3 — Acceptance verification
     explicit mission criteria / eval cases

V4 — Independent review
     fresh-context critic / security / architecture / Ponytail review

V5 — Environment verification
     build / container / migration / staging

V6 — Live verification
     smoke test / E2E / health / logs / telemetry

V7 — Post-change verification
     regression watch / SRE evidence / rollback readiness
```

Not every task needs every layer. The mission's risk class compiles the required verification contract.

## Verification contract

Every engineering mission MUST declare:

```yaml
verification:
  required:
    - lint
    - typecheck
    - unit_tests
    - acceptance
    - independent_review
  conditional:
    security_review: when_trust_boundary_changes
    migration_test: when_schema_changes
    staging_e2e: when_user_flow_changes
  evidence:
    retain_logs: true
    retain_diff: true
    retain_test_summary: true
```

## Fail closed

A red mandatory gate:
- blocks merge/deploy,
- returns the mission to the correct node in the graph,
- records failure evidence,
- never gets converted to green by prose.

## Bounded verification loop

```text
implement
  ↓
verify
  ├─ pass → critic
  └─ fail → diagnose → fix → verify
                         ↑         │
                         └─────────┘
```

Default retry budget: 3 local correction passes per failing node. Beyond the budget, block and escalate rather than burning tokens indefinitely.

## Evidence stage ownership

Verification Engineering owns the transition from `reported` to `verified` for the claims covered by its configured matrix. Deployment/readback and mission acceptance are separate later transitions and must not be inferred from test success alone.
