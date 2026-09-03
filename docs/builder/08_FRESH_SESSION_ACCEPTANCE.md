# Fresh-Session Acceptance

Fresh-session acceptance is a release invariant, not a best-effort test.

## Why

An automation that only works because the build session still holds hidden context is not deployed software.

## Acceptance environment

Create a new Hermes session for the target OS Nano Director/profile. It may use only:

- deployed SOUL/config
- installed ordered skills
- declared MCP/tools
- durable knowledge/memory available by contract
- declared inputs
- deployed deterministic programs
- configured provider routes

It may NOT use:

- builder conversation context
- unstaged local files
- remembered temporary paths
- manual fixes not represented in package/config
- hidden credentials outside the declared resolver

## Automation rule

Cron/persistent automation lifecycle:

```text
created_disabled
-> fresh-session manual trigger
-> evidence pass
-> enable
-> trigger again
-> delivery/readback pass
-> accepted
```

Failure returns the OS to Builder. Never enable first and hope production is the test.
