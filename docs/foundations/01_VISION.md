# Vision

## Product promise

> **Hire an AI team. Install its operating system. Connect Discord. Start operating.**

The experience should feel closer to installing an operating organization than assembling bots and workflows by hand.

## Agentik

Agentik is the product, workspace, installer, fleet manager and marketplace.

It owns:
- Node installation and lifecycle
- OS installation and upgrades
- organization desired state
- fleet health
- marketplace/distribution
- universal UI
- licensing/billing where applicable

It is not merely a chatbot, workflow editor, app builder or collection of agents.

## AGK

AGK is the organizational protocol, standard and governance layer.

AGK defines:
- organization hierarchy
- OS contracts
- mission lifecycle
- typed capabilities
- permissions
- evidence/evaluation requirements
- composition of OSs
- context and routing contracts
- recovery rules
- Discord surface contracts
- desired-state schemas

AGK should avoid duplicating Hermes execution primitives.

## Agentik Node

Agentik Node is the deployable runtime distribution and the primary organization isolation boundary.

A Node can be installed for:
- Gareth
- a company
- a client
- a lab
- an enterprise

Client development may run in an isolated local Zone on Gareth Station. Production placement is policy-driven and normally uses a dedicated client Host/Node when stronger isolation or ownership is required.

## Hermes

Hermes is the execution kernel.

Hermes owns as much execution infrastructure as possible:
- messaging gateway
- sessions
- persistent profiles
- subagent delegation
- projects
- Kanban boards/tasks
- worktrees
- skills
- plugins/hooks
- MCP/toolsets
- provider/model routing
- memory provider integration
- cron/webhooks
- checkpoints/diagnostics

AGK should compile policy and organization intent into Hermes configuration and plugins rather than build a second orchestration engine.

## Operative System

An Operative System is an installable operational capability.

An OS may contain:
- Nano Director
- persistent worker profiles where trust/identity requires them
- dynamic subagents
- skills
- programs/workflows
- capabilities
- memory/data schemas
- knowledge contracts
- evaluations/evidence
- permissions
- Discord surface declarations
- Agentik UI views
- doctor/recovery logic

An OS may itself compose other OSs.

## Discord as compiled organization cockpit

The organization and installed OSs declare desired interaction surfaces.

Agentik compiles those declarations into:
- roles
- role hierarchy
- categories
- text/forum/voice channels as needed
- permission overwrites
- routing bindings
- channel topics/metadata
- slash-command scopes
- mission thread policies

The human should not have to manually construct the server after every installation.

## Organization model

Agentik provides a metamodel, not one universal org chart:

```text
Organization
→ Macro Domain
→ Domain
→ OS
→ Nano Director
→ NanoTeam
→ Team Director (optional)
→ profiles / subagents
```

## Example: Gareth

```text
Gareth
├── Business
│   ├── Strategy
│   ├── Product
│   ├── Content
│   ├── Sales
│   ├── Network
│   ├── Capital
│   └── Knowledge
├── Life
│   ├── Journal
│   ├── Decision
│   ├── Mindset
│   ├── Relationship
│   ├── Connector
│   ├── Learning
│   ├── Performance
│   └── Wealth
└── Agentik / Products
    ├── Agentik
    ├── AGK
    ├── Hermes integration
    └── OS Factory
```

## Example: Moonbase

```text
Moonbase Capital
├── Investment Operations
│   ├── Searchers
│   ├── Dealflow
│   └── Portfolio
├── Fund Operations
│   ├── LP
│   ├── Fundraising
│   └── Investor Reporting
├── Technology
│   ├── Product
│   ├── DevOps
│   ├── Data
│   ├── QA
│   └── Security
└── Corporate Operations
    ├── Finance
    ├── Legal
    └── Backoffice
```

These structures are intentionally different; Discord is generated from each organization rather than copied from Gareth.
