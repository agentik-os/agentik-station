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

An OS in this hierarchy is a complete governed domain capability, not merely a
bot team. Its reusable definition and the client's configured instance are
different objects. Environment Zones contain client-owned **OS instances and
Projects as siblings**; Projects are bounded work, not the container of the
Organization. See [OS instances](05_OS_INSTANCES.md) for the executable ownership
and runtime mapping, including routing scope versus Unix isolation.

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
