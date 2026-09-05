# VPS workflow and system-map review

Date: 2026-09-05. Baseline: `c923a6c` on `main`.

Scope: repository concept, fresh-VPS bootstrap, failing component CI and the public
README. This is source/fixture verification, not acceptance of a live VPS, model
account or Discord bot. The previous model's identity is not evidence for or
against the design.

## Plan First and ownership

1. Trace Host → Zone → Project → OS → Hermes → chat/tools → evidence.
2. Independently inspect bootstrap correctness, native runtime boundaries and CI.
3. Repair reproducible defects without selecting a new tenancy or sudo model.
4. Restore complete system explanation with source-owned SVG maps and text.
5. Run adversarial fixtures, component/repository checks, render inspection and
   release metadata validation; publish the result with explicit acceptance limits.

The root integration operator owns bootstrap/preflight, documentation and final
verification. Independent reviewers own launcher/guided-setup fixes, CI/runtime
repairs, SVG assets and bootstrap regression fixtures. Each review branch reports
evidence to the integration owner; no live external setup is delegated.

## Verdict: keep the concept, strengthen the transitions

Station should remain the governed Linux foundation, Zones the identity boundary,
Projects the asset owners, OS packages the reusable teams, and Hermes the execution
engine. Chat is a projection. A provider supplies inference, not authority. A
second scheduler or an all-powerful chat process would blur these useful boundaries.

The practical weakness is **transition reliability**: a catalog is not installed
profiles; installed profiles are not a routed bot; a successful kernel is not a
completed bootstrap; a model's report is not accepted execution. The new README
maps show both those relationships and their pending verification gates.

## Repaired defects

| Area | Observed problem | Source repair and regression |
| :--- | :--- | :--- |
| Wrapper input | Process-substitution errors could be swallowed and fall back to a core install | Direct checked argument construction; missing values/invalid modes rejected; real full/team specs tested |
| Wrapper lifecycle | RETURN cleanup fired again after local variables went out of scope; empty arrays failed under Bash 3.2 | Subshell-scoped EXIT cleanup; safe empty-array expansion; success/cancellation/failure fixtures |
| Early bootstrap | Eligibility and target checks occurred after package/account work | Read-only `--plan`, early Host/identity/path checks, no overwritten foreign checkout, exact published-tree drift check |
| Plan/apply | Bootstrap reconstructed desired state after earlier mutations | Generate/show one InstallSpec and pass that exact file to kernel apply in the confirmed invocation |
| Password sudo | A newly created locked account could not complete nested interactive sudo | Already-authorized root bootstrap invokes the kernel; human still sets the future account password |
| Hermes ownership | AGK-TUI could install Hermes even when parent bootstrap skipped it | Parent owns install lifecycle; AGK always receives `--without-hermes` |
| Hermes launcher | Sync could replace an installed launcher with a self-referential symlink | Resolve and validate source/destination; preserve an identical launcher; reject directory targets |
| Guided setup | Zero-exit Tailscale status could report offline/NeedsLogin with stale DNS; service startup health raced | Bounded loopback retry and one validated Running/Online/IP snapshot; optional unenrolled state is explicit, not private-URL success |
| Update timing | Weekly updater was enabled before remaining selected stages | Enable after selected dependencies and guided setup succeed |
| Component dependency | Root CI's dev environment lacked Pillow used by component tests | Declare the existing reviewed Pillow pin in root dev extras and the SBOM |
| Real web worker | Local `operator.py` shadowed Python's stdlib module when the worker was executed directly | Rename to `operator_commands.py`; update import; test real direct subprocess startup with and without site initialization |

Bootstrap preflight is an early accident/conflict check. It is not a race-proof
root transaction over operator-writable paths. Kernel SafeFS checks remain the
privileged reconciliation boundary; the broader operator/supply-chain trust issue
is not solved by adding more path validation.

## Verification performed

- Executable wrapper/bootstrap fixtures under Bash 3.2 and 5.3: **117 passed**.
  Package managers, accounts, sudo, installers and services were stubbed. Tests
  assert no mutation call occurs during planning or rejected-input paths.
- Launcher and guided-setup focused tests: **28 passed** with synthetic services,
  Tailnet JSON and launcher trees. No real Tailnet or systemd changes.
- CI/runtime repair: actual pinned Crawl4AI and ScrapeGraphAI environments each
  passed their offline library tests and direct worker health/Chromium launch.
  This is local package compatibility, not paid extraction or deployed Linux egress.
- Six SVGs rendered and inspected at desktop and mobile widths. Static geometry,
  self-containment, semantic descriptions and reduced-motion behavior are checked;
  no live browser or GitHub animation execution was available locally.
- Aggregate repository suite: **338 passed**; shipped AGK-TUI suite: **225 passed,
  2 optional-library skips**; Builder/Librarian deterministic gates: **7/7**.
  The optional libraries were exercised separately as described above.
- Repository Doctor passed, including with Python site packages disabled;
  generated metadata matched the 1,099-file inventory. Python AST, JSON/YAML,
  selected schemas, shell syntax and identity/action-pin hygiene passed.
  GitHub Markdown rendering preserved all seven SVG references and disclosure
  sections. GitHub CI is repository evidence, not deployed-Host acceptance.

## Decisions and work not silently implemented

### 1. Decide what an OS instance owns

Published OS distributions are scoped by Zone/Project, but native profile names
and runtime receipt keys are not consistently instance-scoped. Installing the same
OS for a second Project in a Zone can collide. A Project-specific cwd makes the
conflict operational, not merely cosmetic.

Choose explicitly between **one team per Project** (instance-qualified profiles,
bindings and receipts) and **one team per Zone** (a validated per-mission Project
context). Until then, do not promise repeated multi-Project OS installation.
A clear duplicate-instance rejection is safer than an automatic force overwrite.

### 2. Connect the intended Director, not just a Zone gateway

Generic platform setup selects the Zone's default gateway. It does not complete
the intended one-OS/one-Director/one-bot routing automatically. Installation must
bind and read back the selected native profile, guild/channel and human allowlist.
Discord, Telegram and Slack need separate transport acceptance. Rich Discord
cards are not proof of permission enforcement or parity on every provider.

### 3. Make retries and acceptance durable

An OS distribution can be published before all profile installs succeed. A retry
then encounters an existing immutable destination. Whole-bootstrap stages also
lack one global lock and durable stage journal; interrupted web-runtime builds can
need supervised repair. Kernel `READY_FOR_SETUP` may coexist with later failure.

Next implementation should reuse only an identical validated bundle, record
per-profile/stage completion and preserve operator configuration. Bind acceptance
receipts to package/configuration digests and runtime observations; printed Doctor
output alone must not act as a durable acceptance record. Keep migrations explicit.

### 4. Reduce authority and prove updates/recovery

Broad passwordless operator sudo, incomplete runtime tool ACL enforcement, mutable
upstream transitive installers, full dependency locking, canary/ring promotion,
code-and-state rollback and off-Host restoration remain separate workstreams from
this repair. `--sudo-mode password` is not an enforcement service. Same-Zone roles
are not separate Unix security principals. Strix still requires a disposable LAB,
an approved target/source boundary and human consent; no active scan was run.

## The first live acceptance mission

Use a disposable supported Linux VPS, one development Zone, a synthetic Project,
the DevOps OS, one model account and a dedicated test Discord application.

1. Review `bootstrap.sh --plan`, install and save stage/Doctor evidence.
2. Install the OS, verify the exact native profiles and Project cwd, then bind Atlas.
3. Ask Atlas to fix a deliberately failing greeting test. Forge implements the
   repair; Sentinel verifies it; Atlas returns an evidence nonce and artifact links.
4. Test denial for an unauthorized user and channel without exposing credentials.
5. Restart the gateway; repeat in a fresh session and read back the actual Project.
6. Separately exercise update failure and restoration before production promotion.

Passing this mission accepts only that configuration. It does not accept voice,
all providers, every OS, Fleet, Strix isolation or production recovery by extension.

## Release boundary

This remains a source candidate on release line `11.12`. A Host with different
content already frozen under that version must not be overwritten. A reviewed new
release identity and supervised migration are required for deployment upgrades.
The new preflight intentionally detects that conflict before bootstrap mutation.
