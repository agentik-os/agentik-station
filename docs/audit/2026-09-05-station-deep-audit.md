# Station deep audit and governed Strix integration

Status: LOCAL_VERIFICATION_COMPLETE — external acceptance pending. Baseline: `a0f5274` on `main`, 2026-09-05.

## Scope and acceptance

Owner: repository integration operator. Scope: the existing macOS Station development
checkout, its installer/runtime sources, shipped components, OS contracts and tests.
This is not authorization to run active security tests against a VPS, domain, cloud
account or production service. Tests use synthetic fixtures; live acceptance stays
explicitly pending. No production credentials or source uploads are authorized.

The requested work has two outputs: a working, governed Strix resource/team integration
and an evidence-based challenge of the repository. Reproducible defects in that path
may be repaired; material architecture alternatives are recommendations, not silent
whole-system rewrites. The previous model's identity is not evidence of correctness
or incorrectness.

## Plan First dependency graph

1. Baseline inventory and upstream/source probes.
2. Review the trust chain: bootstrap → release → identities → Hermes/OS compiler
   → tools/chat/credentials → execution → evidence/recovery.
3. Derive Strix's real package, runtime, CLI, exit-code and artifact contracts from
   pinned upstream source. Review the existing ScrapeGraphAI path against its library.
4. Implement the smallest native-Hermes integration, with explicit scope authorization,
   isolated credentials/runtime, resource limits and honest result interpretation.
5. Exercise regression and adversarial tests, native contracts and repository Doctor.
6. Publish findings with severity, evidence, repair state, alternatives and remaining
   live acceptance gates; update installation/atlas/resource documentation and metadata.

Dependencies: 1 → 2/3 → 4 → 5 → 6. Independent parallel review is optional and awaits
the user's choice; until then the repository integration operator owns all work.

Acceptance requires consistent pins/paths/manifests, a compiled Hermes team, a
fail-closed Strix adapter, tested ScrapeGraphAI contracts, passing relevant suites,
clean release hygiene and an explicit list of unexercised external gates. Installation,
configuration, local verification and operational acceptance are different claims.

## Verdict

Keep the architecture; strengthen its executable boundaries before adding another
orchestrator. **Hermes as the execution engine, Station as the Host/Zone control
plane, Projects as asset owners and OS packages as reusable teams is a useful
separation.** The weakest point is the distance between declared policy and
observed behavior. A rich contract catalog can pass every structural check while
a live Zone cannot traverse its HOME or a profile loses its project cwd.

This is a risk-based repository-wide architecture/implementation review, not a
claim of line-by-line verification of every vendored dependency or a penetration
test. High-risk paths were traced concretely; wider component behavior is covered
by existing test suites where indicated. No independent second reviewer was used
(the optional delegation question was not answered during implementation).

### Coverage and evidence limits

| Area | What was inspected/exercised | What remains unproven |
|---|---|---|
| Bootstrap and FHS | Shell bootstrap/dependency scripts; typed installer, identities, ownership, SafeFS, plans and temp-root tests | This revision booting on fresh Linux as multiple real UIDs |
| Release/Fleet | Manifest/provenance/SBOM generation; immutable publication; remote archive/SSH plan and receipt contracts | Fresh remote bootstrap, interrupted upgrade, rollback and Host identity attestation |
| Hermes/OS | All six source OS Doctors/compiler outputs; native distribution ownership; gateway/profile environment construction | Fresh installed-profile chat, actual service lifecycle and configuration-preservation behavior |
| DevOps team | Role/tool/provider/workflow/recovery contracts, deterministic program validator, Strix mission mapping | Every declared scenario executed against a live runtime; prompt text is not an ACL |
| Chat/setup | Native gateway integration, protected setup store and credential paths; component transport tests | Real Discord/Telegram/Slack OAuth, intents, interactions, expiry and rate-limit readback |
| Web extraction | Public/DNS/redirect boundary, worker process, environment and output; actual offline library tests | Paid extraction, production egress policy and deployed Chromium on both Linux architectures |
| Strix | Actual pinned CLI interface, Docker manifest metadata, upstream runtime/report source; synthetic adapter lifecycle | Docker/network isolation, container/source UID compatibility, LLM billing and real assessment quality |
| Memory/observability/voice | Installer/resource roles and maturity boundaries; existing component contracts | Honcho/Hindsight recall isolation, Langfuse trace redaction, Discord audio/Parakeet failover |
| AGK-TUI | Shipped component tests, plugin packaging and existing dashboard asset contract | A fresh interactive browser/desktop user journey on this revision |

## Repaired findings

Severity here describes impact if this path is deployed, not evidence of an incident.
All repairs are source/local-test claims until the Linux acceptance gate succeeds.

| ID | Severity | Concrete defect | Repair and evidence |
|---|---|---|---|
| F01 | P1 | OS compilation appended a second `terminal:` YAML mapping, overwriting cwd; worker configs retained the director ID. Raw path substitution could become YAML structure. | Structural safe-YAML merge, duplicate-key rejection, actual profile ID, literal project path, semantic round-trip tests in `tests/security/test_os_compiler_boundaries.py`. PyYAML is now an explicit runtime dependency, also installed by bootstrap/system packages. |
| F02 | P1 | Root compiled/published below Zone-owned `HERMES_HOME`, following ordinary path operations. Agent-controlled ancestors could redirect privileged writes; root `0700` publication parents also prevented Zone traversal. | Stage/publish only under root-owned `/opt/station`, reject writable/symlink ancestors, freeze public distributions. Regression rejects unsafe compiler/publication ancestors. |
| F03 | P1 | Mixed system/Zone FHS parents were `0750` for the system group, but Zone users have separate groups. Their own `0700` children remained unreachable. Organization/environment parents had the same issue. | Traverse-only `0711` shared parents; private children unchanged; explicit mode/Doctor regressions and an actual `runuser` traversal/denial probe added to disposable-VPS acceptance. That live probe has not been run locally on macOS. |
| F04 | P1 | Gateway/profile/Composio identity switches set selected env vars without clearing the inherited environment. Operator/provider secrets could bleed into a Zone process. | `env -i`, explicit HOME/HERMES_HOME/runtime/PATH values, argv regression tests. The Zone loads its own credentials; no caller key is forwarded. |
| F05 | P2 | Compiler copied `COMMANDS.yaml` and Librarian `research_fabric/`, but did not include them in native `distribution_owned`. | Native distribution ownership includes both; DevOps additionally includes the actual Strix plugin and team contract. |
| F06 | P1 | Hermes updater could report `VERIFIED_UPDATED`/exit 0 after gateway status failed. | Gateway failure now produces `DEGRADED_GATEWAY_FAILED`/nonzero exit; a fake-Hermes process regression checks the durable receipt. No automatic-update policy was silently disabled. |
| F07 | P2 | Parent Hermes performed DNS before entering the web worker's timeout; scratch output used global temp storage, and cancellation cleanup was incomplete. | Parent validates syntax only; all DNS/connect/fetch occurs inside the 180-second worker. Output lives in the Zone cache; termination is in `finally`; tests cover DNS placement and timeout cleanup. |
| F08 | P2 | A real ScrapeGraphAI run required a public tokenizer download absent from the install/import-only gate. | Fresh setup prewarms two SHA256-verified tokenizer assets; deployed worker health/extraction validates them. Real `SmartScraperGraph.run()` is exercised with a fake local model and networking disabled. Older immutable runtimes must be inspected/archived and rebuilt. |
| F09 | P1 | Tailscale returned `VERIFIED` for any valid JSON/zero exit, even `NeedsLogin`; missing `Online` defaulted to true. | Require Running backend, explicit online self node and assigned addresses. Six synthetic status regressions distinguish daemon observation from peer/ACL acceptance. |

## Remaining findings and decisions — not silently implemented

### D01 — P1: the always-sudo bootstrap operator is the largest blast radius

`bootstrap.sh` intentionally grants `agk-station` passwordless broad sudo by default.
That is consistent with the earlier “sudo AI operator” request, but inconsistent
with treating that same agent as a containment boundary. A hostile instruction in
a dependency, tool result or web page can become a Host-level incident if it drives
unrestricted terminal actions. Zone isolation cannot protect against Host root.

Recommendation: split conversational orchestration from a small privileged action
service accepting typed, scoped capabilities (operation, resource, digest, expiry,
nonce and human approval). The bot asks; the privileged service validates and
executes. Keep a human break-glass administrator. This is a substantial authority
change and needs a deliberate operator decision, not an undocumented sudo edit.

### D02 — P1: role/tool contracts are not a complete policy enforcement engine

`os/devops/tools/CONTRACTS.json` declares default deny, roles and budgets. The source
Doctor validates that declaration; it does not mediate every Hermes terminal,
MCP or provider call. The web plugin is distributed broadly. Profiles in one Zone
share its Unix trust domain. “Sentinel is independent” currently means workflow
separation, not an independently secured execution principal.

Recommendation: compile contracts into actual enabled toolsets/routes where Hermes
supports it; put irreversible operations behind typed adapters/capabilities; use a
different Zone/worker when genuine privilege separation is required. Add negative
tests in which the wrong principal invokes the real adapter. Avoid building a
second general agent scheduler to solve a permission problem.

### D03 — P1: Strix needs a disposable worker boundary, not production Docker

The integration deliberately installs only the CLI by default in the complete
stack. Active execution needs an operator-accepted LAB, reviewed source disclosure,
an expiring root-owned grant and a dedicated key. Snapshot filtering is not DLP;
an internal Docker network is not sufficient host isolation. The worker acceptance
hash records human attestation, not an automatic firewall proof.

Docker-capable actors can bypass local root-file controls; the LAB must therefore
be disposable and free of unrelated tenants/secrets. Provider-side budgets are
necessary: Strix cost limits are best effort, and the writable job marker is not
a hard cumulative/one-use ledger. No generic public-target scanner, cloud uploader,
autofix merge or additional autonomous Station director was enabled.

### D04 — P1: automatic updates do not yet implement the stated promotion rings

The check watcher (`hermes_updates.py`) explicitly plans LAB/candidate/stable
promotion. The weekly apply script directly runs `hermes update --backup --yes`,
then Doctor/gateway observation. These are two different mechanisms, not a tested
canary pipeline. State backup restoration is not automatically a code/environment
rollback, and local Doctor success is not connector/fresh-session acceptance.

Recommendation: auto-discover and build a candidate, run a disposable compatibility
mission, then promote the exact artifact to stable and retain the previous code
and state pair. Keep today's requested auto-update behavior visible until that
policy change is approved. The false-success bug itself is fixed in F06.

### D05 — P1 before rollout: reuse of release `11.12` is not an upgrade strategy

This working revision still has release ID `11.12`. The immutable installer correctly
refuses different bytes under an existing release directory with that ID. Pushing
new source to `main` does not upgrade an already installed immutable release.
OS package versions and preserved Hermes user configuration need the same care.
Native Hermes `profile install` also refuses an existing profile without `--force`;
`--force` copies distribution config rather than preserving user overrides. Station's
current install path is not yet an idempotent in-place OS migration/retry mechanism.

Recommendation: issue a new reviewed release ID before rollout, build the artifact
once, test migration from the previous release, promote it, and test rollback.
Do not weaken equality checks or overwrite old releases to make an update pass.
Repository integration and live deployment are separate deliverables.

### D06 — P2: pins and SBOM do not yet describe every installed byte

The top-level packages/wheels/images are pinned, but Python dependency closures
are resolved during installation. Shell bootstrap, generated SBOM and shared venv
publication are not one fully reproducible build pipeline. The SBOM lists declared
components and npm lock contents; it is not an inventory of an observed Host.

Recommendation: per-platform complete hashed Python locks, build/publish once,
record resolved dependency inventories and image digests in the installation
receipt, then compare declared vs installed. Keep executable build hooks away from
root where practical. Adding another library increases this workload.

### D07 — P1 before relying on recovery: backup/restore is not accepted recovery

`providers/backup.py` has a useful plan/run/check/staging split and does not claim
restore acceptance. However it accepts broad path inputs and ordinary parent-path
operations; it is not yet the same canonical scoped/SafeFS boundary as the installer.
Repository structural recovery checks validate a procedure/checksum, not a real
restored workload.

Recommendation: before exposing restore to an autonomous agent, bind it to a
validated Zone, explicit snapshot and isolated staging root; enforce no-follow
ancestor checks, complete credential ownership checks and negative tests. Rehearse
off-Host restore, then actual Hermes/connector readback. Do not advertise `restic
check` as proof that the whole system can be recovered.

### D08 — P2: protected setup is a bearer-link flow, not identity-bound approval

The broker hashes expiring one-time tokens, checks redirect domains and stores
keys locally, which is useful. A copied usable link is still a bearer capability.
The “requesting-principal-only” card label is a delivery requirement, not proof of
the HTTP submitter's Tailnet/chat identity. This must not be reused as a root action
approval without an additional identity/capability check.

Recommendation: bind sensitive approvals to a verified Tailnet/user identity and
the exact operation digest, with revocation and audit. Bound HTTP connection time
and concurrency. Generic `.env` secret serialization also deserves literal-value
tests for quotes/interpolation; Strix avoids that ambiguity with a separate file.

### D09 — P2: declared semantic scenarios are not executed evaluations

“Six identities / fifteen Librarian inputs / twelve scenarios” are structural
contracts in `os_contract.py` and `os/devops/programs/runner.py`. Those counts do not
measure judgment quality, real permission enforcement, recovery or independent
verification. Temp-root installation runs as one UID, explaining why F03 survived.

Recommendation: every important scenario names an executable test or recorded
mission. Run real different-UID probes, stale/expired approvals, malformed tool
output, provider outages, duplicate events, key rotation and interrupted updates.
Keep mock, real-library-offline and real-service acceptance results separate.

### D10 — P2: reduce overlapping state ownership and optional-service coupling

Honcho, Hindsight, Hermes memory, Station receipts, Kanban, Linear and Composio
serve different purposes, but “install all” does not define which one is authoritative
for each fact. Langfuse is observability, not mission authority; a tracker is not
the execution journal; a memory backend is not the approval ledger.

Recommendation: a per-Zone capability matrix explicitly selects memory backend,
tracker, identity and evidence owner; optional connectors can fail independently.
Keep the preferred Next/Convex/Clerk/Stripe/Vercel stack a Project recipe. Add
CPU/RAM/disk preflight before heavy browser, voice, memory or security capabilities.
Preserve the requested voice/web defaults, but do not claim every VPS can host all
services simply because their installers exist.

### D11 — P2: receipts and tools need a consistent data-minimization policy

Strix summaries deliberately exclude raw logs/findings. Other helpers still copy
subprocess stdout/stderr into receipts. Native tools/providers can emit identifiers,
request bodies or secrets. Broad log capture is not equivalent to redaction.

Recommendation: typed summaries plus private raw artifacts with explicit retention,
per-Zone access and redaction tests. Never publish raw evidence automatically to
Discord, a tracker, Langfuse or a shared Control projection.

## Recommended implementation order

1. **Runtime truth first:** fresh Linux multi-UID acceptance, native profile/chat
   acceptance and a new immutable release/migration test. Prove repaired boundaries.
2. **Authority next:** decide the privileged-operator split, capability/approval
   service and provider-side budgets. Keep core/shared Hosts free of Strix Docker.
3. **Reproducibility and recovery:** complete dependency locks, candidate promotion,
   installed-state receipts, then off-Host restore/fresh-session rehearsal.
4. **Product quality:** executable DevOps scenarios, connector failure handling,
   memory/backend ownership, resource preflight and real multi-platform UX tests.

Do not start by adding more agent identities, another database of the same mission
or another universal workflow engine. The system becomes stronger when ownership,
permissions and evidence remain comprehensible with fewer independent moving parts.

## Verification record

Final suite counts and publication state are recorded in `VALIDATION_11_12.md` after
the regression run. The pinned Strix CLI was installed in an isolated local uv
environment and `--help` inspected; Docker image metadata was read without starting
a daemon/container. ScrapeGraphAI's actual graph ran with a fake local model and
network disabled after public tokenizer assets were prewarmed. No paid model call,
active scan, production credential, external upload or VPS deployment occurred.

External gates remain: clean Linux install/update, real Zone/native Hermes session,
Discord/Telegram/Slack and Composio readback, voice failover, LAB network/container
acceptance and synthetic Strix assessment, provider budget observation, and restored
workload acceptance. No result here establishes production `OPERATIONAL` status.
