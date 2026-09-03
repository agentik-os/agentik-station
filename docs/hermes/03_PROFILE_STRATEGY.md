# Profile Strategy

## Profiles should be scarce and meaningful

Do not create one profile per tiny agent.

Persistent profiles are appropriate for:
- Executive / Oracle
- major Nano Directors
- security-separated specialists
- identities with distinct credentials
- bots requiring durable independent state

## Example internal profiles

```text
core-oracle
business-director
life-director
devops-director
knowledge-director
```

## Example client profiles

```text
moonbase-executive
moonbase-devops
moonbase-knowledge
```

Only create more when needed.

## Use subagents for

```text
architect
backend engineer
frontend engineer
database specialist
QA
critic
reviewer
researcher
risk analyst
writer
editor
```

## Canonical rule

```text
Cognitive difference
→ subagent

Credential / memory / trust difference
→ profile
```

## Profile Distribution strategy

Reusable intelligence should be packaged as distributions.

Example:

```text
agentik-os/director-devops
```

Installed locally as:

```text
gareth-devops
moonbase-devops
dentistry-devops
```

Shared:
- reviewed role logic
- skills
- defaults
- workflows

Local:
- secrets
- memory
- sessions
- deployment-specific config
