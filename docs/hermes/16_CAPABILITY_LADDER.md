# Fifteen Hermes capabilities, mapped to Station

This is a capability reference, not a claim that fifteen live integrations are
configured. Review baseline: Hermes commit
`29112bef099274229cadff79cdff7bf7b99c4b77`, selected by
`config/versions.lock` as release `v2026.8.31`. Its Python package version is
`0.21.0`; the supplied article's `v0.17.0` label is not Station's runtime version.
Nineteen official source/documentation files were fetched at that immutable
commit and compared byte-for-byte with the reviewed local checkout.

The article is a useful menu, not an authority for commands, defaults, security
boundaries, prices or readiness. Where upstream documentation disagrees with
the implementation, the pinned parser, defaults and consumer code take priority.

## Capability map

| Level | Verified native capability | Station path and remaining acceptance |
| --- | --- | --- |
| 1. One-shot and setup | One-shot chat and quick, full and blank-slate setup flows exist. [Setup source][setup] | Use the immutable Station installation and the owning Zone/OS instance. `hermes_platforms.py` deliberately selects `setup model` for provider enrollment: the full wizard can offer gateway installation/start. A successful install is not a successful authenticated conversation. |
| 2. SOUL, MEMORY, USER | `SOUL.md` supplies identity. `MEMORY.md` and `USER.md` live under the profile's `memories/`; they have character budgets and session-start snapshots. The native memory tool uses atomic file replacement. [Memory][memory], [writer][memory-tool] | `os_runtime.py` compiles SOUL plus Station rules. Keep personal facts in the selected profile, not the distribution. Verify a bounded, nonsecret write and new-session recall; never seed another person's memory or assume atomic writes make a shared home safe for independent agents. |
| 3. Background and busy input | `/bg`, `/steer`, `/queue` and `/model` exist. `/bg` starts a separate conversation without the foreground history. `display.busy_input_mode` supports `interrupt`, `queue`, `steer`; upstream defaults to `interrupt`. [Command registry][commands], [CLI][cli] | Use native interaction controls; no second Station background scheduler. Give `/bg` its own complete scope and output contract. Test steering/queuing and cancellation before unattended use. The current registry does not register `/background`. |
| 4. Skills and hubs | Native skills, bundles, discovery, hub installation and security scans exist. [Skills][skills] | Canonical OS skills come from `os/`; the shared operational package is `os/_shared/skills/station-orchestration/`. Review external skill provenance and scanner findings before installation. No automatic per-SKILL.md `model:` routing was verified; use supported profile, delegation or cron model configuration instead. |
| 5. MCP and Tool Search | A reviewed MCP catalog and deferred tool discovery exist. `tools.tool_search.threshold_pct` defaults to **5**, not 10; it bounds the injected listing. `auto` currently enables the bridge whenever deferrable tools exist. [MCP][mcp], [Tool Search][tool-search] | The SDK and a disabled ChatbotX example are delivered separately from account enrollment. Review source/bootstrap commands, configure one profile, select exact tools and test identity/readback. Keep resources, prompts, sampling and elicitation closed unless explicitly needed. A catalog install can execute third-party code. |
| 6. Delegation | `delegate_task`, background results and leaf/orchestrator roles exist. Executed defaults are **10 concurrent children, 250 child iterations, depth 1**. Some upstream prose still says 3/50. [Defaults][delegation-defaults], [consumer][delegate-source] | Station can deliberately select 3 children, 50 iterations and depth 2; those are Station bounds, not upstream defaults. Native children inherit the parent's credential/tool context, with child restrictions. Use independent worktrees for concurrent edits and explicit file ownership. Background completion records do not make in-process child execution crash-durable. |
| 7. Goals, cron and checkpoints | `/goal`, `/subgoal`, a judge and deterministic goal gates exist; the default goal budget is 20 continuation turns. Cron's default tick is 60 seconds; `no_agent`, script `wakeAgent` gates and `context_from` are supported. Checkpoints are opt-in, disabled by default. [Goals][goals], [cron][cron], [checkpoints][checkpoints] | Use explicit criteria, evidence and stop conditions. A goal does not create a Kanban card. Prepare schedules without activation; enable only an authorized routine after reviewing scope, principal, workdir and delivery. Checkpoints are partial file recovery, not database backups or rollback of external actions. |
| 8. Profiles | Profiles separate Hermes configuration, credentials and state, but are not OS sandboxes. Native clone flows can copy credentials. [Profiles][profiles] | Station's hard boundary is the Zone's Unix identity. Namespaced instance roles resolve to native profiles; compiled tools also use `terminal.home_mode: profile`. Roles within a Zone still share its UID. Never clone accounts across Zones or treat a different profile name as a filesystem access barrier. |
| 9. Wiki and Obsidian | Bundled `llm-wiki` and `obsidian` skills use `WIKI_PATH` and `OBSIDIAN_VAULT_PATH`. They operate on files, not a newly installed knowledge server. [Wiki][wiki], [Obsidian][obsidian] | Bind a reviewed absolute Project/OS knowledge path. Do not silently use the upstream home-directory fallbacks. Resolve variables before file-tool calls; preserve source provenance, contradictions and links. Verify retrieval and owner permissions using nonsecret material. |
| 10. Kanban | SQLite-backed boards support dependencies and `triage/todo/ready/running/blocked/review/done/archived`. The gateway dispatcher normally ticks every 60 seconds. Goal-mode cards borrow the goal engine. [Kanban][kanban] | Reuse the Station Project/mission mapping and namespaced role assignments. Review dispatcher activation and concurrency. Use declared `dir:` or worktree workspaces for durable work: default scratch workspaces can be removed at completion. A board or tenant filter does not replace Zone isolation. |
| 11. Voice | Native STT/TTS, CLI audio and messaging voice exist, with provider, extras and codec requirements. [Voice][voice] | Station ships reviewed voice defaults, codecs and a local Parakeet path; `station voice setup` enrolls one instance role explicitly. Verify input, transcript, selected fallback and actual reply on the intended account/channel. Software health alone does not prove live voice acceptance. |
| 12. Browser | Local/cloud browser drivers and disposable browser sessions exist. Using a real browser profile can copy cookies and logins and is an explicit opt-in. [Browser][browser] | Station's Playwright/Chromium and governed `station-web` extraction do not by themselves prove that Hermes' `browser-use` or `agent-browser` driver is ready. Probe the selected native driver separately, then test a scoped page. Do not adopt personal logins or enable cloud/private-network routing implicitly. |
| 13. Compatible API | Hermes' gateway exposes an OpenAI-compatible API, normally at `127.0.0.1:8642`, with required bearer authentication. The API includes access to the agent's tools, including terminal execution. [API][api], [activation code][api-config] | Treat enrollment as a privileged integration. Keep `platforms.api_server.enabled: false` until explicitly selected: a usable `API_SERVER_KEY` can otherwise auto-enable the adapter. Use a profile-local credential, restricted bind/CORS and negative authentication tests. Public `/health` is liveness, not authenticated readiness. |
| 14. ACP | The command is **`hermes acp`**, not `hermes acp start`. `hermes acp --check` checks adapter dependencies. The pinned extra requires `agent-client-protocol==0.9.0`. [Parser][acp-parser], [ACP][acp], [dependency][pyproject] | Source availability is not installation acceptance. At the review baseline the Workstation sync selected voice/messaging/mcp, not acp; check actual installed extras. Verify a handshake with the selected editor and its approval behavior. A bridge can auto-approve requests, so transport connectivity is not a safety guarantee. |
| 15. Profile distributions | Git distributions package SOUL/config/skills/cron/MCP/plugins. Installation excludes credential/history paths; profile exports are broader and may contain personal memory and sessions. [Distributions][distributions] | Reuse Station's compiler, native profile installation and trusted runtime ledger. Keep `os/` as the only editable OS source and review immutable content. Do not replace an installed instance via an unreviewed remote profile update, copy credentials or activate imported schedules automatically. |

## Corrections that affect implementation

- **Not a fifteen-step readiness scale.** These are independent capabilities.
  Installing libraries, delivering manifests, configuring an account and proving
  an operational workflow remain separate states.
- **Background is `/bg`.** A background conversation needs its own context;
  `/steer` modifies the running conversation and `/queue` schedules its next turn.
- **Default drift is real.** At this pin, the delegation documentation's 3/50
  examples disagree with the executed 10/250 defaults. Depth is 1. Set intended
  Station bounds explicitly and verify the resolved native values.
- **Tool Search is not triggered at 10% of context.** Its current 5% setting is
  a catalog-listing budget, further bounded by `listing_max_tokens`.
- **A skill is not a model router.** Keep route intent in the OS provider policy
  and apply it through supported native model/provider configuration. Do not add
  an unconsumed YAML key and claim that it changes execution.
- **No generic USD hard caps were verified.** The pinned config/consumers do not
  establish daily/session/monthly dollar ceilings. Provider-specific billing
  controls are separate. Local counters and estimates cannot guarantee a bill.
- **Goal completion is not acceptance.** A judge can be wrong or stop on a
  blocked objective. Deterministic gates and relevant account/service readback
  remain mandatory; a stop or paused budget is never proof of success.
- **Raft is a separate optional integration.** Hermes does include an adapter
  for [raft.build][raft]: `RAFT_PROFILE` activates a wake bridge. It requires a
  Raft CLI, an authenticated External Agent and a workspace. It is not Raft
  consensus, not a replacement orchestrator, and not an enrolled Station service.

## Proposed bounded configuration for a new profile

This is a reviewable example, **not an instruction to overwrite an existing
profile**. The release's compiler/configuration and native readback determine
what is actually installed. Account/model selection is deliberately absent.
The root agent remains responsible for the whole result, including child work.

```yaml
agent:
  max_turns: 64
delegation:
  max_concurrent_children: 3
  max_spawn_depth: 2
  max_iterations: 50
  orchestrator_enabled: true
  subagent_auto_approve: false
goals:
  max_turns: 20
display:
  busy_input_mode: steer
tools:
  tool_search:
    enabled: "on"
    threshold_pct: 5
    listing: auto
    listing_max_tokens: 4000
    search_default_limit: 5
    max_search_limit: 25
kanban:
  dispatch_in_gateway: false
  auto_decompose: false
  review_dispatch: false
  dispatch_interval_seconds: 60
  max_in_progress: 3
  max_in_progress_per_profile: 1
checkpoints:
  enabled: false
browser:
  use_real_profile: false
platforms:
  api_server:
    enabled: false
```

The principal runtime limit is `agent.max_turns`, not `agent.max_iterations`.
Child and goal budgets are different counters; none is a global mission token,
money or wall-clock cap. `agent.run_budget_seconds` is an optional per-run timing
control, not a substitute for acceptance or provider billing limits.
`auxiliary.goal_judge.provider/model` can select an approved judge route; leaving
them unset inherits native resolution rather than inventing an affordable model.
[Agent defaults][agent-defaults], [delegation defaults][delegation-defaults],
[goal/auxiliary defaults][defaults], [Kanban defaults][kanban-defaults].

The inactive Kanban settings above are for **pre-enrollment staging**. A selected
Director may explicitly enable dispatch, decomposition and review after its
board, assignees, workspace ownership, concurrency and recovery have been
accepted. They are not a reason to stop an already approved dispatcher. Never
run competing dispatchers on the same board. Enable checkpoints per reviewed
coding workspace if desired; verify that they actually cover the relevant files.
Quote `"on"` in YAML so it remains a string rather than a YAML boolean.

## Integration and acceptance checklist

1. Resolve package, Zone, instance, canonical role and native profile from the
   catalog and trusted instance record. A catalog entry is not membership or an
   installed instance; a role name is not necessarily a package ID.
2. Compile the shared orchestration skill and reviewed native defaults into
   new distributions. Preserve existing provider/account configuration; existing
   instances need an explicit reviewed update and readback, not silent adoption.
3. Prove configuration with the native consumer, not just YAML parsing. Test
   independent child results, goal pause/stop, bounded concurrency and a failed
   deterministic gate. Keep synthetic tests account-free where possible.
4. Deliver wiki recipes and scoped knowledge paths. Do not copy a vault, memory
   or credential store from another Zone to make a demonstration work.
5. Audit ACP and native browser dependencies separately from source/Chromium
   presence. API, Raft, external MCP, paid models and schedules remain separate
   enrollment/authorization/readback gates.
6. Record prepared, observed, verified, read_back and accepted accurately. Keep
   unresolved capabilities below OPERATIONAL, with the next repair action.

Station implementation references: `src/agentik_station/os_runtime.py`
(`_profile_config`, `_profile_distribution`), `os_lifecycle.py`,
`os_instances.py`, `hermes_platforms.py`, `config/hermes/voice.default.yaml`,
`resources/chatbotx/hermes-mcp.example.yaml`, and
`installer/npm/runtime.mjs`. Policy references: `AGENTS.md`,
`rules/STATION_AGENT_RULES.md` and `docs/hermes/02_NATIVE_MAPPING.md`.

[setup]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/setup.py#L3070
[memory]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/memory.md
[memory-tool]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/tools/memory_tool.py#L897
[commands]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/commands.py#L200
[cli]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/cli.md#L361
[skills]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/skills.md
[mcp]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/mcp.md#L54
[tool-search]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/tool-search.md#L90
[delegation-defaults]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/config_defaults.py#L2086
[delegate-source]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/tools/delegate_tool.py#L903
[goals]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/goals.md
[cron]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/cron.md
[checkpoints]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/checkpoints-and-rollback.md#L88
[profiles]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/profiles.md#L130
[wiki]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/skills/research/llm-wiki/SKILL.md
[obsidian]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/skills/note-taking/obsidian/SKILL.md
[kanban]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/kanban.md#L55
[voice]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/voice-mode.md
[browser]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/browser.md
[api]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/api-server.md#L608
[api-config]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/gateway/config.py#L2299
[acp-parser]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/subcommands/acp.py
[acp]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/features/acp.md
[pyproject]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/pyproject.toml#L283
[distributions]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/profile-distributions.md
[raft]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/website/docs/user-guide/messaging/raft.md
[agent-defaults]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/config_defaults.py#L45
[defaults]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/config_defaults.py
[kanban-defaults]: https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/hermes_cli/config_defaults.py#L2818
