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

Work starts only from a Linear issue. Production requires an engineering
approval and a separate deployment authorization.
