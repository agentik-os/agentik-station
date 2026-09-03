# Complete System Checklist

Use this as the final "did we forget something?" list.

## Foundation
- [ ] clean Ubuntu LTS
- [ ] non-root admin
- [ ] SSH keys
- [ ] Tailscale
- [ ] firewall
- [ ] fail2ban
- [ ] Docker
- [ ] filesystem conventions

## Hermes
- [ ] persistent volume
- [ ] provider
- [ ] gateway
- [ ] multiplex profiles
- [ ] dashboard private
- [ ] profiles
- [ ] Projects
- [ ] Boards
- [ ] Goals
- [ ] deterministic gates
- [ ] review loop
- [ ] delegation
- [ ] recursive delegation limits
- [ ] worktree isolation
- [ ] context files
- [ ] skills
- [ ] bundles
- [ ] skill governance
- [ ] plugins
- [ ] hooks
- [ ] MCP
- [ ] cron
- [ ] webhooks
- [ ] checkpoints
- [ ] rollback
- [ ] doctor
- [ ] security audit
- [ ] logs
- [ ] backups
- [ ] provider pools / fallbacks
- [ ] model routing

## AGK
- [ ] Organization Registry
- [ ] OS Registry
- [ ] Context resolution / binding registry
- [ ] Capability Registry
- [ ] Credential policy
- [ ] Memory namespaces
- [ ] Evidence model
- [ ] Mission IDs
- [ ] event model
- [ ] approvals
- [ ] sync logic

## Organization
- [ ] custom Macro Domains
- [ ] custom Domains
- [ ] OS assignment
- [ ] Nano Directors
- [ ] NanoTeams
- [ ] project mapping
- [ ] Discord mapping

## Integrations
- [ ] GitHub
- [ ] Linear
- [ ] Notion
- [ ] DB
- [ ] optional Composio
- [ ] optional Parakeet
- [ ] optional VoiceStudio
- [ ] Ponytail when DevOps/Builder/Engineering OS is installed

## Security
- [ ] no global client secret pool
- [ ] org isolation tested
- [ ] memory isolation tested
- [ ] repo isolation tested
- [ ] board isolation tested
- [ ] production capability separated
- [ ] private dashboard
- [ ] plugin versions pinned
- [ ] update rollback tested

## Distribution
- [ ] Agentik Node repo
- [ ] Profile Distributions
- [ ] Skill registry
- [ ] OS manifests
- [ ] deployment config repo
- [ ] agentik.lock
- [ ] installer
- [ ] doctor
- [ ] update channels
- [ ] compatibility CI

## Recovery
- [ ] state backup
- [ ] offsite backup
- [ ] secret recovery
- [ ] clean VPS restore tested

## Acceptance
- [ ] Discord → Mission
- [ ] Context resolved
- [ ] Correct OS
- [ ] Correct Project
- [ ] Correct Board
- [ ] NanoTeam spawned
- [ ] Worktree isolated
- [ ] Goal gates pass
- [ ] QA
- [ ] Review
- [ ] PR / CI
- [ ] staging
- [ ] live verify
- [ ] production verify
- [ ] evidence
- [ ] Linear
- [ ] Notion
- [ ] memory candidate
- [ ] Discord done

## DevOps / Ponytail
- [ ] Ponytail pinned in `agentik.lock`
- [ ] `hermes plugins install DietrichGebert/ponytail --enable`
- [ ] plugin active after Hermes restart
- [ ] DevOps Director can invoke Ponytail skills
- [ ] implementation flow uses Ponytail ladder
- [ ] review gate includes `ponytail-review`
- [ ] security/debt review available where configured

## Discord zero-to-operational bootstrap
- [ ] Discord application/bot created
- [ ] bot token stored outside Git
- [ ] bot connected to target guild
- [ ] bootstrap handshake proves target guild
- [ ] Bootstrap Director profile exists
- [ ] `discord.admin.bootstrap` capability exists
- [ ] desired state compiles from organization + installed OSs
- [ ] current guild state inventory captured
- [ ] diff generated before mutation
- [ ] repeated apply is idempotent
- [ ] roles generated
- [ ] role hierarchy verified
- [ ] categories generated/adopted
- [ ] channels generated/adopted
- [ ] category/channel permission overwrites applied
- [ ] OS/team/director/board bindings persisted by immutable IDs
- [ ] mission-thread policy configured
- [ ] route smoke tests pass for every exposed OS
- [ ] Administrator removed after bootstrap
- [ ] runtime bot permissions verified least-privilege
- [ ] drift detector healthy
- [ ] Discord bootstrap evidence stored

## Bot Mode / Virtual Teams

- [ ] Hermes Bot Mode enabled where OS manifests require it
- [ ] Persistent Bots created only for durable responsibilities/boundaries
- [ ] OS Director mapped to a persistent Hermes Bot/Profile
- [ ] Persistent NanoTeams compiled to Bot Groups
- [ ] Temporary specialists use `delegate_task` or Kanban workers instead of agent sprawl
- [ ] Dedicated Nano Director Discord bot/channel bindings compiled from installed OS manifests
- [ ] Channel defaults and virtual mentions resolve to immutable profile bindings
- [ ] One real Discord gateway per organization by default
- [ ] Separate Discord applications require an explicit identity/security boundary
- [ ] Bot-to-bot cross-organization communication denied by default
- [ ] Bot routing, permissions, Kanban and E2E mission verified by `agentik doctor`


## Engineering Constitution v4
- [ ] Gauntlet Loop configured and bounded
- [ ] Verification Engineering contracts compiled by risk class
- [ ] Hermes verify_on_stop enabled for code-modifying unattended profiles
- [ ] Ponytail installed for DevOps/Builder/Engineering OSs
- [ ] Model route aliases used instead of vendor-hardcoded workflow logic
- [ ] Subagent delegation contracts enforced
- [ ] parallel mutable work isolated by worktrees
- [ ] fan-out/fan-in integration gates tested
- [ ] typed Loop-Graph compiled into durable Hermes task state
- [ ] Hermes native logs retained as runtime truth
- [ ] AGK engineering episode evidence indexed
- [ ] Hermes self-improvement enabled according to organization policy
- [ ] shared skill promotion gated by eval/review
- [ ] security/policy self-modification prohibited


## Builder OS / OS factory
- [ ] Builder OS installed as system OS on development/candidate Node
- [ ] Locked 2026-08-31 AGK OS Contract present
- [ ] Librarian dependency reachable
- [ ] Four owner gates implemented
- [ ] 14_BUILDER_HANDOFF.md generated for every new/materially upgraded OS
- [ ] 15 domain inputs mapped into concrete contract deltas
- [ ] Dedicated Discord bot + channel per OS
- [ ] Fresh-session acceptance blocks automation enablement
- [ ] Doctor + rollback + recovery rehearsed
- [ ] Builder self-improvement cannot mutate hard governance rules
- [ ] Existing OS contract-gap audit available


## Orchestration Intelligence v9
- [ ] ambiguous missions produce explicit goal/constraints/acceptance;
- [ ] connector readiness is probed before dependency;
- [ ] plan graph has visible owners and verifier ownership;
- [ ] prepared/observed/reported/verified/read-back/accepted are distinct;
- [ ] parallel work has isolation + fan-in;
- [ ] source freshness/quality are declared for research;
- [ ] user-facing artifacts pass render/taste gates;
- [ ] memory promotion is review-first;
- [ ] degraded services expose next repair action;
- [ ] external coding language is executor-neutral.
