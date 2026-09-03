# Nano Director and NanoTeam

## Nano Director responsibilities

A Nano Director should:
1. understand domain responsibility
2. resolve context
3. understand mission outcome
4. determine whether it should act
5. plan
6. create/modify durable graph
7. select NanoTeam
8. delegate
9. track blockers
10. enforce verification
11. request approvals
12. produce evidence
13. update knowledge/memory appropriately

## NanoTeam

NanoTeam is a role topology, not necessarily a permanent set of processes.

Example:

```text
Research
Architecture
Engineering
QA
Security
Reviewer
SRE
Knowledge
```

## Role contract

Every role definition should specify:
- purpose
- input
- allowed capabilities
- forbidden capabilities
- output format
- verification responsibility
- escalation policy

## Self-validation rule

The same agent should not be the only authority that:
- implements
- tests
- reviews
- approves
- declares production healthy

## v3 Hermes Bot Mode mapping

- Nano Director -> persistent Hermes Bot/Profile.
- Persistent NanoTeam members -> Hermes Bots.
- NanoTeam collaboration -> Hermes Bot Group.
- Durable work -> Hermes Kanban.
- Temporary specialist -> `delegate_task` subagent.
