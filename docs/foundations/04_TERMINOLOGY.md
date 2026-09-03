# Terminology

## Agentik
Product / workspace / marketplace.

## AGK
Organization protocol, control plane and governance layer.

## Agentik Node
Deployable runtime distribution.

## Hermes
Execution kernel.

## Organization
A person, company or other governed operational entity.

## Macro Domain
Top-level organization grouping.

Examples:
- Business
- Life
- Investment Operations
- Technology

## Domain
Focused operational area inside a Macro Domain.

## Operative System (OS)
Installable operational capability.

## Composite OS
OS that composes several other OSs.

## Domain OS
Focused OS responsible for a subject.

## Nano Director
Persistent authority for an OS.

## NanoTeam
Specialist team composed by a Nano Director.

## Team Director
Optional intermediate orchestrator.

## NanoAgent
Usually an ephemeral Hermes subagent.

## Workforce
Several OSs collaborating on one shared mission.

## Mission
Durable objective represented by a root execution task / graph.

## Project
Long-lived workspace/repository context.

## Board
Durable Hermes execution scope.

## Capability
Typed permission to use an integration/tool/service.

## Skill
Reusable HOW.

## Memory
Machine-oriented retained knowledge.

## Knowledge
Durable documentation, usually Notion/Git/docs.

## Evidence
Proof that an operation or result actually occurred.

## Bot Mode terminology (v3)

- **Bot**: persistent Hermes profile representing a durable AI coworker role.
- **Bot Group**: persistent Hermes multi-Bot collaboration unit; canonical runtime mapping of the persistent portion of a NanoTeam.
- **Mission Worker**: profile executing durable Kanban work; not necessarily a persistent Bot identity.
- **Ephemeral Subagent**: short-lived delegated specialist created with `delegate_task`.


## Orchestration terms

- **Capability lane** — reusable orchestration discipline activated by a mission/OS.
- **Evidence stage** — prepared, observed, reported, verified, read_back or accepted; describes what is actually known, not merely task progress.
- **Capability readiness** — runtime-checked state of an adapter/tool/account for a specific principal/environment.
- **Execution owner** — actor responsible for performing a graph node.
- **Verification owner** — actor/system responsible for a required independent proof gate.
- **Fan-in** — durable integration node that joins parallel branches before system-level verification.
