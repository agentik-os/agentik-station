# Hindsight server software bundle

`../hindsight.json` installs the full `0.9.2` server image and an external
PostgreSQL/pgvector image. This is not the `hindsight-client` SDK-only recipe.
No container, database, schema, credential, bank or listener is created.

## Primary provenance

- [Release source](https://github.com/vectorize-io/hindsight/tree/ebad478240d3171bb88201ececda5e8d9883d22d)
  matches the official `ghcr.io/vectorize-io/hindsight:0.9.2` revision label.
- [Release README](https://github.com/vectorize-io/hindsight/blob/v0.9.2/README.md)
  distinguishes actual server, embedded runtime and client installations.
- [Official installation guide](https://hindsight.vectorize.io/developer/installation)
  distinguishes the full/slim images, external LLM requirements, PostgreSQL
  with vector extensions, embedded development database, supported image UID
  and stable worker identity.
- [Native Hermes integration](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/plugins/memory/hindsight/README.md)
  documents cloud, local-embedded and local-external modes.

Public registry metadata was inspected on 2026-09-05, not executed. The selected
Linux AMD64 platform manifest bytes were SHA256-checked and their configuration
architecture read back. The server's version/revision labels identify `0.9.2`
and the source above. The external database is the reviewed `pgvector:pg15`
image (PostgreSQL `15.19-1.pgdg12+2`); its exact bytes are pinned in JSON.
That database satisfies the documented PostgreSQL 14+ prerequisite, but its
extension/migration/API compatibility still requires native runtime acceptance.

## Separate runtime gate

For a VPS, select private external PostgreSQL rather than treating development
pg0 as a production deployment. The full image includes local embedding/reranker
runtime but does not replace the extraction/reflection LLM: provide a separately
deployed local inference service or explicitly enrolled provider. Assign an
owning Zone/principal, authentication, storage, backups, stable worker identity
and resource limits. Respect the image's supported UID through reviewed user
namespace/storage mapping; do not blindly change its container UID.

Use separate scoped services or reviewed tenant authentication; bank names and
a shared API key are not hard isolation. Explicitly bind the native Hermes
provider to endpoint and bank. Its `all` extra excludes Hindsight; an unrelated
operator venv does not satisfy native imports. Do not rely on setup's unpinned
`hindsight-all` lazy install. Embedded development additionally needs unique
profile names because Zone `HOME/.hindsight` can be shared across HERMES_HOME
roots. Require synthetic retain completion, recall/reflect, restart persistence
and unauthorized access denial before operational acceptance.
