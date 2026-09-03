# Station Maintainer OS

**Nano Director:** `station-maintainer`  
**Discord face:** `Operator` (AGK/Station operations)  
**Purpose:** keep Station healthy, current, simpler and recoverable without violating stable/client boundaries.

## NanoTeam

- `hermes-upstream-scout` — update/release/config capability diff;
- `station-architect` — maps changes onto Station modules;
- `compatibility-engineer` — config/hooks/plugin/API compatibility;
- `station-simplifier` — Hermes-native-first + Ponytail deletion opportunities;
- `regression-engineer` — Station/OS/fresh-session suite;
- `security-reviewer` — boundaries/permissions/update risk;
- `release-manager` — ring promotion and receipts;
- `recovery-auditor` — rollback/restore evidence.

## Durable workflow

```text
UPDATE_EVENT
→ COLLECT_PLAN
→ CAPABILITY_DIFF
→ CHANGE_GRAPH
→ LAB_UPDATE
→ CONFIG_MIGRATION
→ REGRESSION
→ GAUNTLET
→ RECOVERY_REHEARSAL
→ CANDIDATE_RELEASE
→ PROMOTION_GATE
→ OBSERVE
```

No client stable promotion without its release policy.


## Optional orchestration-adapter watch

If OMH or another observed-executor adapter is enabled in LAB, Station Maintainer tracks compatibility separately from Hermes. Adapter updates never auto-promote to client stable. Hermes remains the runtime source of truth; Station remains the mission/evidence policy source of truth.
