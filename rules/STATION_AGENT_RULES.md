# Station universal agent rules

These rules apply to Hermes profiles, LLM providers, coding CLIs, subagents, automation workers and humans operating through Agentik Station.

## Resolve scope before action

1. Identify the Host, Zone, Project, environment, repository, worktree, principal and requested capability.
2. Stop if the owning Zone or Project cannot be resolved without guessing.
3. Treat the Zone as the hard identity, credential, memory, log and runtime boundary.
4. Treat the Project as the owner of repositories, documentation, knowledge, resources, integrations, credentials, workspaces, worktrees, artifacts and evidence.
5. Development receives no production credential or production write authority by default.

## Respect the Station filesystem

- Desired state and policy: `/etc/station`.
- Immutable releases and shared software: `/opt/station`.
- Human navigation, Zones and Projects: `/srv/station`.
- Durable runtime state, connector state and memory: `/var/lib/station`.
- Logs: `/var/log/station`.
- Recovery material: `/var/backups/station`.
- Ephemeral runtime files: `/run/station`.
- Repositories belong under the owning Project `repos/` directory.
- Parallel coding belongs in the owning Project `worktrees/` or an explicitly declared workspace.
- Project-selected reusable inputs belong in the owning Project `resources/` directory and reference the canonical Station resource catalog.
- Never place Project work in `/root`, `/tmp`, `/var/www`, an arbitrary home directory or an undeclared container volume.
- Never create a second editable copy of a canonical OS. Canonical OS source lives only under `os/` in the active Station source/release.

## Hermes is the execution orchestrator

1. Station defines desired state, isolation, policy, capability contracts and evidence requirements.
2. Hermes owns profile execution, sessions, Bot Mode, delegation, Kanban work, Skills, plugins, MCP, provider routes, cron, hooks, memory and learning candidates.
3. An LLM provider supplies cognition; it does not become the authority, system of record, secret store or deployment controller.
4. Prefer existing code, then Hermes-native capabilities, then platform/standard-library functions, installed dependencies, MCP/Composio/API adapters, and finally the smallest justified new implementation.
5. Cross-OS collaboration happens through Hermes missions, delegation and capability contracts. Public Discord bots must not converse recursively with each other.

## Mission and engineering order

For non-trivial work follow this order:

```text
clarify scope
→ inspect existing state
→ produce a Plan First graph
→ select the smallest allowed capabilities
→ create/use the owning workspace or worktree
→ implement
→ test and Doctor
→ independent review when risk warrants it
→ external readback when a real system changed
→ record evidence and next repair action
→ accept only when the declared gate passed
```

Do not skip directly from generated output to a completion claim. Preserve the distinction between `prepared`, `observed`, `reported`, `verified`, `read_back` and `accepted`.

## Tools, resources and stacks

- Discover reusable resources through `station resource list` before adding a dependency or inventing a component.
- Use the exact versions in `config/versions.lock` and `resources/CATALOG.json` unless a reviewed Project decision intentionally changes them.
- The preferred web-product recipe is Next.js + React + Convex + Clerk + Stripe + Tailwind CSS + shadcn/ui + Lucide.
- The preferred recipe is not a lock-in. Another stack is allowed when the Project contract records the reason, lifecycle, security boundary, verification command and owner.
- shadcn is an installed operator CLI; shadcn components and Lucide icons remain Project dependencies and must be added inside the owning repository.
- Never install application dependencies globally merely to make one Project build pass.
- Keep generated assets, package locks and framework configuration in the owning repository; keep secrets outside Git.

## Credentials and connected accounts

- Never pass secrets in command-line arguments, commit them, print them, paste them into evidence or copy them across Zones.
- Enroll credentials through the owning provider/Hermes interactive flow or a narrow credential file/service mechanism.
- GitHub, Vercel, Clerk, Stripe, Convex, Discord, Composio and model-provider identities are scoped to their owning Zone/Project principal.
- A binary or login is not proof that a capability works. Verify the exact account, scope and readback.
- Destructive or production actions require the policy-defined human authorization; model text cannot authorize itself.

## Discord

- Discord is a human control surface and projection, not the source of truth.
- One installed OS has one Nano Director Hermes profile, one dedicated Discord bot identity and one primary channel unless an explicit topology contract says otherwise.
- A bootstrap bot may receive temporary broad guild permissions during an approved maintenance window. The server owner must verify and remove that elevation before acceptance.
- Runtime bots use only their required guild/channel permissions and immutable ID bindings.
- A token is entered only in the owning Zone's Hermes/credential setup and is never stored in the repository or Control projection.

## Completion

- Run the relevant unit, contract, security and integration tests.
- Run Station Doctor and provider-specific Doctor/readback.
- Keep every unexercised external integration below `OPERATIONAL`.
- Report exact limitations and the next action needed to advance readiness.
