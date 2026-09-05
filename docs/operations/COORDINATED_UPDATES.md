# Coordinated Station updates

Station updates a **reviewed set**, not unrelated `latest` versions. Hermes,
its Python ABI/native memory clients, Station plugins, web workers and their
browsers, server images, npm clients and platform services have compatibility
dependencies. A newer upstream release is a proposal, not proof that the set works.

## Inspect the whole set

```bash
station update plan          # all delivered SBOM components and lock pins; offline
station update check         # public GitHub/npm/PyPI metadata; no installation
station hermes check         # no native Hermes command or real-profile import
sudo station status --software
```

Each source remains visible if metadata is unavailable, no release is published,
or manual review is required. OCI digests, Python/Node tracks and unsupported
metadata endpoints are explicit review gates, not silently updated or dropped.
Commit-pinned repositories (including AGK TUI and Honcho) also track the public
default-branch commit when no release pin is used. Such an observation is labelled
as a commit candidate, never as a stable release or an accepted upgrade. Client
SDK/CLI versions and application server versions are compared independently.
`check` exits successfully when supported metadata requests complete (including
an explicit upstream 404/no release); network or malformed-response failures
return nonzero. `collection_succeeded` is distinct from `discovery_complete`:
manual source/image reviews can remain incomplete after a successful collection.
Neither field means that an upgrade is compatible or installed.
Git checkouts and non-Git Hermes source distributions can both be inspected.
Without verifiable source identity, the latter reports unknown provenance;
Station does not invent a commit from its own desired pin.

The weekly Host timer now performs this **coupled discovery only**. It no longer
pulls a new Hermes HEAD into a working installation. The existing timer name and
`--skip-hermes-auto-update` opt-out are retained for compatibility. The dedicated
Hermes watcher stays read-only. `station hermes update` now requests a coordinated
release instead of independently changing Hermes; `--check-only` remains a
read-only compatibility alias. Old direct shell helper modes are legacy recovery
tools, not the supported coupled deployment workflow.

A weekly GitHub workflow also uploads the complete candidate report. It has
read-only repository permission: no PR branches, forced pushes, package publish,
dependency file changes or automatic merges. `main` remains the sole maintained
branch. The report explicitly distinguishes discovery from acceptance.

## npm: update the runtime, not only the installer package

Updating the npm package alone does **not** change an existing Station runtime.
After an authorized npm release is actually published, install that exact reviewed
package version, then use its update workflow:

```bash
# Substitute an actually published, reviewed version; no publish is implied here.
npm install --global @agentik-os/station@<reviewed-version>
agentik-station update-plan --root "$HOME/station" --json
agentik-station update --root "$HOME/station" --yes
agentik-station verify --root "$HOME/station"
```

Fresh installations from 11.29 record a private verified software baseline.
Update refuses modified/added software, missing baselines, downgrades and
same-release pin changes. **11.26–11.28 Workstations lack that baseline and require
a reviewed legacy migration; they are not silently adopted.** No npm registry
publication or account ownership is inferred from source/pack tests.

Before mutation, stop/remove only the owning gateway's service binding and close
the owning RMUX sessions/daemon. Update refuses an existing definition, loaded
service, ambiguous service-manager response or private endpoint; it does not
stop unrelated services or infer permission to restart a bot.

The migration preserves `projects/` and personal account/configuration files.
It moves seven fixed software trees into a private transaction backup and
rebuilds their replacements at their **final paths**. Virtual environments are
not relocated after construction. The existing profile name and enrollment are
retained; plugin-enable/config-sync steps are not repeated. Native verification
and protected-state comparison must pass before the new baseline is committed.

On ordinary failure, Station attempts automatic software restoration; failed
candidates and the transaction record remain under `evidence/update-<id>/`.
If restoration or its verification fails, the pending journal and retained
software/evidence require reviewed recovery; no successful recovery is reported.
Unknown concurrent
account edits are never overwritten as part of software recovery. A killed
process leaves a pending journal and blocks repair/enrollment/activation:

```bash
# Inspect the journal and ensure the owning runtime is inactive first.
agentik-station update-recover --root "$HOME/station" --yes
```

Recovery can archive a lock only after its recorded owner is proved dead. A
same-UID process whose command line contains this Station root blocks recovery;
no process is killed automatically. This check does not prove absence of
processes referring to the root only through their cwd, environment or open
files: inspect residual installer activity after interruption before recovery.
Saved
lock records remain in private evidence. Ambiguous or living lock owners are
refused, not cleared by a timeout.
Concurrent recovery requests are serialized by a separate recovery guard. If
that guard itself is interrupted, it is retained for explicit owner/evidence
inspection; the CLI does not recursively clear it. Recovery validates the entire
predecessor baseline before moving software and only republishes it after the
restored inventory matches.

This is software recovery, not a database/account rollback. As with Workstation
itself, the mechanism is a same-UID namespace, not a sandbox against another
process using that UID. Shared-client isolation still requires a Linux Host Zone.

## Host rollout and adaptation gates

Review candidate sources/licenses/security, update coupled pins and adapters,
reconcile transitive lockfiles and image digests, run unit/security/contract
tests, and accept a native LAB/canary installation. Review persistence and
database migrations separately; a passing import cannot accept a schema change.
Publish a **new immutable Station release** on main. Preserve the Host's typed
InstallSpec when applying the kernel; repair changed software components from
that immutable release and rerun `status --software`. Existing service-software
receipt/digest conflicts require a reviewed migration, not silent adoption.

No generic installer can guarantee compatibility with all future upstream
changes. This workflow makes their detection and required adaptation visible;
it does not claim automatic database migration, OS-profile migration or fully
unattended fleet promotion. Live client/provider/chat acceptance remains scoped
to its owning identity. Ponytail's security block cannot be cleared by changing
a version number or disabling an upstream scanner.
