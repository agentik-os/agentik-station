# {{CLIENT_NAME}}

AGK client organization: `{{CLIENT_ID}}`.

This is the legacy shared-operator workflow, not canonical Station client Zone
registration. Its Hermes profile separates runtime state but shares the operator
Unix identity and may share CLI accounts under `HOME`. Different clients and
sensitive environments require separate Station Zones; no automatic migration
or credential copying is performed.

- Runtime: `{{RUNTIME_TYPE}}`
- Hermes profile: `{{HERMES_PROFILE}}`
- Secrets: `~/.config/agk/clients/{{CLIENT_ID}}/env`
- Standard: `../../system/CLIENT-STANDARD.md`

Before acting:

```bash
agk client doctor {{CLIENT_ID}}
eval "$(agk client env {{CLIENT_ID}})"
```

Work starts only from the configured tracker issue and AGK durable work record
(Linear is the default adapter). Production requires an engineering approval
bound to the exact PR/head SHA and a separate deployment authorization.
