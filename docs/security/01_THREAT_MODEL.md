# Threat Model

## Main threats

### Cross-client credential leakage
Mitigation:
- isolated Zones for all clients; dedicated remote Hosts for production or stronger isolation when policy requires
- profile-scoped credentials
- capability resolver
- no global secret pool

### Cross-client memory leakage
Mitigation:
- namespaced provider
- separate profiles
- separate Nodes where appropriate
- memory candidates / approval

### Wrong repository execution
Mitigation:
- Hermes Project
- Board binding
- AGENTS.md
- context resolver
- deny unresolved context

### Wrong production deployment
Mitigation:
- production capability
- separate deployment credential
- approval
- post-deploy verification

### Agent self-approval
Mitigation:
- independent review role
- review lifecycle
- deterministic gates

### Agent modifies critical files destructively
Mitigation:
- worktrees
- checkpoints
- rollback
- Git

### Public dashboard exposure
Mitigation:
- localhost/private bind
- Tailscale/reverse proxy/auth if needed

### Malicious or unsafe plugin
Mitigation:
- pin commits
- review plugins
- compatibility CI
- minimal plugin set

### Supply-chain drift
Mitigation:
- `agentik.lock`
- immutable image digests / SHAs
- update channels

### VPS loss
Mitigation:
- reproducible infrastructure
- offsite backup
- DR test

### Permanent Discord Administrator
Mitigation:
- bootstrap-only Administrator window
- automatic demotion after verify
- doctor fails if runtime Administrator retained
- least-privilege runtime role

### Discord role hierarchy mistake
Mitigation:
- preflight hierarchy check
- never attempt to manage roles at/above bot's highest role
- verify final hierarchy after provisioning

### Destructive reconciliation
Mitigation:
- plan/diff before apply
- adopt-and-extend default
- no delete/rename unmanaged resources
- explicit migration policy + approval for destructive operations

### Channel-name routing spoof / accidental rename
Mitigation:
- immutable Discord ID binding registry
- names only for display/bootstrap matching
- deny sensitive action on ambiguous bindings

### Privileged Bootstrap Director misuse
Mitigation:
- typed Discord capabilities, not generic root
- maintenance window
- evidence for every mutation
- apply capability disabled outside bootstrap/reconcile window
