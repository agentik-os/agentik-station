# {{CLIENT_NAME}}

AGK client organization: `{{CLIENT_ID}}`.

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
