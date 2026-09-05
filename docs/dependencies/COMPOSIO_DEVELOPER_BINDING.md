# Composio Discord: installed CLI, missing developer binding

Station installs Composio CLI **0.4.0** as public, root-owned software. This does
not enroll a Composio account or configure the Discord adapter. The Station
`provider composio-discord plan` command returns non-executable templates with
`CONFIGURATION_REQUIRED`; `link` and `verify` refuse before any native command or
account call. Hermes remains the messaging gateway and execution orchestrator.

The public executable is `/usr/local/bin/composio`, pointing to
`/opt/station/tools/composio/0.4.0/composio`. The Zone must not execute the
operator-private launcher or inherit another identity's credentials. Native
manual enrollment remains an explicitly authorized task under the owning Zone
identity; this document is not an unscoped execution recipe.

## Why the previous facade is blocked

The reviewed release is
[`@composio/cli@0.4.0`](https://github.com/ComposioHQ/composio/releases/tag/%40composio/cli%400.4.0),
at commit `1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28`. Its
[root command registration](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/commands/index.ts)
does not expose root `connected-accounts`; that group is under
[`dev`](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/commands/dev.cmd.ts).

Adding `dev` alone is insufficient. The
[link implementation](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/commands/connected-accounts/commands/connected-accounts.link.cmd.ts)
uses consumer project resolution unless a developer project name is supplied.
For a consumer project it selects the consumer identity, not the requested
developer `--user-id`. Root `link` is also consumer-only and cannot substitute
for a Zone-bound developer flow.

Account
[listing](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/commands/connected-accounts/commands/connected-accounts.list.cmd.ts)
requires explicit `--user-id` filtering and resolves a developer project from
the local working-directory context. The
[project resolver](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/services/command-project.ts)
must therefore resolve the same project selected for linking. An inherited
caller directory is not a trusted Zone binding.

The tool-catalog grammar is `composio tools list discord`: the toolkit is a
[positional argument](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/commands/tools/commands/tools.list.cmd.ts),
not `--toolkit`. Catalog output is not an account or successful-tool readback.

## Required before a future executable adapter

- Explicit owning Host/Zone/principal and authorized operator.
- Reviewed Composio organization and exact developer project selection; no
  consumer fallback or guessed project name.
- A validated Zone-owned working directory whose native project context matches
  that selection. This need not invent or silently register a Station Project.
- Separate native login and developer-mode enrollment, without copying keys,
  configuration or cookies from another principal. Developer mode defaults on
  in the pinned [configuration schema](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/models/cli-user-config.ts),
  but its current state must not be assumed.
- Matching ACTIVE connected-account evidence for the intended user/project and
  an allowed read-only Discord tool result, followed by human acceptance.

Station has no trusted contract for the external developer-project/workdir
binding yet. The user must choose that scope before an adapter can safely use
it. Station does not run native project initialization automatically: upstream
[`dev init`](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/commands/init.cmd.ts)
can create a project API key and write project configuration and `.env.local`.

Finally, a zero CLI exit is not proof of login or an ACTIVE account. The pinned
[authentication guard](https://github.com/ComposioHQ/composio/blob/1bf17e13a2e02fd435b1ef590c2c42af9a7d9e28/ts/packages/cli/src/effects/require-auth.ts)
can return without performing the requested operation when login is absent.
The blocked Station facade neither emits raw account/credential output nor
labels an unconfigured adapter `DEGRADED` or `OPERATIONAL`.
