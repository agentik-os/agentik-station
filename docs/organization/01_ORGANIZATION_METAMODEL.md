# Organization Metamodel

## Universal structure

```text
Organization
└── Macro Domain
    └── Domain
        └── OS
            └── Nano Director
                └── NanoTeam
                    └── Team Director (optional)
                        └── NanoAgents
```

## Why this matters

The execution system is universal.

The business hierarchy is not.

Agentik should be capable of modeling:
- a single person
- a startup
- a fund
- a clinic
- a law firm
- a creative studio
- a holding company
- a family office

without imposing the same departments.

## Metadata examples

Organization:
```yaml
id:
name:
type:
```

Macro Domain:
```yaml
id:
name:
owner:
```

Domain:
```yaml
id:
name:
os:
```

OS:
```yaml
id:
version:
director:
capabilities:
memory_policy:
```
