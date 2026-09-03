# Builder Mapping: AGK OS v2 -> Hermes + Connected Capability Plane

Builder compiles the OS contract onto existing runtime primitives instead of building a second agent kernel.

| AGK OS v2 primitive | Runtime implementation |
|---|---|
| Nano Director | persistent Hermes Profile/Bot + dedicated Discord identity |
| NanoTeam persistent member | Hermes Profile/Bot |
| durable worker | Hermes Kanban worker profile |
| temporary specialist | `delegate_task` |
| Mission | AGK durable object + Hermes Kanban root task |
| Mission graph | Hermes Kanban DAG + AGK typed edges/acceptance |
| ordered skills | Hermes Skills + explicit skill graph/order |
| deterministic program | script/tool/no-agent cron |
| provider routes | Hermes model/provider routing and per-task override |
| coding isolation | Hermes projects/worktree isolation/sandbox |
| external capability | native Hermes tool, MCP/plugin, Composio session, or direct API |
| automation | Hermes cron/webhook + Station event policy |
| Composio trigger | Station ingress -> OS route -> Mission/Kanban |
| logs | Hermes native logs/events; AGK evidence indexes required proof |
| self-improvement | Hermes learning loop -> governed candidate promotion |
| distributed profile | Hermes Profile Distribution when suitable |

## Compile-time rule

Builder asks, in order:
1. Is deterministic code enough?
2. Is there a Hermes-native primitive/tool?
3. Is an approved plugin/MCP already installed?
4. Does Composio solve the external SaaS auth/tool/session/trigger problem cleanly?
5. Is a dedicated direct API adapter justified?

The answer is recorded in the OS integration adapter contract and verified by Doctor.
