# ChatbotX complete server software

[The service manifest](../chatbotx.json) installs the actual prebuilt ChatbotX
application, background workers, realtime server, isolated JavaScript executor,
MCP server, database, queue/cache and object-storage software. It is separate
from the [native CLI resource](../../chatbotx/README.md). Hermes remains Station's
orchestrator; ChatbotX is a domain application under that orchestration.

## Software installation is not activation

The Host service installer must pull every manifest reference and read back its
exact digest and `linux/amd64` platform before recording software installation.
A checkout, this manifest, or a successful CLI `--version` is insufficient.
Images can be installed without running their code: this bundle authorizes no
container creation/startup, service account, public listener, database migration,
seed, storage policy change, credential enrollment or MCP connection. Runtime
configuration and account acceptance remain pending after a successful pull.

The nine required images are:

| Software | Reviewed version | Purpose |
| --- | --- | --- |
| ChatbotX builder | 1.5.0 | Web application and API |
| ChatbotX worker | 1.5.0 | Background processing |
| ChatbotX realtime | 1.5.0 | Realtime application transport |
| ChatbotX JavaScript executor | 1.5.0 | Isolated user-authored flow execution |
| ChatbotX MCP | 1.5.0 | Native application MCP server |
| TimescaleDB HA | pg18.4-ts2.27.2-all | PostgreSQL database with upstream extensions |
| Redis | 8.8.0-alpine | Queue and cache |
| RustFS | 1.0.0-beta.8 | S3-compatible object storage |
| RustFS rc | v0.1.22 | Separately authorized storage initialization tool |

The JSON contains platform-manifest digests, not mutable version tags or only
multi-platform index digests. Registry manifest bytes were SHA-256 checked and
their image configurations read on 2026-09-05. All five application image labels
identify version `1.5.0` and source commit
[`526ea40fd81b20d7f2e754810d16a4d9a36d9a0c`](https://github.com/ChatbotXIO/ChatbotX/tree/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c).
The application images are AMD64-only at this review. Do not silently substitute
ARM emulation or claim native ARM64 support.

The nine images total approximately 3.61 GB of compressed layers before shared
layer deduplication; unpacking, writable state, backups and other Station
services need additional space. TimescaleDB alone accounts for approximately
2.58 GB compressed. The official installation guide calls for Docker 24+,
Compose 2.20+, 4 GB RAM and 4 vCPU; the standalone repository states a lower
baseline. Use the stronger published baseline and assess the combined Host
workload before activation. The worker launches multiple Node processes; the
image count is not a process or memory budget.

## Deployment inputs and exclusions

The reviewed full-app topology is the
[standalone compose at `1b71fc4`](https://github.com/ChatbotXIO/chatbotx-docker-compose/blob/1b71fc4fe9e21cebbf868e1f1474e8d99a7ca27e/docker-compose.yml),
not the main monorepo's development-infrastructure compose. The standalone file
does not define MCP, so the separately published MCP image is included here.
Its published ports, example secrets, mutable application tags and automatic
migration/seeding are not accepted Station defaults. No runnable deployment
template is shipped while the following activation gates remain unresolved.

Adminer `5.4.2` and MailHog `v1.0.1` are optional maintenance/demo tools in that
upstream topology, not application runtime requirements or installed claims in
this manifest. MailHog is not an accepted production mail provider. If a bounded
maintenance/demo mission needs them, its separately reviewed AMD64 pins are:

- `docker.io/library/adminer@sha256:594b9c6d80cce82bff8b75109bac402a662cc6723a742d09878935663907e2d0`
- `docker.io/mailhog/mailhog@sha256:8d76a3d4ffa32a3661311944007a415332c4bb855657f4f6c57996405c009bea`

Never run the upstream `upgrade.sh`; it performs host-wide Docker pruning.
Do not rebuild from the source commit as an interchangeable fallback: upstream
Dockerfiles contain mutable base/tool inputs and some non-frozen installation
steps. A derived or ARM64 build needs its own reviewed pins and native tests.

## Activation gates

1. **Ownership and isolation.** Resolve Host, owning Zone, environment, Project
   or OS instance, principal and community/licensed edition. Persist state,
   credentials, logs and backups beneath that Zone's canonical Station roots;
   declare storage ownership and mount mapping explicitly. Shared immutable
   images are not permission to share a database or credentials between Zones.
   Do not grant a gateway/operator broad Docker access to run this application.

2. **Secrets and initial administrator.** Use a private credential service or
   editor with `umask 077`, directories `0700` and files `0600`. Generate unique
   database and S3 credentials, `BETTER_AUTH_SECRET` (at least 32 characters),
   `ENCRYPTION_KEY` (exactly 64 hexadecimal characters),
   `REALTIME_BROADCAST_SECRET` (at least 32 characters) and
   `JAVASCRIPT_EXECUTOR_TOKEN` (at least 32 characters). Keep the encryption key
   stable and recoverable; rotation is a separate migration. No secrets in
   argv, manifests, evidence or shared environment files. Set any
   `PLATFORM_ADMIN_EMAIL` only to the explicitly enrolled owner. SMTP, provider
   accounts and marketing channels require that owner's separate enrollment.

3. **Database lifecycle.** Keep `RUN_DB_MIGRATE=false` and `RUN_DB_SEED=false`
   for normal startup. The builder supports a distinct one-shot `migrate`
   command; approve it only against the resolved database with schema-version
   evidence and an accepted backup/restore plan. The upstream seed creates
   `demo@example.com` with a publicly known password and verified administrator
   access on an empty database. Never seed a production instance. Do not use a
   migration or reinstall to overwrite existing state.

4. **Configuration and network correctness.** The following names come from
   the pinned application schema, not older documentation. Internal examples
   assume separately approved services named `filesystem`, `realtime`, `redis`
   and `postgres`; they do not authorize network creation.

   | Setting | Required decision/correction |
   | --- | --- |
   | `S3_ENDPOINT` | Use the internal object-storage URL, for example `http://filesystem:9000`; upstream compose misspells this as `S3_ENPOINT`. |
   | `S3_BUCKET`, `S3_REGION` | Explicit storage namespace and matching provider region. |
   | `NEXT_PUBLIC_BUILDER_URL`, `BETTER_AUTH_URL` | Matching accepted application origin behind TLS. |
   | `NEXT_PUBLIC_INTERNAL_WS_URL` | For this topology, `http://realtime:1999`, not container-localhost. |
   | `NEXT_PUBLIC_INTERNAL_STORAGE_URL` | For this topology, `http://filesystem:9000/chatbotx/`, not container-localhost. |
   | `NEXT_PUBLIC_STORAGE_URL` | Separately reviewed external asset origin if used. |
   | `DATABASE_URL`, `REDIS_URL` | Dedicated internal service endpoints and scoped credentials. |
   | `SMTP_SERVER`, `SMTP_FROM` | Actual approved SMTP service and sender; localhost is not a different container. |
   | `JAVASCRIPT_EXECUTOR_URL` | Private executor address reachable only by the worker. |
   | `EXPO_PUSH_ENABLED` | Set `false` until push behavior and its account are explicitly accepted; worker source defaults to true. |
   | `NEXT_PUBLIC_EDITION` | `community` unless a valid, scoped enterprise entitlement has been verified. |

   Keep database, Redis, storage console, executor and MCP private. Public web,
   realtime and any asset routing require separately reviewed TLS, authentication,
   firewall and webhook rules. Do not copy upstream `host.docker.internal`
   access or broad CORS without a documented need. Object-storage initialization
   is a data/policy mutation: upstream grants anonymous access to a public
   prefix and passes storage credentials to its CLI. Neither is automatically
   authorized by installing the `rc` executable.

5. **Realtime startup and executor containment.** The pinned realtime entrypoint
   runs unpinned `pnpm dlx partykit dev`. Before activation, inspect the pulled
   image and verify an offline invocation of its already installed
   `partykit@0.0.115` (the source package pins it). A candidate is the bundled
   Node entry `apps/realtime/node_modules/partykit/dist/bin.mjs` with the realtime
   working directory, but its presence and native behavior must be verified;
   it is not an accepted executable recipe yet. Do not download packages at
   startup or write secrets into the image.
   Preserve the executor's dedicated `internal: true` network joined only by
   worker and executor, no published port, dropped capabilities,
   `no-new-privileges`, read-only root, 16 MiB `noexec,nosuid,nodev` temporary
   mount, 128-process limit, 2 CPU/512 MiB limits and explicit concurrency 2.
   Several other upstream images default to root; assess each UID, writable
   path and healthcheck natively before applying runtime restrictions. Do not
   assume a `curl` binary exists merely because a compose healthcheck uses it.

6. **Hermes/MCP and external readback.** Pulling the MCP image installs server
   software, not its listener or a Hermes connection. Use an explicitly scoped
   private API/schema origin and transport; upstream defaults to both stdio
   and SSE and loads `.env` from its working directory. The separately shipped
   [disabled Hermes template](../../chatbotx/hermes-mcp.example.yaml) keeps
   connection, sampling, elicitation, lazy cache and all tool classes disabled.
   The pinned Hermes environment must have its actual `mcp` SDK extra installed.
   ChatbotX uses `x-workspace-token`; the pinned Hermes header-auth wizard's
   Bearer-only shortcut is not the correct enrollment path. Review schema
   `servers` URLs before providing credentials. Tools include mutations and
   lack safety annotations; exact allowlists and policy remain necessary.
   Confirm the chosen workspace/account with authorized read-only evidence
   before any contact write, flow activation or message sending. Keep Station's
   administration bots separate from application marketing channels.

## License and source evidence

Preserve the original notices in every pulled upstream image; do not relabel the
bundle as uniformly MIT or redistribute a modified enterprise build. The
[release root license](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/LICENSE)
is byte-identical to Station's retained
[upstream notice](../../chatbotx/LICENSE.upstream), checked on 2026-09-05. It
separates MIT code, `apps/builder/src/enterprise` under a
[Commercial License](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/builder/src/enterprise/LICENSE),
and third-party components under their own licenses. Database, Redis, RustFS
and their bundled dependencies retain their own terms. The MCP package manifest
declares ISC; this is a recorded metadata discrepancy, not permission to discard
the root notice. Pulling an official image is not enterprise entitlement.

The official edition guide describes community as a single workspace; enterprise
features and multiple workspaces require the applicable license. Resolve
separate community instances per owning Zone or a properly licensed deployment;
an edition environment variable does not grant rights or client isolation.

Primary evidence, reviewed against the immutable application source above:

- [Release v1.5.0](https://github.com/ChatbotXIO/ChatbotX/releases/tag/v1.5.0)
  and [official container packages](https://github.com/orgs/ChatbotXIO/packages).
- [Installation requirements](https://chatbotx.io/docs/installation/docker-compose)
  and [edition guide](https://chatbotx.io/docs/super-admin/enterprise-edition).
- [Builder configuration](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/builder/src/env.ts),
  [storage configuration](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/packages/filesystem/src/keys.ts)
  and [encryption requirements](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/packages/encryption/src/keys.ts).
- [Migration/seed entrypoint](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/builder/docker/rootfs/usr/local/bin/docker-entrypoint.sh)
  and [seed behavior](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/packages/database/src/seed/index.ts).
- [Realtime entrypoint](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/realtime/docker/rootfs/usr/local/bin/docker-entrypoint.sh)
  and [pinned realtime dependency](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/realtime/package.json).
- [MCP startup](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/mcp-server/src/index.ts)
  and [worker configuration](https://github.com/ChatbotXIO/ChatbotX/blob/526ea40fd81b20d7f2e754810d16a4d9a36d9a0c/apps/worker/src/env.ts).
