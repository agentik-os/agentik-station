# Station 11.13 — Owned orchestration review

## Outcome and scope

The product change is the path from a reviewed clean-VPS installation to an owned
Project, a complete installed OS team, its selected Director and a testable first
mission. It is not another orchestration engine: **Hermes executes; Station owns
placement, structure, policy, installation evidence and the next operator action.**

The [first-mission guide](../operations/06_FIRST_MISSION.md) is the executable
operator sequence. The [earlier review](2026-09-05-vps-workflow-review.md) records
the source defects and unresolved choices that led to this release.

## Reviewed implementation plan

1. Persist the outer bootstrap's stages separately from kernel reconciliation.
2. Bind native OS installation to a trusted Project and exact complete team.
3. Route provider and chat setup to the named Director, never incidental state.
4. Expose local observations and ordered next actions without executing them.
5. Close the missing Project-creation step for full/core and System/Factory Zones.
6. Verify adversarial failures and publish as a new immutable software release.

Parallel ownership separated bootstrap state, OS lifecycle and onboarding/Project
creation. Root integration owned CLI wiring, documentation, release identity and
cross-module checks. No live VPS, external account enrollment, Discord deployment,
paid model request or Strix scan is implied by local tests.

## What changed

| Gap | Implementation | Deliberate boundary |
| :--- | :--- | :--- |
| Kernel success hid later bootstrap failure | Separate held lock, exact spec/options/source fingerprints and durable named stages | Reported state, not an atomic all-system transaction |
| Blind rerun after an incomplete bootstrap | Explicit attempt-ID acknowledgement and retained previous receipt | Fresh reviewed attempt; no automatic skip, rollback or orphan-process cancellation |
| Full/core Zones lacked their first workspace | Scoped Project command reuses canonical kernel layout and rules | Never overwrite an existing/partial Project; no Host/dependency reinstall |
| OS success relied on one command or Director | Root-owned ledger, complete-team native file readback and per-profile checkpoints | Unknown/ambiguous existing profiles require repair, never `--force` |
| OS names collided across Projects | Each `(Zone, OS id)` binds one team/Project/version and immutable bundle hash; multiple Projects and distinct OS teams remain possible | No multi-Project instance naming or automatic old-profile adoption |
| Chat could select an incidental profile | Trusted Director resolution and explicit Hermes `--profile` | Zone default remains explicit when no OS is selected |
| Provider setup was disconnected from OS setup | Selected Director's native provider wizard | Human controls account consent; secrets stay outside bundles/receipts |
| Setup printed generic gates | Dependency-ordered local read model with exact next commands | No automatic execution, authentication or live acceptance |
| Status observation could execute Hermes startup | Opt-in bounded systemd-only probe | Service state is not a successful bot mission |
| Metadata checks modified immutable artifacts | In-memory expected SBOM/provenance/manifest from `VERSION` | Generation is an explicit separate write |

The source implementation lives in `bootstrap_state.py`, `projects.py`,
`os_lifecycle.py`, `onboarding.py`, `hermes_platforms.py` and `cli.py` under
`src/agentik_station/`. No second runtime scheduler or duplicated OS definition was
introduced. Project rules still come from the kernel's canonical templates.

## Evidence contract

An OS installation records the expected complete team and exact bundle. Every
native profile must contain the required distribution metadata and critical
Project configuration. Safe retries preserve completed profile state and install
only missing profiles; malformed, untracked, renamed, conflicting or tombstoned
profiles stop the operation. Native stdout/stderr are not copied into receipts.

`station os verify` runs Doctor for the full team, then reads the team back again.
It records local Doctor evidence against configuration hashes. Later configuration
changes make that evidence stale. A failed Doctor is repairable through the native
setup wizard and another verification; it does not require overwriting the profile.

The onboarding report remains read-only. Unknown provider authentication stays
unknown, missing or unreadable bootstrap evidence cannot become success, and live
mission acceptance remains pending. The optional process probe invokes systemd
readback only. Full native Hermes startup is a separate explicit action.

Hermes compatibility was checked against the repository's pinned release
`v2026.8.31`, commit `29112bef099274229cadff79cdff7bf7b99c4b77`; see the
[pinned upstream source](https://github.com/NousResearch/hermes-agent/tree/29112bef099274229cadff79cdff7bf7b99c4b77).
The release does not silently upgrade that dependency or substitute a new bot
protocol. Live platform support still requires its own upstream and account checks.

## Verification coverage

Regression coverage includes actual Bash stage-failure propagation with stubbed
system actions, lock and receipt corruption, descriptor-pinned Project creation
under rename/symlink attacks, actual DevOps compilation with a fake native profile
installer, partial-team recovery, bundle/Project collisions, full-team Doctor
failure/repair, selected Director argv, no-secret command reports and pure read-only
onboarding/metadata checks. These are source and temporary-filesystem tests.

Use repository Doctor, the security/unit/contract suites, shipped AGK tests and
factory checks before publishing. The disposable Ubuntu acceptance workflow and
the fresh-session bot mission are separate evidence; ordinary CI does not replace
them. Test results belong to the specific commit, not every future main checkout.

## Release and remaining decisions

Station 11.13 publishes beside 11.12. Changed bytes are never republished over the
same immutable release ID. OS package versions are unchanged; there is no automatic
migration/adoption of legacy profiles lacking this trusted installation ledger.

Still required before production or a broader autonomy claim:

- observe a clean supported VPS installation, its selected dependencies and actual
  native Hermes profile/gateway behavior;
- enroll the first Tailnet identity and human-owned bot, then prove inbound/outbound
  routing, authorization negatives, delegation, evidence and restart behavior;
- design explicit multi-Project OS instances if one OS must serve multiple Projects
  in the same Zone; do not silently share credentials or claim profile isolation;
- narrow broad operator sudo and implement complete runtime action/tool enforcement;
  same-Zone roles currently share one Unix authority;
- make guided setup explicitly profile-aware before claiming that Zone-base secret
  forms enroll every Director automatically;
- harden interrupted dependency repair without relocating Python virtualenvs whose
  scripts embed absolute paths; inspect surviving sudo children before retry;
- verify paid voice, each required connected account, tracing/memory data boundaries,
  disposable Strix LAB, production promotion and encrypted off-Host restore separately.

The goal is a clean, explainable Chief AI Officer foundation with truthful evidence,
not an assertion that installing packages makes an autonomous production system.
