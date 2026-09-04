# Local and Remote Placement

Local and remote are Fleet placement decisions.

```text
organization-alpha-dev  → station-core-01
organization-alpha-prod → organization-alpha-prod-01
example-project-dev     → station-core-01
example-project-prod    → example-project-prod-01
```

A Host registry entry describes connectivity, role and health. A Zone registry entry references its Host. Projects and OSs do not care whether the Host is the Operator VPS or a remote VPS.
