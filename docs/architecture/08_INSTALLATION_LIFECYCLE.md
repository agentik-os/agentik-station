# Installation lifecycle

```text
REPOSITORY_CLONED
→ PLAN_READY
→ HOST_BASE_APPLIED
→ STATION_INSTALLED
→ BASE_ZONES_CREATED
→ RUNTIME_INSTALLED
→ SERVICES_INSTALLED
→ DOCTOR_PASS
→ READY_FOR_SETUP
→ INTEGRATIONS_ENROLLED
→ DISCORD_PROVISIONED
→ FRESH_SESSION_ACCEPTED
→ OPERATIONAL
```

Installation and setup are deliberately distinct because secret enrollment and external OAuth/Discord application ownership cannot safely live in a public or reusable repository.
