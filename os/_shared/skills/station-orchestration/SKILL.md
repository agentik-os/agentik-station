---
name: station-orchestration
description: Plan and execute scoped Station missions through native Hermes roles, delegation, goals, Kanban, cron and knowledge workflows, with bounded autonomy and evidence-based acceptance. Use for multi-step work, role-routing ambiguity, durable task graphs or selection among these execution modes.
---

# Station orchestration

Hermes executes the work; Station establishes ownership, policy, isolation and
acceptance. This skill grants no additional credentials, filesystem access,
production authority or permission to activate recurring work.

## 1. Resolve the owner before selecting an executor

Identify the Host, Zone, Organization if applicable, OS instance, canonical role,
environment and principal. For Project work, identify its repository and owning
workspace/worktree. An OS-owned mission can use its instance workspace without
inventing a Project. In personal Workstation mode, first resolve the validated
Workstation context; do not apply Linux Host/Zone provisioning to it.

Read the available package catalog and the selected trusted instance record
through the authorized Station surface. Existing CLI forms include:

```text
station os catalog --json
station os instance show --zone <zone> --instance <instance>
station os instance setup --zone <zone> --instance <instance> --role <role> --plan
```

These are examples with placeholders, not commands to run without resolved
identifiers. A catalog entry means available software, not user membership or
an installed instance. A role name such as `master-os-builder` is not necessarily
an OS package ID. Resolve the role-to-native-profile mapping from the selected
instance; do not guess another profile when a name is unavailable. If that
instance is missing or unreadable, report the exact missing selection/access
and next safe setup action. Do not rerun Host bootstrap, adopt an unrelated
profile or install a replacement instance merely to answer a routing question.

Zone Unix identity is the hard isolation boundary. A profile, board, tenant
filter or allowed-Project list is not a filesystem sandbox. Profiles within one
Zone can share its UID and some gateway/CLI state. Do not copy `.env`, auth,
cookies, provider keys, memories or account stores between profiles or Zones.

## 2. Make a small mission graph

Record the requested outcome, current evidence, scope/non-goals, deliverables,
owners, dependencies, risks, verification commands and stop conditions in the
owning workspace/evidence namespace. Distinguish observed facts from assumptions.
For each parallel branch assign an execution owner and verification owner.

Use this leverage order: existing code or resource, native Hermes capability,
platform/stdlib, installed dependency, authorized connector/API, then the
smallest justified new implementation. Probe availability before relying on a
tool or account. Prefer a short deterministic program when the operation does
not require model judgment.

| Need | Native execution choice |
| --- | --- |
| One bounded action | A normal turn or one-shot invocation in the resolved profile |
| Independent side investigation | `/bg` with its own complete prompt and scope |
| Redirect active work / follow up later | `/steer` / `/queue`; neither grants wider scope |
| Independent branches needed for this answer | Transient `delegate_task` children in the parent's context, bounded by native depth/concurrency |
| A task requiring a persistent specialist's profile | Explicit scoped native one-shot invocation of its mapped profile, after enrollment |
| One outcome needing repeated turns | `/goal` with explicit criteria and deterministic gates |
| Durable handoffs, dependencies or review by named roles | A Kanban board and scoped cards |
| A recurring or event-triggered routine | Prepare native cron/webhook configuration; activation is a separate authorized action |

## 3. Route roles and delegate bounded work

Use an existing instance role for a persistent responsibility. Use a transient
child for a cognitive subtask that does not need a new account or durable
identity. Route domain work to its installed Director and specialists using
their declared capability contracts; do not create a persistent profile for
every small task.

`delegate_task` has no profile selector. Its task fields are `goal`, `context`
and optional `output_schema`; naming a mapped role in the task does not load
that role's configuration, SOUL, skills, memory or accounts. Use this tool only
when a child in the parent's inherited context is the intended executor. Do not
invent a `profile` field or report that a persistent specialist ran merely
because a transient child was given its title.

A child assignment must contain: objective, relevant context, exact owned
files/responsibility, allowed inputs and outputs, forbidden side effects,
verification criterion and return format. Tell coding children they are not
alone: preserve others' edits and use separate declared worktrees for concurrent
changes. Do useful independent work while they run; do not duplicate the same
investigation merely because it was delegated.

Honor the resolved native concurrency, depth and iteration limits. The reviewed
Station example is 3 children, depth 2 and 50 child iterations, but inspect the
installed configuration rather than assuming those values. Hermes derives
further-delegation capability from child depth, `max_spawn_depth` and
`orchestrator_enabled`; the legacy `role` argument is ignored. At depth 2 with
the switch enabled, first-level children can delegate. A task instruction is
not an enforcement mechanism for making a child a leaf. Do not increase limits
or enable automatic approval to get past a failure.

Native children inherit the parent's permitted tools and provider context;
an assignment is not an access-control boundary. Keep sensitive work in the
correct Zone/profile. Parent completion requires integrating child results and
checking their evidence. Background child execution is not a durable worker
service: after interruption/crash, read state and reconcile before retrying.

For a persistent mapped-role task, first confirm the selected instance/OS home,
owning Unix identity, native profile, provider enrollment, approved workspace,
task authority and applicable budget. Resolve the reviewed native Hermes
executable directly; a convenience launcher that fixes a Director is not a
general specialist selector. This schematic argv uses the pinned native parser:

```text
hermes --profile <mapped-native-profile> chat --oneshot --query-file /absolute/owning-workspace/task.md
```

Replace placeholders only from the trusted instance record and exact role map.
Use the owning private `HOME`, selected instance's base `HERMES_HOME`, and owning
workspace as process cwd. Native selection can rewrite `HERMES_HOME` to the
effective profile directory; do not reuse that value as the base. Resolve the
base from trusted runtime evidence. In Workstation mode consult its private
`OS_INSTALL.json`/`PERSONAL.json`; do not append another `--profile` to a
`stepper`, `builder` or `librarian` launcher. Keep the task file absolute, scoped
and nonsecret; do not put credentials in argv or copy `.env`, auth, memory or
provider stores to make another profile work.

The pinned parser accepts an optional `--max-turns N`, a per-conversation-turn
tool-iteration bound forwarded by the native consumer. Choose a positive bound
only within the authorized task budget; never increase an applicable limit or
start repeated profile invocations to bypass an exhausted budget. This is not
a USD or mission-wide cap. Keep output/evidence in the owning workspace and
verify the actual selected profile and result before claiming a role handoff.

If a peer is unenrolled, its scope is unknown, or the permitted invocation path
is unavailable, produce a scoped handoff artifact with the missing selection or
acceptance and continue independent authorized work. Do not switch to another
account, bypass the legacy AGK identity guard, activate a dispatcher, or start a
new service as an implicit fallback. Named-role and cross-OS live orchestration
remain NOT_VERIFIED until an enrolled bounded task roundtrip is accepted.

## 4. Use goals for iteration, gates for truth

For an authorized multi-turn objective, express `/goal` with:

- the concrete deliverable;
- how to verify it;
- constraints and preserved behavior;
- the permitted scope;
- when to stop, report a blocker or request a new decision.

Use `/subgoal` to add acceptance criteria without replacing the active goal.
Add deterministic `/goal gate` commands only after reviewing their exact
workspace, effects and suitability. A gate can execute code; a command named
test is not automatically read-only. Preserve independent review for critical
changes and external readback for account/service claims.

Goals are single-session. They do not create Kanban cards or transfer work to
another profile. A native judge's done verdict, a paused budget or a blocked
objective is not proof that the mission succeeded. Use native wait/continuation
behavior for in-flight work; do not repeatedly wake a model to poll unchanged
state when a deterministic watcher or completion notification suffices.

## 5. Use Kanban for durable coordination

Select the board belonging to the resolved scope and inspect existing cards
before creating new ones. Give every card an assignee resolved from the instance
role map, acceptance criteria, dependencies, a declared workspace and an
idempotent identity where supported. Use the native `kanban_*` tools when they
are available to the agent; the CLI remains appropriate for authorized human
or deterministic automation paths.

Use the native review state for independent verification. Do not mark a card
done while its mandatory evidence is missing. Use worktree or an explicit
absolute `dir:` workspace for deliverables that must survive completion; default
scratch workspaces can be deleted. Attach final artifacts through the native
completion mechanism before scratch cleanup.

Do not start a second dispatcher for the same board. Do not activate dispatch,
auto-decomposition or review workers on an unaccepted board merely because a
gateway is installed. Respect existing approved scheduling and capacity limits.
After a crash, inspect claims, outputs and prior external effects before retry;
avoid duplicate messages, releases, payments or other irreversible effects.

## 6. Prepare routines without silently activating them

For recurring work, first specify owner, purpose, cadence, workdir, input trust,
delivery destination, runtime bound, retry/idempotency policy and disable/repair
action. Prefer `no_agent` for deterministic script-only jobs. A reviewed script
can emit a `wakeAgent` decision to avoid an unnecessary model run; inspect the
script and output contract rather than trusting its name.

Use `context_from` only for explicitly authorized upstream jobs in the same
scope. Treat their output as data, preserve source/time and account for missing
or stale results. Never use it to bridge client/Zone data accidentally. Prepare
an inactive proposal or reviewed plan; do not enable cron, gateway startup,
webhook listeners, API endpoints or recurring paid work unless that specific
activation was authorized and its acceptance checks are complete.

## 7. Separate memory from a knowledge repository

Use native profile memory for small, durable facts and user preferences relevant
to this owner. Keep one factual concern per entry, consolidate duplicates, and
respect character limits and write-approval settings. Do not save raw logs,
credentials, temporary task state or another client's information. Verify
cross-session recall when persistence is part of the requested outcome.

Use the existing `llm-wiki` / `obsidian` skills for a larger linked knowledge
base. Resolve `WIKI_PATH` / `OBSIDIAN_VAULT_PATH` to a reviewed absolute path in
the owning Project/OS knowledge area; never silently create a vault at the
upstream home-directory fallback. File tools require resolved paths, not shell
variable strings. Preserve sources, dated observations, uncertainty,
contradictions and links from synthesis back to evidence. Do not publish or
move private knowledge to a service without the relevant authority.

## 8. Control effort without inventing a financial guarantee

Honor `agent.max_turns`, `delegation.max_iterations`, `goals.max_turns` and
concurrency limits. These bound different execution loops, not the entire bill.
`agent.run_budget_seconds` is a separate optional run-time control. Use approved
profile/delegation/cron routes and `auxiliary.goal_judge` where configured; do
not silently change providers or assume a SKILL.md `model:` field routes calls.

No generic native daily/session/monthly USD hard cap was verified at the reviewed
Hermes pin. Report estimates as estimates. Provider spending controls require
their own account setup and readback. Compression preserves usable context; it
is neither a permission change nor a spending ceiling. Do not reset budgets,
spawn another profile or bypass a scanner to evade a limit.

## 9. Finish with evidence, or a precise next action

Act autonomously on authorized, scoped, reversible work; preserve unrelated
edits and existing runtime/account state. Before a destructive or production
effect, verify the exact targets, applicable authorization, recovery plan and
post-action readback. If the current authority is insufficient, stop at that
boundary, not at every routine implementation step.

Report the outcome first, then changed artifacts, checks actually run, observed
results, untested account/service gates and the next repair action. Use
prepared, observed, verified, read_back and accepted accurately. A delivered
manifest, installed binary, model claim or green liveness endpoint is not
OPERATIONAL. Do not print credentials, full private configuration or unrelated
client data into summaries, logs or evidence.

## Reference baseline

This procedure was checked against Hermes commit
`29112bef099274229cadff79cdff7bf7b99c4b77`; revalidate native keys and commands when
the Station pin changes. In a Station checkout, see
`docs/hermes/16_CAPABILITY_LADDER.md` for the complete fifteen-capability map and
immutable source links, and `rules/STATION_AGENT_RULES.md` for the governing
cross-provider contract. This skill is operational guidance, not a replacement
for native permissions, Station's runtime ledger or live acceptance.

Pinned execution contracts: [delegate task schema](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/tools/delegate_tool.py#L5088),
[depth-derived child capability](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/tools/delegate_tool.py#L1738),
[profile selection](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/main.py#L516),
[one-shot query and turn options](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/_parser.py#L353),
[turn-bound consumer](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/main.py#L3481).
