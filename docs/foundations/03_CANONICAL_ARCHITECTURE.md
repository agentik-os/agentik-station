# Canonical Architecture — Station v7

```mermaid
flowchart TB
  H[Human / Event / API / Trigger] --> SURF[Discord / Agentik UI / Webhook]
  SURF --> HG[Hermes Gateway / Ingress]
  HG --> S[Hermes Session]
  S --> ND[Nano Director Hermes Bot/Profile]
  ND -->|temporary| DEL[delegate_task]
  ND -->|durable| M[AGK Mission]
  M --> K[Hermes Kanban Root Task / DAG]
  K --> W[Worker Profiles / Projects / Worktrees / Sandboxes]

  AGK[AGK OS v2 Desired State] --> SC[Station Controller]
  SC --> HP[Hermes Profiles/Skills/Plugins/Cron]
  SC --> CP[Capability + Identity Policy]
  CP --> ADAPTER{Adapter}
  ADAPTER --> HTOOLS[Hermes native]
  ADAPTER --> MCP[MCP / Plugin]
  ADAPTER --> COMP[Composio Session]
  ADAPTER --> API[Direct API]
  COMP --> SAAS[External SaaS]
  MCP --> SAAS
  API --> SAAS

  W --> E[Evidence / Evals / Hermes Logs]
  SAAS --> E
  K --> E
  E --> V[Schema-backed Views / Discord / Agentik UI]
```

## Rule

AGK defines *what is allowed and what outcome exists*. Hermes decides *how agentic execution runs*. Composio may supply a scoped external-tool/auth plane. Station enforces boundaries and lifecycle. Agentik distributes and visualizes the resulting organization.
