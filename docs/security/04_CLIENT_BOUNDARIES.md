# Client Boundaries

## Target architecture

```text
Agentik Fleet
├── Gareth Node
├── Moonbase Node
├── Dentistry Node
└── Client Nodes
```

## Shared

Can share:
- public OS packages
- reviewed skills
- profile distributions
- Agentik releases
- compatible plugin versions

## Not shared

Must not share by default:
- secrets
- raw memory
- sessions
- databases
- artifacts
- private repos
- production deployment credentials

## Client ownership

Ideal enterprise model:
- VPS belongs to client or dedicated environment
- GitHub belongs to client
- Discord belongs to client
- Linear/Notion belong to client
- data belongs to client
- Agentik installs/updates the runtime and OSs
