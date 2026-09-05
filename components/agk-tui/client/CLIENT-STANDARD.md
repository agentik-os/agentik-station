# AGK Client Organization Standard

Standard version: `2`

This is the **legacy shared-operator client workflow**, also selected explicitly
by `station client --legacy`. Client workspaces and Hermes profiles separate
routing, configuration and conversation state; clients inside `mission` share
its Unix identity and may share CLI authentication under its `HOME`. They are
not separate Station Zones or Unix sandboxes. AGK business objects use the stable
client id from `.client/manifest.yaml`.

For new Station clients, register their existing Organization environment Zones
with `station organization register`, then enroll a domain runtime with
`station os instance install`. OS instances and Projects are siblings in each
Zone. Use different Zones for client/environment isolation. These legacy commands
neither provision that boundary nor migrate existing client data or credentials.

## Sources of truth

- The AGK durable work record owns canonical delivery identity, authorization,
  context continuity, evidence pointers and state history.
- Linear is the default work-tracker adapter and owns its projected product
  issue, comments and configured workflow state. The protocol also permits
  GitHub Issues or a manual durable tracker adapter when the client contract
  explicitly selects it; the current automated client controller is Linear-first.
- GitHub owns code, branches, commits, pull requests and CI evidence.
- Figma owns product design when the client uses it.
- Google Drive owns meeting summaries and source documents when enabled.
- Hermes owns agent execution and resumable conversation state.
- The client runtime owns staging and production execution.
- Discord is the human decision interface, never the work database.
- AGK owns orchestration, policy checks, audit records and identity mapping.

## Mandatory delivery invariant

```text
NO DURABLE WORK RECORD / TRACKER ISSUE
    -> NO CODING
    -> NO COMMIT
    -> NO PULL REQUEST
    -> NO DEPLOYMENT
```

Every work record preserves the same client, tracker issue, repository, branch,
mission id and Hermes session throughout revisions. `REQUEST CHANGES` resumes
that existing context; it must not silently create a fresh agent session.

## Client boundary

```text
workspace/clients/<slug>/
├── README.md
├── CLIENT.md
├── AGENTS.md
├── CLAUDE.md
├── .client/
│   ├── manifest.yaml
│   ├── runtime.yaml
│   ├── integrations.yaml
│   ├── permissions.yaml
│   ├── workflow.yaml
│   ├── team.yaml
│   └── operations.yaml
├── repos/
├── knowledge/
├── projects/
├── artifacts/
├── deployments/
├── infrastructure/
├── automation/
├── scripts/
├── logs/
├── state/
│   ├── work/
│   ├── reviews/
│   └── runs/
└── tmp/
```

Secrets never live in that tree. The only supported local secret store is:

```text
~/.config/agk/clients/<slug>/env
```

It is owned by the current profile and has mode `0600`. Composio OAuth tokens
remain in Composio's profile-local store; client configs contain only account
aliases such as `client-<slug>-linear`.

## Logical team

Atlas is the Hermes orchestrator and is exposed to clients with the friendly
alias Project Manager. The executable team contains exactly six stable
identities: Atlas, Architect, Forge, Sentinel, Release Engineer and SRE. The
larger product/design/frontend/backend/QA/security/platform/FinOps roster is a
capability map onto those six identities, not 17 independent bots.

Product
Management owns product direction while the Project Manager owns intake,
decomposition, agent routing, delivery status, risks and acceptance
coordination. The meeting-intake coordinator converts cited Google Drive meeting
summaries into deduplicated Linear work.

The team definition is logical and cheap. Roles are instantiated on demand and
their sessions are preserved; they are not permanent processes. The standard
roster covers Product, Engineering, Platform, Security, QA, Release,
Observability, FinOps and Design. Every runtime session is tagged with `client`,
`project`, `mission`, role and Linear issue metadata.

## Workflow and human gates

The same semantic gates can be projected in two views: `compact` for normal
product delivery and `regulated` when every QA/security/release state must be
visible. Hiding a state never removes its gate.

The standard flow is:

```text
DEV REQUEST / VALIDATED FEEDBACK
  -> PRODUCT DEFINITION
  -> READY FOR ENGINEERING
  -> IN PROGRESS
  -> ENGINEERING REVIEW
  -> REAL BROWSER QA
  -> HUMAN VALIDATION
  -> CTO APPROVED
  -> READY TO DEPLOY
  -> PRODUCTION
  -> VERIFIED
  -> DONE
```

Raw web feedback and product/engineering delivery are separate work surfaces.
Feedback is never implemented directly: the Project Manager triages it and
promotes a validated item into a linked delivery issue containing full context,
acceptance criteria, risks and a test plan. Direct owner development requests
enter through the dedicated `dev-requests` Discord channel; the PM proposes a
plan and creates or links the delivery issue before any coding begins.

When an agent claims work, Linear moves to `IN PROGRESS`. The agent reads the
complete issue, all comments, attachments, screenshots, linked feedback,
existing commits/PRs and affected code before implementation. Coding complete
is not QA complete. Work uses test-first vertical slices, engineering/security
review and real navigation in a deployed non-production environment using
Chrome when available. Browser QA covers happy paths, edge/error paths,
responsive and visual coherence, console errors, failed network requests and
non-logical behavior. Screenshots and exact validation steps are attached to
Linear.

Any defect returns the same issue, branch, pull request and preserved Hermes
session to `IN PROGRESS`. The loop repeats until acceptance criteria pass, real
navigation works, no known blocking bug remains and evidence is complete. Only
then may an agent propose `HUMAN VALIDATION`.

`CTO APPROVED` means the engineering result is accepted. `READY TO DEPLOY`
requires a separate production authorization. A production action without that
second approval is rejected even when engineering was already approved.

`CTO APPROVED`, `READY TO DEPLOY`, `PRODUCTION` and final `DONE` are human-only.
Agents may prepare proposals and evidence but cannot set, simulate or complete
those fields without an authenticated human interaction and recorded decision
id. `DONE` follows verified production health and user-visible behavior.

Specialists are on-demand preserved sessions visible through AGK TUI. Every
inter-agent handoff records owner, requested input, expected output, evidence
and blockers in the shared Linear issue/work record. Discord provides the human
interface and debug stream but never replaces Linear as source of truth.

Default autonomy is `decide → act → verify → record → continue`. An agent asks
only when no safe useful path remains. `BLOCKED` is valid only with all five
fields—`blocked_by`, `already_tried`, `impact`, `need`, `resume`—and resumption
uses the same work record, branch, PR and Hermes session. Material tracker
comments use `Status / Result / Evidence / Next` and deduplicate on work,
material event and artifact version.

## Operational completeness

`.client/operations.yaml` is the machine contract for the parts a code-only
workflow commonly misses: service ownership, environments and data classes,
pipelines/artifact identity, SLI/SLO/error budgets, alerts, incidents/on-call,
postmortems, encrypted off-Host backups with RPO/RTO and restore rehearsal,
dependency/vulnerability/license policy, costs, access reviews, offboarding,
ADRs and runbooks. Production cannot be called complete while a required
section is empty or unverified.

## Policy levels

- L0: read-only inspection.
- L1: branch and development changes tied to a Linear issue.
- L2: staging actions with evidence.
- L3: production actions requiring explicit human authorization.
- L4: critical operations; destructive database deletion is forbidden and
  other critical actions always require a CTO authorization.

Every infrastructure action becomes an immutable AGK Run record containing the
actor, machine, action, before/after versions, issue, commit, timestamps,
result, evidence and rollback availability.

## Integrations

Client integrations are selected through stable, non-secret aliases. A client
must never fall back to another account merely because it is the profile's
default connection. The expected aliases are recorded in
`.client/integrations.yaml` and verified before external actions.

GitHub, Vercel, Convex and Google Drive are first-class optional integrations.
Convex credentials stay in the client secret store and every development,
staging and production deployment id must be explicit. Google Drive uses a
client-specific account alias and folder allowlist; every Linear task created
from a meeting cites its Drive source and is deduplicated by file id plus content
hash.

Discord supports a shared CTO Command Center or a dedicated client bot. The
default onboarding path uses a dedicated DevOps Atlas bot with
client-scoped categories/channels and explicit connection aliases. Provisioning
is dry-run first, idempotent and must roll back resources created by a failed
apply.

Linear webhooks are accepted only when the HMAC-SHA256 signature over the raw
request body is valid and `webhookTimestamp` is within the configured replay
window. Webhook secrets are never written to the client workspace.

## Installation contract

`agk client bootstrap` installs this standard without provisioning a client.
`agk client init` performs local, transactional scaffolding only. External
resources are planned and verified separately; creation requires an explicit
apply command and human confirmation.

The same controller is available from the Station entry point:

```bash
station client bootstrap --upgrade
station client init <client-id> --name "Client Name"
station client doctor <client-id> --online
```
