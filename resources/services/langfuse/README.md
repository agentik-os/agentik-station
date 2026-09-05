# Langfuse server software bundle

`../langfuse.json` replaces a source-only installation claim with six concrete
OCI image requirements. The software installer pulls and inspects those images
in local root Podman; it never executes them. `SOFTWARE_INSTALLED` remains
`configuration_required: true`, `operational: false`.

## Primary provenance

- [Langfuse v4.28.1 Compose](https://github.com/langfuse/langfuse/blob/v4.28.1/docker-compose.yml)
  defines web, worker, PostgreSQL, ClickHouse, Redis and MinIO dependencies.
- [Release source](https://github.com/langfuse/langfuse/tree/70cff8078545a7cac01fea1462cd6d077d8dfa3e)
  matches both application images' OCI revision labels and version `4.28.1`.
- [Official deployment guide](https://langfuse.com/self-hosting/deployment/docker-compose)
  documents the complete service topology, secrets and capacity considerations.
- [Native Hermes integration at the Station pin](https://github.com/NousResearch/hermes-agent/blob/29112bef099274229cadff79cdff7bf7b99c4b77/plugins/observability/langfuse/README.md)
  is opt-in, requires its runtime SDK and project credentials, and fails open
  without those dependencies. A plugin listing alone is not trace acceptance.

Public registry metadata was read on 2026-09-05 without pulling or executing
images. The selected Linux AMD64 platform manifest bytes were SHA256-checked
against their digest, then their image configurations were inspected. Selected
upstream tags: `4.28.1` for web/worker; `postgres:17`; `redis:7`;
`clickhouse/clickhouse-server:25.12`; `cgr.dev/chainguard/minio:latest`.
The manifest records immutable platform digests, never those mutable tags.
PostgreSQL/Redis version strings come from image environment metadata,
ClickHouse from its build-version label. MinIO has no semantic-version label;
the recorded timestamp is explicitly its image creation timestamp.

## Separate runtime gate

Do not apply upstream Compose directly: its public ports, example credentials,
mutable references and service entrypoints need a reviewed deployment adapted
to Station. Choose a Zone/principal, private networking, secrets, durable state,
backup policy and UI access route. No user, organization, API key, schema or
migration is created by this bundle. Do not use arbitrary named volumes.

Install a pinned compatible Langfuse SDK into the actual Hermes runtime and
explicitly enable `observability/langfuse` in the owning profile. Use separate
project credentials per scope. Prefer `HERMES_LANGFUSE_CAPTURE=metadata` until
content export is authorized. Acceptance requires a synthetic Hermes trace
visible in the intended project after flush and negative cross-Zone access
checks, not merely healthy containers.
