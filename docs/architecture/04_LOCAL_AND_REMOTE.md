# Local and Remote Placement

Local and remote are Fleet placement decisions.

```text
moonbase-dev  → gareth-core-01
moonbase-prod → moonbase-prod-01
verba-dev     → gareth-core-01
verba-prod    → verba-prod-01
```

A Host registry entry describes connectivity, role and health. A Zone registry entry references its Host. Projects and OSs do not care whether the Host is the Gareth VPS or a remote VPS.
