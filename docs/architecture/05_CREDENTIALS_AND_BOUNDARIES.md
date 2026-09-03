# Credentials and Boundaries

Credentials are scoped at Zone or Project level and delivered at runtime. Git stores only examples, schemas, encrypted blobs when appropriate, and external secret references.

Default file modes:

```text
Zone root        0750
credentials/     0700
credential files 0600
```

Services run as Zone identities. Use systemd credential delivery and hardening where applicable. Do not rely on `protect-*.sh` scripts to enforce isolation.
