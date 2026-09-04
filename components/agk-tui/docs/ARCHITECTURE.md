# Architecture

## Multi-user topology, single control plane

```text
profile_id                 TopologyManager                 runtime boundary
operator  ───────────────▶ linux-user:operator ─────────▶ Hermes + RMUX + workspace
agentik   ───────────────▶ linux-user:agentik  ─────────▶ Hermes + RMUX + workspace
mission   ───────────────▶ linux-user:mission  ─────────▶ Hermes + RMUX + clients
private   ───────────────▶ linux-user:private  ─────────▶ Hermes + RMUX + workspace
                                   │
                                   └── shared official Hermes code
                                       /opt/agk-terminal/hermes-agent
```

Business objects, Discord bindings and AGK commands use `profile_id`. Only
TopologyManager knows the Linux username mapping. This keeps the current VPS
strongly isolated while allowing a later single-user deployment to use the
same product model. Mission client runtime topology (`local`, container,
remote VPS, or external) remains separate from profile topology.

Mission can additionally host the optional `collective` Hermes named profile.
It keeps independent credentials, sessions and a canonical
`hermes-gateway-collective.service`, while remaining inside the Mission Linux
boundary at `~/.hermes/profiles/collective`.

The canonical declaration is `config/topology.yaml`; a system install writes
it to `/etc/agk-terminal/topology.yaml`. `agk-terminal topology status` audits
the mapping without mutation, while `topology apply --yes` only creates missing
directories/manifests and updates the official-Hermes compatibility symlink.
It does not move or delete user content.

## Workspace and knowledge boundaries

- Operator owns infrastructure, security, deployments, monitoring,
  automation, deposit and system documentation.
- Agentik owns products, projects, missions, research, content, growth,
  community, reusable knowledge and generated artifacts.
- Mission owns client roots. Every client receives its own identity, projects,
  missions, knowledge, artifacts, infrastructure and automation directories.
- Private owns personal projects, journal, goals, learning, research,
  knowledge and artifacts.

Hermes state remains profile-local in `~/.hermes`; AGK registry state remains
profile-local in `~/.agentik`. Official built-in skills come from the shared
Hermes checkout, while profile-installed skills and MCP credentials remain
inside their Linux security boundary. Composio is exposed uniformly through
`agk-terminal composio`, but each profile authorizes its own account.

AGK also reads eligible active messaging sessions from the profile-local
Hermes `state.db`. It projects them as resumable entries in Sessions and, for
named profiles, beneath the corresponding catalog agent. Resuming creates an
RMUX wrapper around the existing native Hermes session ID; it does not copy or
translate the transcript. Discord's session selector resolves the same IDs
through Hermes' protected cross-platform resume path. See
[Conversation continuity](SESSION-SYNC.md).

```text
AGK native TUI
  ├─ reads ~/.agentik/{runtime,control}.db
  ├─ controls RMUX through its public CLI/SDK contract
  ├─ launches provider TUIs inside durable RMUX sessions
  └─ reads redacted provider, skill, MCP and OS inventory

Official Hermes Agent
  ├─ ~/.hermes/plugins/agentik_os  (AGK domain/runtime tools)
  ├─ ~/.hermes/plugins/platforms/discord
  │                                  (AGK control center; shadows bundled Discord)
  ├─ ~/.hermes/agents/master-os-builder
  ├─ ~/.hermes/skills              (official and user skills)
  ├─ ~/.hermes/config.yaml         (MCP and gateway configuration)
  └─ ~/.hermes/.env                (secrets; never copied into this repo)

Composio CLI
  ├─ authenticated SaaS actions through `link`, `search`, `tools list`,
  │  `execute`, `run`, and `proxy`
  └─ ~/.agentik/composio-connections.json
     redacted toolkit/status/count cache refreshed after login/link and by
     `agk composio list`; account IDs, aliases and credentials are excluded.
```

The core has no provider credentials. Provider installation is an explicit
foreground action and uses the provider's official installer. Existing user
homes are preserved during upgrades and runtime refreshes.

The Discord override is intentionally isolated from Hermes core. Its patch
provenance is recorded beside the plugin so it can be rebased or retired when
the same controls land upstream.
