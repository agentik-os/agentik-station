# Evidence Before Claims

This is a Station-wide truthfulness contract for machine status.

## Evidence classes

| Evidence class | Meaning | Human label example |
|---|---|---|
| `prepared` | intent/handoff/plan exists | `Plan • not run` |
| `observed` | runtime activity was directly observed | `Code • running` |
| `reported` | executor/worker claims its work ended | `Code • reported done` |
| `verified` | configured verification gate passed | `Test • verified` |
| `read_back` | external/deployed result was observed | `Ship • read back` |
| `accepted` | declared mission acceptance passed | `Mission • accepted` |

## Claim rules

- `prepared` may never be rendered as “running”.
- `reported` may never be rendered as “verified”.
- task-list completion is not evidence by itself.
- a process exit code proves only what that command contract says it proves.
- CI “green” proves only the checks actually configured in CI.
- deployment command success is not service health; post-deploy readback is separate.
- artifact generation is not visual quality; render inspection is separate.
- configuration presence is not connector readiness; runtime probe is separate.

## Evidence object

Every elevated claim records:

```text
claim_id
mission_id
subject
claim
stage
evidence_type
observer/verifier
source locator
observed_at
freshness/expires_at when relevant
```
