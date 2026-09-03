# Station Discord Experience — Hermes plugin scaffold

This package implements Zone-local mission-plan state and a fail-closed `pre_tool_call` gate. It is intentionally marked **SCAFFOLDED / NOT_INSTALLED**.

It does not claim to provide the production Discord transport. The remaining gate includes Components V2 rendering, host-owned bot tokens, interaction authorization, rate limits, idempotent message editing, replay, command/message readback, and test-guild acceptance.

## Required runtime context

- `STATION_CURRENT_MISSION_ID`
- `STATION_ZONE_STATE_ROOT`

The database is forced under the current Zone state root. A shared global mission database is forbidden.

Before promotion, validate the package against the Hermes version pinned by Station using the Hermes plugin Doctor, then run the Station contract tests and a real test-guild mission.
