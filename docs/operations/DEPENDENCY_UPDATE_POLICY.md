# Dependency update policy

`main` is the maintained branch. Dependency proposals do not authorize upgrades:
retain reviewed versions in `config/versions.lock`, package manifests/lockfiles,
and immutable GitHub Action SHA pins until a replacement passes review.

`.github/dependabot.yml` sets `open-pull-requests-limit: 0` for pip, both npm
directories, and GitHub Actions. This pauses automatic version-update PRs; it
does not disable Dependabot vulnerability alerts or the dependency graph.
Security-update PR automation is a separate repository setting, already reported
disabled by repository API readback on 2026-09-05; this change does not alter it.
If enabled later, security-update PRs can create branches independently of this
version-update limit. Keep security alerts under active manual review. See
[GitHub's Dependabot options reference](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#open-pull-requests-limit-).

## Manual integration

Review upstream changes, supported runtimes, integrity and transitive lockfile
changes before updating. Test candidates in an isolated local workspace; integrate
accepted changes manually on `main` only after the relevant tests pass. Keep Node
types aligned with the deployed Node major. Reconcile duplicate pins, run the
full applicable test/build gates, regenerate release metadata, and require
`./station doctor --repo` plus provenance checks before publishing. Changing CI
action pins also requires the affected artifact/attestation workflow readback;
ordinary unit-test success is not that evidence. Never auto-upgrade merely to
remove a proposal branch.

## Deferred proposals — 2026-09-05

These eight proposals are **deferred, not merged**. All had failing repository
verification on their historical CI bases; those failures alone do not prove an
upgrade incompatible with current `main`. TypeScript 7 additionally failed the
Node-contracts job. No candidate below has been accepted by this policy change.

| PR | Proposed version | Captured head SHA | Required review |
| --- | --- | --- | --- |
| [#2](https://github.com/agentik-os/agentik-station/pull/2) | upload-artifact 7.0.1 | `211c842d5a9fc1eec30b145ee68fe243325c61b1` | Preserve artifact behavior; verify affected workflows. |
| [#5](https://github.com/agentik-os/agentik-station/pull/5) | pytest 9.1.1 | `086a2bf0d7537162e094fe840bc14aa163d76392` | Suite/plugin compatibility and separate workflow pytest pins. |
| [#6](https://github.com/agentik-os/agentik-station/pull/6) | TypeScript 7.0.2 | `52ec9404aafe25ed306dcbcb51d9d5768a396cff` | Diagnose failing Node-contracts job before adoption. |
| [#7](https://github.com/agentik-os/agentik-station/pull/7) | jsonschema 4.26.0 | `29f59b2e6090fcc7f43105bf2d86feb4c29fda4d` | Rebase and verify schema/security contracts. |
| [#9](https://github.com/agentik-os/agentik-station/pull/9) | @types/node 26.4.1 | `6f9042fbd32cf142159df54172d36a30c56718df` | Node 26 types mismatch the deployed Node 24 runtime; retain compatible 24.x types. |
| [#10](https://github.com/agentik-os/agentik-station/pull/10) | attest-build-provenance 4.2.2 | `78b146f00d4fbecf17fbfa28d0b9418070ee0e3f` | Verify action inputs, permissions and attestation readback. |
| [#11](https://github.com/agentik-os/agentik-station/pull/11) | Vite 8.2.2 | `d7f98e38e256c37c42a1b7b8d19740bfdd68d4b9` | Coordinated Node 24 toolchain/typecheck/build validation. |
| [#12](https://github.com/agentik-os/agentik-station/pull/12) | Vitest 4.1.11 | `0c6d8c963e7ba9931b5fdc73c1871b572f086a97` | Coordinated test-runner and Vite compatibility validation. |

Archive status: **READ_BACK — all eight proposals archived and closed**.
The tag for each row is
`archive/dependency-proposals/2026-09-05/pr-N`, where `N` is the PR number.
On 2026-09-05 the operator reconciled each remote head against this table,
published all eight tags atomically and read back their exact SHAs before closing
the PRs. Subsequent GitHub PR readback confirmed all eight closed; remote ref
readback confirmed all eight tags retained and `main` as the only branch.
The removed proposal branches remain recoverable from these tags. Tags preserve
proposals, not merged code or upgrade acceptance.
