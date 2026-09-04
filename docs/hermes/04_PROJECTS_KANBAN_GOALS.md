# Projects, Kanban and Goals

## Project

Use Hermes Project as the durable workspace abstraction.

```text
AGK Project
→ Hermes Project
→ one or more repos/folders
```

## Board

Bind a board to a project.

```text
Hermes Project
→ Board
→ Missions
→ Tasks
```

## Board boundary

A board is a durable execution boundary.

Avoid one board per trivial task.

Good:

```text
agentik-platform
organization-alpha-platform
personal-life-system
```

Bad:

```text
fix-button-board
write-email-board
```

## Mission

One important intention becomes one root mission.

Example:

```text
MB-142 Searcher Scoring
├── research
├── architecture
├── data model
├── backend
├── UI
├── tests
├── QA
├── review
└── deployment verification
```

## Goal mode

Use Goal mode for tasks with:
- explicit outcome
- acceptance criteria
- verification
- stop conditions

## Deterministic gates

Engineering examples:

```text
pytest
npm test
npm run lint
npm run typecheck
npm run build
```

An agent should not be able to declare success while mandatory gates are red.

## Review lifecycle

```text
ready
→ running
→ review
→ approved → done
          ↘ changes requested → running
```
