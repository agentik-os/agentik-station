# AGK CLIENT DELIVERY SYSTEM — GLOBAL MASTER v3

Status: canonical global operating standard
Applies to: every professional client managed by MISSION/AGK
Execution brain: Hermes Agent
Human control plane: Discord + authorized tracker state changes
Operational SSOT: AGK durable work record; Linear is the default tracker projection
Code SSOT: GitHub

## 1. Purpose

AGK is not a thin Discord → Linear → GitHub integration. It is an auditable agentic software-delivery operating system that understands why work exists, what success means, which client boundary applies, who owns each decision, which agents are active, what evidence exists, what risk remains and which human action is pending.

Canonical outcome:

```text
Request
→ Structured Mission
→ Durable Work Record + selected tracker (Linear by default)
→ Agentic Build
→ Pull Request
→ Automated Verification
→ Real Browser QA
→ Security
→ Staging
→ Business Review
→ CTO Review
→ Human Production Approval
→ Controlled Merge Main
→ Production Deployment
→ SRE Verification
→ Evidence
→ Done
→ Knowledge
```

The objective is verified client outcomes, not code generation.

## 2. Isolation

Every client is a security unit. Never mix client repositories, Linear resources, credentials, cloud projects, databases, environments, logs, knowledge, persistent sessions or evidence.

Canonical boundary:

```text
AGK
└── Client
    ├── identity
    ├── projects
    ├── missions
    ├── knowledge
    ├── architecture
    ├── repos
    ├── linear
    ├── agents
    ├── skills
    ├── workflows
    ├── infrastructure
    ├── environments
    ├── security
    ├── decisions
    ├── evidence
    ├── incidents
    ├── releases
    └── reports
```

`CLIENT.md` is the client context SSOT: business context, products, stakeholders, repositories, tracker teams/projects, environments, URLs, deployment strategy, security/data classification, allowed/forbidden tools, approvals, active missions and known risks. `.client/operations.yaml` is the machine contract for services, environments, pipelines, reliability, incidents, backup/recovery, dependencies, costs, access, offboarding, ADRs and runbooks.

Secrets never enter prompts, Linear, Discord, logs, git, documentation, screenshots or memory. Use client-scoped OAuth/Composio aliases or the canonical mode-0600 client vault. Tailnet Secure Input is the fallback for non-OAuth manual credentials.

## 3. Hermes is the agentic brain

Hermes is the required execution brain for every client organization. Atlas is
the public Project Manager alias. The six canonical execution identities are
Atlas, Architect, Forge, Sentinel, Release Engineer and SRE; the specialist
roster maps capabilities to those identities rather than creating a bot swarm.

- Every client has an isolated Hermes Project Manager profile.
- Every client has a named Hermes Project visible in AGK TUI.
- Every client has a durable client-scoped Kanban board/work graph.
- Product, Engineering, Quality, Design, Security and Platform work executes through preserved, inspectable Hermes sessions/runs.
- Every session is tagged or linked to client, project, mission, role and Linear issue.
- `Changes Requested` resumes the same issue, branch, PR and Hermes session. Never create a replacement context that loses history.
- Inter-agent communication uses the shared Linear issue/work record and durable Kanban comments/events. Every handoff states owner, requested input, expected output, evidence and blockers.
- Ephemeral delegation may assist a bounded subtask, but must not replace durable client supervision for material delivery work.

AGK TUI must expose client Project, sessions, active tasks, runs, blockers, reviews and evidence so the CTO can supervise the system rather than chase agents.

## 4. Client organization and channels

Each client receives:

- dedicated DevOps Atlas / Project Manager Discord bot;
- isolated Hermes PM profile;
- `dev-requests` owner intake channel;
- `cto-inbox`, `reviews`, `releases`, `incidents`, `client-status`, `agent-activity`;
- `team-product`, `team-engineering`, `team-quality`, `team-platform`, `team-design`;
- client Project and Kanban board visible in AGK TUI.

`dev-requests` is the canonical direct development request surface. The PM responds without requiring a mention, clarifies only necessary ambiguity, proposes a plan, then creates or links the delivery issue. It does not code from raw Discord prose.

Discord is the human interface and decision surface. The durable work record is
canonical; Linear remains the default tracker projection.

## 5. Request intake and mission normalization

Requests may originate from Discord, AGK UI, meetings, Linear, email, product feedback, monitoring, CTO, domain/product leaders or agent discovery.

The PM determines:

- client and project;
- request source;
- bug / feature / product / improvement / ops / security / research;
- urgency and business impact;
- technical impact and affected systems;
- dependencies and risks;
- required agents;
- human approvals;
- evidence and rollback needs.

The PM separates FACT, ASSUMPTION, DECISION, OPEN QUESTION and RISK. It never invents requirements.

No ambiguous request enters implementation. It first becomes a structured mission and Linear issue.

## 6. Feedback and delivery separation

Raw product/web feedback and Product & Engineering delivery are separate work surfaces.

```text
Raw Feedback Team / Project
→ PM Triage
→ validated opportunity
→ linked Delivery Team issue
→ Product Definition
```

Never implement directly from raw feedback. Preserve the source feedback issue and create a linked delivery issue with normalized context and acceptance criteria.

Client developers join the Delivery team, not the noisy raw feedback team, unless explicitly needed.

## 7. Durable work record and tracker issue contract

Every implementation mission requires a stable AGK work record and a selected
tracker issue containing:

- title;
- source and requester;
- business/product context;
- problem and expected outcome;
- user/business impact;
- complete relevant history and comments;
- attachments/screenshots;
- acceptance criteria;
- technical context;
- affected repositories/services;
- dependencies;
- security/data constraints;
- testing and real-navigation requirements;
- staging/deployment requirements;
- evidence required;
- rollback considerations;
- links to source feedback/meeting, mission, PR, staging, release, incident and decisions.

Agents must read the full issue, every comment, attachments, screenshots, linked issues, existing PRs/commits and affected project documentation before work.

## 8. Global semantic workflow

The default adapter projects these states into Linear. `agk-work-tracker/v1`
also supports GitHub Issues or a manual durable adapter when configured with
stable record ids and authoritative state ids. The current automated client
controller is Linear-first.

Canonical states:

```text
TRIAGE
PRODUCT DEFINITION / BACKLOG
READY FOR ENGINEERING
IN PROGRESS
ENGINEERING REVIEW
QA
SECURITY REVIEW
STAGING
BUSINESS REVIEW
CTO REVIEW
APPROVED FOR PROD
RELEASE QUEUED
DEPLOYING
PRODUCTION VERIFY
DONE
```

Exceptional states:

```text
BLOCKED
CHANGES REQUESTED
FAILED QA
FAILED SECURITY
FAILED DEPLOY
ROLLBACK
CANCELED
DUPLICATE
```

State semantics:

- `Product Definition / Backlog`: documented opportunity, passive by default.
- `Ready for Engineering`: explicit human authorization to start the scoped mission.
- `In Progress`: an agent has claimed and is actively working the issue.
- `Engineering Review`: implementation, architecture, tests and regression review.
- `QA`: acceptance criteria plus real browser/API/integration verification.
- `Security Review`: proportional risk review; mandatory for sensitive changes.
- `Staging`: deployed non-production evidence package exists.
- `Business Review`: domain/product leader validates the requested outcome.
- `CTO Review`: compact decision package is ready.
- `Approved for Prod`: authorized human production approval.
- `Release Queued`: AGK release controller accepted the approval and gates.
- `Deploying`: main merge/deployment pipeline executing.
- `Production Verify`: SRE verifies production and critical user flows.
- `Done`: verified outcome with complete evidence; human-only by default.

Agents update Linear automatically as execution changes. Agents may never set `Approved for Prod` or `Done`. Production deployment states are controlled by the release controller under a valid human authorization record.

## 9. BACKLOG IS PASSIVE

```text
BACKLOG = DOCUMENTED OPPORTUNITY
BACKLOG ≠ AUTHORIZED WORK
```

Meetings, agent discoveries, QA opportunities, monitoring suggestions and newly created issues may produce backlog candidates. They do not authorize coding.

Agents may analyze, document, estimate, prioritize, identify dependencies and prepare plans. They may not move backlog to Ready, create implementation branches, consume significant budget or start a mission without explicit human authorization.

Accepted triggers include:

- Discord/AGK UI `Start Mission`;
- explicit CTO or delegated Product/Domain Leader instruction;
- manual authorized Linear move to `Ready for Engineering`;
- approved client request.

Record who authorized, source, timestamp, client, project, issue, scope, priority and constraints.

## 10. Harness Engineering Loop

### Claim

- Validate client/project/issue/authorization.
- Move Linear to `In Progress`.
- Preserve issue, branch, PR, session and work record.

### Understand

- Read complete issue/history/evidence.
- Inspect architecture, relevant code, conventions, related issues, open PRs, dependencies, migration and deployment risk.
- Produce problem statement, expected vs actual, implementation plan, test plan, likely files/interfaces, data/API impact, security risk and rollback plan.

### Build

- Use the smallest capable team.
- Vertical slices and test-first behavior.
- One clear responsibility per task.
- Minimal scope; no unrelated refactor.
- Reuse project abstractions where appropriate.
- Add tests and update documentation.
- Never read or expose secrets.

### Engineering Review

Reviewer checks correctness, architecture, maintainability, complexity, duplication, errors, edge cases, performance, security, tests, observability, documentation and compatibility.

Findings use BLOCKER / HIGH / MEDIUM / LOW / SUGGESTION. BLOCKER/HIGH normally block progression.

### QA and real navigation

Coding complete is not QA complete. QA uses a deployed preview/staging surface and the exact client/environment/role Chrome profile declared in `runtime.yaml`. When authentication is required, anonymous, personal and cross-client profiles are forbidden. Authentication must be re-probed after every browser restart.

Verify:

- happy path;
- edge and failure states;
- permissions and tenant isolation;
- responsive/visual behavior;
- APIs/database/integrations;
- console errors;
- failed network requests;
- incoherent or non-logical behavior;
- regression risk.

Capture before/after/error screenshots, test report and exact reproduction/validation steps at mobile 390x844, iPad 820x1180, desktop 1440x900 and large desktop 1920x1080. Dismiss safe obstructing overlays before evidence capture or document why an overlay cannot be dismissed. Screenshots are full-page/unobstructed, must decode, carry dimensions/size/SHA-256, be posted to the client Quality channel and attached back to Linear through a verified URL. Browser evidence binds work, actor, session, exact URL and time window and receives a control-plane signed QA receipt. No QA pass without all four viewports and evidence.

Every material workflow gate receives a Linear evidence comment. Preserve failed attempts and correction loops instead of rewriting history. Comments identify issue/work/task/session, expected versus actual, exact environment/URL/build/viewport, executed steps and commands, console/network findings, PR/head SHA, CI/review/security/staging, risk/rollback, blockers and next human action. Attach before/after/failure images plus mobile, iPad, desktop, large-desktop and contact-sheet evidence. Discord mirrors this evidence but never replaces Linear.

### Correction loop

Any failure moves the issue back to `In Progress` and resumes the same branch, PR and Hermes session. Repeat Build → Review → QA/Security until acceptance criteria pass, real navigation works, no known blocker remains and evidence is complete.

## 11. Security review

Security is proportional to risk and covers authentication, authorization, secrets, PII/client data, validation/injection, dependencies, API exposure, permissions, tenant isolation, logging, storage, transport and infrastructure.

Authentication, payments, permissions, production data migrations, PII, infrastructure, secrets, billing and compliance are high risk and require explicit security and production confirmation.

## 12. PR and CI

Branch convention:

```text
client/project/linear-id-short-description
```

Every production change uses a PR except a documented emergency hotfix.

PR includes Linear issue, mission, problem, implementation, decisions, affected files/components, tests, security/migration impact, visual screenshots, staging URL, limitations and rollback.

Mandatory project-relevant CI may include build, lint, formatting, types, unit/integration/API tests, DB/migration validation, dependency checks, static analysis, secret detection and security scanning. Failed mandatory gates block human review.

## 13. Staging, business and CTO review

Substantial changes reach preview/staging before production. Linear records staging URL, commit SHA, PR, build/version, environment, evidence and known production differences.

Business/Domain Review answers: does this solve the requested business/product requirement? Record Approved / Changes Requested / Rejected.

CTO is not the first reviewer. The CTO receives a compact decision package:

- client/project/issue/feature;
- business approval;
- PR and implementation summary;
- CI/QA/security results;
- staging link;
- screenshots/evidence;
- risk and rollback;
- recommendation.

CTO actions: Approve Prod / Request Changes / Discuss / Hold / Cancel.

After all machine and business gates pass, the Project Manager posts the compact validation request with screenshots to the configured client `cto-inbox` channel. The authenticated human decision is read back from that exact guild/channel/message interaction. Agents never approve or mark Done on the human's behalf.

## 14. Approved for Prod automation

Linear can trigger controlled release through a signed webhook or verified polling controller. Linear does not push code itself.

When an authorized human approves the exact issue/PR/head SHA and then invokes the authenticated Deploy action, the controller may execute. A Linear state change or ambiguous chat message alone never authorizes deployment.

1. AGK validates webhook signature/replay window or state history.
2. Validate actor is CTO or delegated release owner and verify the exact Deploy interaction in the configured validation channel.
3. Validate client, DPE issue, linked PR, expected base/head branches and repository.
4. Validate CI, Engineering Review, QA, Security, Staging and Business/CTO decision package.
5. Validate production authorization record and no unresolved blocker/high-risk finding.
6. Create immutable Decision + Release Run.
7. Move Linear to `Release Queued`.
8. Merge the approved PR to `main` through GitHub API/merge queue; never raw blind push.
9. Trigger/observe the production pipeline.
10. Move Linear to `Deploying` and record commit/release.
11. On failure: `Failed Deploy` or `Rollback`, incident/evidence, notify CTO.
12. On success: `Production Verify` for SRE.

This controller must be idempotent, deduplicated by issue + approval + PR head SHA, fail closed, and start in dry-run mode for every new client.

## 15. SRE and completion

Production deployment is not completion. SRE verifies service availability, critical endpoints, errors/logs, latency, DB/infrastructure health, critical user flows, integrations and monitoring.

Risky releases maintain a verification window for error/crash/API/queue/DB rates, user reports, resources and business KPI anomalies.

Material regression creates an incident, pauses release, preserves evidence and rolls back when required.

`Done` requires implementation, merged PR, mandatory tests, QA, security when applicable, human reviews, successful production deploy, SRE verification, evidence and documentation. Code merged ≠ done.

## 16. Evidence, decisions and events

Proof > advice. Every mission produces proportional evidence: PR, commit, CI, tests, QA, security, screenshots/video, staging/production URLs, logs, metrics, approvals, release and rollback.

Important decisions record context, options, choice, rationale, tradeoffs, risks, owner, date, issue and PR.

Significant events include request/mission/Linear/task/agent/PR/CI/QA/security/staging/business/CTO/production/SRE/incident/completion lifecycle events.

## 17. Meetings

Meeting reports are evidence. Extract decisions, requests, problems, ideas, risks, questions, constraints, requirements, dependencies, potential bugs/improvements and candidate missions.

Distinguish DECIDED / REQUESTED / SUGGESTED / DISCOVERED / ASSUMED / OPEN QUESTION.

Meeting → candidate backlog, never meeting → autonomous coding.

Produce follow-up: decisions, changes, required action, backlog additions, validation required, blockers and investigations. Surface candidates in Discord with Start Mission / Open Linear / Keep Backlog / Reject.

## 18. Permissions and autonomy

Use least privilege:

- PM: Linear/project context, no production coding by default.
- Builder: issue branch write, no production.
- Reviewer: repo/PR review.
- QA: staging/test systems.
- Security: scoped repo/config/security reads.
- DevOps/Release: controlled pipelines.
- SRE: monitoring/logs and approved operations.

Agents autonomously plan, create issues, decompose, code authorized work, test, review, QA, security-check, document, deploy staging, collect evidence, update status and perform SRE checks.

The default loop is `decide → act → verify → record → continue`. Routine test
failures, review corrections and QA findings stay inside the same mission; they
are not blockers. `BLOCKED` is used only when no useful next action remains and
must include `blocked_by`, `already_tried`, `impact`, `need` and `resume`.
Material comments use `Status / Result / Evidence / Next` and are idempotent by
work record, material event and artifact version.

Humans retain ambiguous product/architecture decisions, sensitive security, destructive actions, production approval, material budget and contractual decisions.

## 19. Emergency and incidents

Hotfix:

```text
Incident → SRE Triage → Hotfix Issue → Minimal Fix → Expedited Verification
→ CTO Approval → Production → Verify → Postmortem
```

Incident management: detect, classify, open, notify, contain, collect evidence, mitigate, rollback/fix, verify, postmortem and prevention tasks.

## 20. Knowledge and continuous improvement

After significant missions capture architecture discoveries, client conventions, failure modes, deployment procedures, integration details, testing patterns, domain constraints, limitations and decisions.

Global knowledge contains generic workflows/skills/templates. Client knowledge contains client business/architecture/process/history. Never cross-contaminate.

Evaluate failures, human intervention, repetition, missing context/evidence and candidates for skills/tests/policies/automation.

## 21. Mission control and attention

AGK provides multi-client counts: active, blocked, awaiting business/CTO, releases and incidents. Notify CTO immediately for incidents, security, critical blockers, architecture decisions, budget impact, high-risk deploys, approvals and major scope changes. Do not spam normal success.

Daily digest: completed, active, blocked, awaiting client/CTO, PRs/staging ready, releases, incidents, risks and decisions.

## 22. Core laws

```text
DOCUMENT > MANUFACTURE
PROOF > ADVICE
DURABLE WORK RECORD > CHAT FOR DELIVERY STATE
PR > DIRECT PRODUCTION MODIFICATION
STAGING > BLIND DEPLOYMENT
VERIFICATION > ASSUMPTION
LEAST PRIVILEGE > CONVENIENCE
CLIENT ISOLATION > SHARED CONTEXT
AUTOMATION > REPETITIVE ADMIN
HUMAN APPROVAL > UNSAFE AUTONOMY
```

Agents may discover, document, propose and prepare work. Only humans authorize new backlog work to start.
