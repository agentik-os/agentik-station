# AGK client organizations

AGK turns each Mission client into an isolated, resumable delivery system.
This document describes the installed contract and the commands an operator
uses. It does not authorize AGK to create remote resources during installation.

## Ownership model

```text
                         AGK CONTROL PLANE
                                  │
                 ┌────────────────┼────────────────┐
                 │                │                │
              CLIENT A         CLIENT B         CLIENT C
                 │                │                │
        credentials/memory  credentials/memory  credentials/memory
        repos/runtime       repos/runtime       repos/runtime
                 │                │                │
            Product team     Product team     Product team
            Platform team    Platform team    Platform team
```

The role definitions are shared. Client credentials, memory, repositories,
runtime context, data and production authority are not shared.

- Linear is the source of truth for product work and status.
- GitHub is the source of truth for code and CI evidence.
- Figma is the source of truth for design when enabled.
- Hermes is the execution runtime and conversation state.
- Discord is the human decision interface.
- AGK owns orchestration, identity mapping, policy enforcement and audit.

## Installed boundary

`agk client init <slug>` creates a private workspace under
`~/workspace/clients/<slug>`. Its `.client` directory contains only non-secret
configuration. State is divided into work items, reviews and Runs. Secrets that
cannot live in Composio are stored at `~/.config/agk/clients/<slug>/env` with
mode `0600`.

Every client gets its own Hermes profile ID and canonical RMUX session prefix.
An agent session is bound to the client, AGK work ID, Linear issue, repository
and branch. A collision with another binding is rejected.

## Safe onboarding

The bootstrap is intentionally empty:

```bash
agk client bootstrap --upgrade
agk client list
```

Plan the local client before writing anything:

```bash
agk client init acme --name "Acme" \
  --runtime hybrid \
  --github-mode org --github-org acme \
  --linear-workspace WORKSPACE_ID --linear-team TEAM_ID \
  --discord-mode shared-command-center --discord-guild GUILD_ID \
  --dry-run
```

Remove `--dry-run` to commit only the local, transactional scaffold. If a local
step fails, AGK removes the stage and does not register a partial client.

The integration plan returns the exact client-scoped aliases to connect:

```bash
agk client integrations plan acme
agk composio connect linear --alias client-acme-linear --no-browser
agk composio connect github --alias client-acme-github --no-browser
agk composio connect discordbot --alias client-acme-discordbot --no-browser
agk client integrations verify acme
```

Use the same Linux profile for Composio login, connection and AGK execution.
For the standard VPS topology that is normally `mission`:

```bash
sudo -u mission -H agk composio login
sudo -u mission -H agk client integrations verify acme
```

Discord has a read-only plan and a distinct write command:

```bash
agk client discord plan acme
agk client discord apply acme --yes
```

Apply uses the exact configured Composio account. It reuses an existing
matching category and channels, creates only missing resources, and rolls back
resources created by that attempt if the remote sequence or local config
commit fails.

Activate the isolated Hermes context only after reviewing the client:

```bash
agk client activate acme --yes
# Run the returned next_command: hermes --profile <generated-id> setup
agk client doctor acme --online
```

Activation deliberately creates a blank profile instead of cloning another
client or the collective profile. The returned `next_command` completes model
authentication and configuration inside that new boundary. AGK refuses to
start the client session until its `config.yaml` exists.

## Work lifecycle

AGK rejects work without a canonical Linear issue and a repository declared in
`.client/integrations.yaml`:

```bash
agk client work create acme \
  --issue ACM-142 \
  --title "Classify attachments" \
  --role backend-engineer \
  --repo acme/product \
  --target staging
```

The created record fixes the issue, provider, role, session, repository and
branch. Start the real Hermes conversation with:

```bash
agk client work start acme WORK-XXXXXXXXXXXX
```

Map each AGK status to the client's exact Linear workflow-state UUID in
`.client/integrations.yaml`. Preview and then apply a client-scoped status and
journal update:

```bash
agk client linear plan acme WORK-XXXXXXXXXXXX
agk client linear apply acme WORK-XXXXXXXXXXXX --yes
```

Apply verifies that the issue belongs to the configured client team before it
writes. Journal comments carry deterministic markers, so retrying the same
state and evidence does not duplicate the comment.

Record delivery evidence and advance only through declared transitions:

```bash
agk client work transition acme WORK-XXXXXXXXXXXX agent_review \
  --actor backend-engineer
agk client work transition acme WORK-XXXXXXXXXXXX automated_qa \
  --actor qa-engineer
agk client work evidence acme WORK-XXXXXXXXXXXX \
  --actor qa-engineer \
  --pull-request https://github.com/acme/product/pull/284 \
  --commit 882ba43 --ci passed --qa passed --security passed \
  --preview https://staging.example/ACM-142 --risk low
agk client work transition acme WORK-XXXXXXXXXXXX ready_for_cto \
  --actor qa-engineer
agk client work review-card acme WORK-XXXXXXXXXXXX
agk client discord review-plan acme WORK-XXXXXXXXXXXX
agk client discord review-apply acme WORK-XXXXXXXXXXXX --yes
```

The Discord delivery targets the provisioned client `#reviews` or `#releases`
channel, disables mentions, and stores the message identity in the work record
so an identical retry does not post twice. The generated component IDs include
the client and work IDs. The Hermes gateway listener applies the same user,
role and channel authorization as slash commands, then routes the action back
to AGK, where the workflow gate is validated again. `REQUEST CHANGES` opens a
modal and resumes the recorded session when it exists; `DEPLOY` queues a
governed deployment request but does not bypass the Run policy or execute an
unconfigured target.

`READY_FOR_CTO` is blocked until PR, CI, QA, security and staging evidence all
exist. Engineering acceptance and production authority use different IDs:

```bash
agk client work approve acme WORK-XXXXXXXXXXXX \
  --approval-id ENG-APPROVAL-ID --actor cto-user-id
agk client work authorize-deploy acme WORK-XXXXXXXXXXXX \
  --approval-id PRODUCTION-AUTH-ID --actor cto-user-id
```

The same ID cannot satisfy both gates.

## Request changes and session continuity

```bash
agk client work request-changes acme WORK-XXXXXXXXXXXX \
  --actor cto-user-id \
  --feedback "Handle corrupted files and expose retry."
agk client work resume acme WORK-XXXXXXXXXXXX \
  --feedback "Handle corrupted files and expose retry."
```

The first command records the decision and clears obsolete approvals. The
second resumes the exact registered RMUX/Hermes session and injects the
feedback. It refuses to create a replacement if that preserved session is
missing or belongs to another client or mission.

## Governed infrastructure Runs

Policies live in `.client/permissions.yaml`:

- L0: read-only inspection.
- L1: development changes tied to an issue.
- L2: staging actions.
- L3: production actions requiring human approval.
- L4: critical actions requiring human approval; database deletion is
  forbidden.

A production deployment is represented by a Run:

```bash
agk client run start acme WORK-XXXXXXXXXXXX \
  --action deploy_production \
  --actor release-manager --machine acme-prod-01 \
  --commit 882ba43 --before v1.4.21 --after v1.4.22 \
  --approval-id PRODUCTION-AUTH-ID --rollback-available
agk client run complete acme RUN-XXXXXXXXXXXX \
  --result success --evidence health-check:passed --evidence smoke-test:passed
```

AGK validates the work state and recorded production authorization before the
Run starts and again before a successful production completion is committed.
After deployment, record health evidence, transition to `verified`, mark the
authoritative Linear issue done, then transition to `done`.

## Webhook boundary

The local Linear verifier checks the HMAC-SHA256 signature over the exact raw
body with constant-time comparison and rejects events outside the replay
window:

```bash
LINEAR_WEBHOOK_SECRET=... agk client verify-linear-webhook \
  --body event.json --signature "$LINEAR_SIGNATURE"
```

The HTTP receiver must preserve the raw request bytes, return quickly, and
queue longer orchestration work. Discord decisions are handled through the
configured Hermes gateway, whose own identity and channel policy must still
authorize the actor. Review buttons do not replace AGK's state checks: the
backend validates every transition again.

## Recovery and diagnosis

```bash
agk client show acme
agk client doctor acme
agk client doctor acme --online
agk client work show acme WORK-XXXXXXXXXXXX
agk client integrations plan acme
```

`doctor --online` requires every enabled integration alias to exist and be
active. A profile default connection with the right toolkit but the wrong
client alias fails the check by design.

Do not manually copy one client's secret store, Hermes profile or state into
another client. Repair the declared connection or runtime mapping instead.

## Upstream protocol references

- [Linear webhooks](https://linear.app/developers/webhooks)
- [Discord interactions](https://docs.discord.com/developers/interactions/receiving-and-responding)
