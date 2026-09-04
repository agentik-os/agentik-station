# Hermes Updates, Backups and Rollback

## Never blind-update production

Do not run:

```text
pull latest → restart everything
```

without compatibility verification.

## Release channels

```text
edge
candidate
stable
```

Suggested:
- lab = edge
- Operator = candidate
- clients = stable

## Pipeline

```text
Hermes upstream release
→ detect
→ compatibility CI
→ canary Agentik Node
→ Hermes doctor
→ security audit
→ plugin checks
→ integration checks
→ E2E mission
→ approve
→ update lockfile
→ candidate
→ stable
```

## Node rollback

Uses:
- previous image/version
- previous `agentik.lock`
- state backup

## Project rollback

Uses Hermes checkpoints / project recovery.

These are separate problems.

## Backup rule

Backups must live outside the VPS.

Back up:
- Hermes state
- memory
- databases
- evidence
- artifacts
- deployment config
- important uploads

Secrets should be recoverable from a secret manager, not from Git.
