# ChatbotX client for Hermes

Station's default Host and personal Workstation installation includes the
reviewed `chatbotx@0.1.3` CLI. Hermes remains the execution orchestrator and the
Station messaging gateway. It can invoke the native CLI through its scoped
`PATH` after an explicit account connection. ChatbotX supplies a separate
marketing workspace; installing its client does not deploy that application,
connect an account, start another gateway, or send a message.

## Installed software and readiness

The authoritative package pin and integrity are in [RESOURCE.json](RESOURCE.json)
and Station's version lock. The CLI's published `dist/index.cjs` has no shebang,
so Station's launcher invokes it with the managed Node runtime. Installation
disables package lifecycle scripts. Do not replace this with an unpinned `npx`
invocation or a global package installation.
Workstation also installs the pinned Hermes `mcp` Python extra, and both
installers require the native MCP SDK to import successfully. This is client
software only in Workstation mode: it does not install a local MCP server or
enable the remote connection. The **full Linux AMD64 Host** additionally installs
the [complete nine-image application/MCP bundle](../services/chatbotx/README.md).
Its containers are not started automatically; private deployment and account
acceptance remain separate. `station deps service-check --component chatbotx`
verifies those image bytes and their bound receipt, not application health.

| Installation | CLI package location |
| --- | --- |
| Personal Workstation | `<workstation>/station/resources/cli/node_modules/chatbotx` |
| Host operator | `<operator-home>/.local/share/station-clis/chatbotx/node_modules/chatbotx` |
| Host shared code | `/opt/station/tools/toolchain/<pin-set>/npm/chatbotx` |

The Workstation launcher is `<workstation>/station/bin/chatbotx`. Workstation
configuration belongs in its private `station/personal/home` context. Shared
Host code is immutable; configuration, credentials, cache and evidence belong
to the owning Zone identity and declared Project or OS instance.

The resource declaration remains `NOT_INSTALLED` until installer evidence proves
the native package and support files. A successful clean-home `--version` and
`--help` probe establishes client capability only. Account/MCP and full
application readiness remain `NOT_CONFIGURED`. The upstream CLI reports
`0.1.3` without configuration, but its configured branch fetches the API schema
and reports a hardcoded `0.1.0`; acceptance probes therefore use a private clean
home and cleared credential environment.

## Enroll one owning profile

1. Resolve the Host or enrolled personal Workstation, Zone where applicable,
   selected Hermes profile, principal, ChatbotX workspace and environment.
   Use the native profile tooling to locate that profile's private configuration
   and credential environment. Development must not inherit production access.
2. In that workspace's ChatbotX settings, obtain a Workspace API token under
   **Settings → Developer → API Keys**. Enroll it through the owning profile's
   private credential editor or narrow credential service. Use `umask 077`,
   directory mode `0700`, and file mode `0600`; verify existing file modes as
   well as new ones. For Host CLI use and the optional Hermes MCP connection,
   the private environment names are `CHATBOTX_API_KEY` and
   `CHATBOTX_API_URL`; enter the actual token only in the private editor or
   credential service. The Workstation CLI launcher clears the ambient
   environment, so inherited ChatbotX variables do not configure that launcher.
   Instead, explicitly enroll the Workstation CLI through a private editor in
   `<workstation>/station/personal/home/.chatbotX/config.json`, using the native
   `apiKey` and `apiUrl` fields described below. The documented cloud API URL is
   `https://app.chatbotx.io/api`. A self-hosted connection uses its reviewed
   instance API URL, including `/api`.
3. Scope delivery to the selected profile/process or private Workstation file.
   Never put the
   token in command arguments, native `config set` flags, chat, shell history,
   repository files, shared code, logs or evidence. Do not copy credentials
   from an existing personal account or another Zone/profile.
4. Confirm the chosen API/schema origin and workspace identity with an
   explicitly authorized read-only operation. Record sanitized account/scope
   evidence. Message sending, contact changes, flows and other mutations need
   their own policy authorization and external readback.

The native CLI has no interactive masked setup prompt. Its `config set` command
accepts flags and writes plaintext JSON to
`<process-home>/.chatbotX/config.json`. The schema is `apiKey: string`,
`apiUrl: string`, and optional `allowSelfSignedCert: boolean`. Writes are not
atomic and do not set explicit private permissions. The success message prints
field names, but token arguments can still enter process listings and history.
Use the explicitly selected private editor or credential service for enrollment;
Station does not implement a new masked setup command. Keep TLS verification
enabled.

CLI configuration resolves flags, then environment, then the stored file. The
cache lives at `<process-home>/.chatbotX/openapi-cache.json`. Both paths follow
Unix `HOME`, not `HERMES_HOME`: separate instance/profile Hermes homes do not
isolate native CLI credentials within the same Zone. Host gateways retain the
canonical Zone home. Use separate Zones when hard account isolation is needed.

## Optional native Hermes remote MCP

[hermes-mcp.example.yaml](hermes-mcp.example.yaml) is a disabled configuration
example, not an installed or connected server. Add it only to the explicitly
selected owning Hermes profile after reviewing the endpoint and credential
scope. Keep it disabled until the profile token, permitted tools and account
readback are accepted. Do not merge it into every profile or shared defaults.
The pinned Hermes implementation treats `tools.include: []` as no registered
server tools. The template also sets `tools.resources`
and `tools.prompts` to `false`: Hermes generates these utility tools separately
from the server-tool include filter. Replace that empty list only with the exact
reviewed names selected from discovery; removing the filter would expose the
server's full tool set. Sampling and elicitation remain disabled.
The template explicitly disables lazy cache registration (`lazy: false`): the
pinned Hermes cached-utility path does not reapply those resource/prompt flags.

ChatbotX expects the custom `x-workspace-token` header. The pinned native
`hermes mcp add` header-auth wizard only constructs Bearer authorization, so
do not use that wizard blindly for this integration. The example uses a literal
environment reference; the token itself must stay in the private profile
environment. Never use a token-bearing URL.

The source names `chatbotx-mcp-server@0.1.0`, but that package was not published
on npm at review. Station does not install it or build the monorepo by default.
The optional remote endpoint is `https://app.chatbotx.io/mcp/sse`, or the
equivalent reviewed self-hosted endpoint. If a separately approved local MCP
server is used later, explicitly select `CHATBOTX_MCP_TRANSPORT=stdio` and a
private working directory: upstream otherwise starts both stdio and an HTTP
listener at `0.0.0.0:3333` and loads `.env` from its working directory.

Both native clients fetch `${CHATBOTX_API_URL}/public-spec.json` without a token,
then trust its first `servers[].url` for API calls. A compromised or unexpected
schema can change request targets; validate origin, redirects and server URLs
before delivering credentials. Commands/tools change with the schema. Live
operation IDs can include `WorkspaceTokenAPI` suffixes, so select tools from
actual discovery instead of copying abbreviated names from documentation.
The upstream MCP tools lack read-only/destructive annotations and include
message sending and workspace mutations. A filter or prompt is not a complete
authorization boundary for an unrestricted shell or API token.

## Full application deployment is separate

The official deployment input is
[ChatbotXIO/chatbotx-docker-compose](https://github.com/ChatbotXIO/chatbotx-docker-compose).
The main repository's compose files provide development infrastructure and
expect applications to run from source. Neither is started by this resource.

A self-hosting decision must review pinned image digests and architecture,
ports/egress, generated private secrets, persistent storage, migrations,
backups and recovery. The reviewed standalone compose uses mutable `latest`
application images, AMD64 application platforms, public example credentials,
published service ports and automatic migrations/seeding. It does not declare
an MCP service despite the broader documentation describing MCP alongside an
instance. Those defaults are not accepted as a Station deployment. Do not run
the upstream upgrade script: it includes a host-wide `docker system prune -f`.

## Provenance and license

Reviewed source commit:
[`77bd6b17b23dcfb15a0a7031374bde31ceec9b86`](https://github.com/ChatbotXIO/ChatbotX/tree/77bd6b17b23dcfb15a0a7031374bde31ceec9b86).
The exact [npm package](https://registry.npmjs.org/chatbotx/0.1.3) integrity was
checked against its tarball. That tarball omits its declared LICENSE file;
[LICENSE.upstream](LICENSE.upstream) preserves the exact root notice from the
reviewed source. Code outside `apps/builder/src/enterprise` is MIT under that
notice; enterprise code has a separate Commercial License. The MCP source
manifest declares ISC, a metadata discrepancy recorded in the resource rather
than treated as one uniform application license.

Relevant primary contracts:
[CLI configuration](https://github.com/ChatbotXIO/ChatbotX/blob/77bd6b17b23dcfb15a0a7031374bde31ceec9b86/apps/cli/src/config.ts),
[CLI setup implementation](https://github.com/ChatbotXIO/ChatbotX/blob/77bd6b17b23dcfb15a0a7031374bde31ceec9b86/apps/cli/src/commands/config.ts),
[MCP handlers](https://github.com/ChatbotXIO/ChatbotX/blob/77bd6b17b23dcfb15a0a7031374bde31ceec9b86/apps/mcp-server/src/server/create-mcp-server.ts),
[official MCP documentation](https://chatbotx.io/docs/mcp/introduction),
[pinned Hermes MCP configuration](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/tools/mcp_tool.py).
