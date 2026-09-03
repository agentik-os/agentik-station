# Module Maturity and Runtime Readiness

Design maturity and live readiness are separate dimensions.

```text
SPECIFIED
→ SCAFFOLDED
→ INSTALLABLE
→ CONFIGURED
→ VERIFIED
→ OPERATIONAL
```

`DEGRADED` means a previously usable module is failing and must include a next repair action.

Examples:

- an OS folder copied into a release is **SCAFFOLDED**, runtime `NOT_INSTALLED`;
- `hermes` on `PATH` is `BINARY_AVAILABLE`, not configured;
- a Discord token stored is not command/message readback;
- a Composio account listed is not a scoped verified session;
- remote installer success is reported execution, not Fleet acceptance;
- a backup file is not recovery until restore rehearsal passes.
