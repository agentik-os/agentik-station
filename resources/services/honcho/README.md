# Honcho server software bundle

`../honcho.json` installs the released server image used for both API and
deriver processes, plus PostgreSQL/pgvector and Redis images. The SDK-only
operator environment remains a different artifact. No container is created,
started or migrated; software evidence is not runtime or account acceptance.

## Primary provenance

- [Released server source](https://github.com/plastic-labs/honcho/tree/5d992bc65afcfbc05a5911ab4edbaa88ef64c690)
  is the revision declared by the official `ghcr.io/plastic-labs/honcho:v3.1.1`
  image. It differs from the newer `HONCHO_COMMIT` source-review pin; this
  bundle deliberately records the image's actual release provenance.
- [Exact release Compose](https://github.com/plastic-labs/honcho/blob/5d992bc65afcfbc05a5911ab4edbaa88ef64c690/docker-compose.yml.example)
  supplies the API, separate deriver, pgvector PostgreSQL and Redis topology.
- [Official image workflow](https://github.com/plastic-labs/honcho/blob/5d992bc65afcfbc05a5911ab4edbaa88ef64c690/.github/workflows/docker-build.yml)
  publishes Linux AMD64/ARM64 application images to the upstream GHCR namespace.
- [Native Hermes integration](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/plugins/memory/honcho/README.md)
  documents profile configuration, workspace/peer identity and automatic writes.

Public registry metadata was inspected on 2026-09-05; no image was executed.
Linux AMD64 manifest bytes were verified against their SHA256, followed by
configuration architecture and application revision/version readback. Reviewed
tag inputs were `v3.1.1`, `pgvector/pgvector:pg15`, and `redis:8.2`; the JSON
pins only the selected platform digests. PostgreSQL and Redis version fields
come from their image configuration metadata. No optional LanceDB or monitoring
demo is selected. Both API and deriver use the single installed server image.

## Separate runtime gate

Do not start the example Compose unchanged: its PostgreSQL trust authentication,
example passwords and unauthenticated defaults are inappropriate for a shared
Station Host. Select a Zone/principal, private authenticated endpoint, dedicated
database/cache/state, migration and backup policy, then explicit LLM/embedding
routes and provider credentials. Loopback alone is not cross-Zone authorization.

Install and compatibility-test the provider SDK in the actual immutable Hermes
runtime; its `all` extra excludes Honcho. Hermes permits only one external
memory provider per profile. Explicitly select endpoint, workspace and peer
identities; avoid shared defaults or collapsed gateway-user identities.
`HERMES_HOME` fallback configuration and Zone `HOME` are not independent account
boundaries. Test authenticated synthetic write, deriver completion, recall after
restart and unauthorized cross-Zone denial before operational acceptance.
