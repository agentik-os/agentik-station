# Bootstrap entrypoint

The preferred first install on a fresh Host is `bootstrap.sh`. It creates the dedicated `agk-station` sudo account, keeps the repository and user tools outside `/root`, installs the pinned operator toolchain and reviewed Hermes release, and then delegates to the typed Station kernel.

```bash
./bootstrap.sh --mode full --with-ai-stack --plan
# After reviewing the plan, choose ONE installation mode:
sudo ./bootstrap.sh --mode full
sudo ./bootstrap.sh --mode team --organization organization-alpha --project platform
sudo ./bootstrap.sh --mode full --with-ai-stack  # includes every optional AI component
```

Use the lower-level `station` / `install` commands below when you need explicit release engineering control.

## Fresh-VPS preflight and confirmation

`bootstrap.sh --plan` runs without sudo. It checks repository Doctor, supported
Linux/systemd/apt and CPU architecture, existing operator identity/home/group,
managed directory chains, the operator profile file, checkout conflicts and any
same-version immutable release content. It creates and removes a temporary
InstallSpec to print the typed kernel plan, followed by the selected dependency,
account and service operations. It does not run apt, create accounts, enroll a
Tailnet or install tools. A private existing target that the caller cannot inspect
causes a check failure; review it with an appropriately authorized operator rather
than loosening its permissions.

The actual bootstrap repeats validation and displays its plan before confirmation.
Within that invocation, **the exact reviewed JSON InstallSpec is passed to apply**.
The earlier `--plan` invocation is a preview, not a persisted approval artifact.
Account/tool/package work remains outside the typed kernel transaction and is
listed separately. Missing option values, invalid modes and unsupported Host
conditions fail before those mutations.

An existing nonempty operator checkout is not overwritten from another checkout.
Run from the preserved checkout after reviewing its state. Changed content cannot
be installed under an already published version—even if provenance text was left
unchanged. These early checks reduce accidental partial installation; they are
not a race-proof privileged reconciliation layer or a complete rollback mechanism.

`--sudo-mode password` uses the already authorized root bootstrap for kernel apply;
it does not require the new account to perform nested interactive sudo. The account
still needs a human-set password before later interactive sudo can work. The
default remains broad passwordless operator sudo; see `SECURITY.md` before use.

AGK-TUI never independently installs Hermes during bootstrap: the parent bootstrap
owns that lifecycle, including `--skip-hermes`. The weekly updater is enabled only
after selected dependency and setup stages succeed. When Tailnet enrollment is
missing, optional guided setup reports `LOCAL_BROKER_READY_TAILNET_NOT_READY`
instead of claiming a private URL; an explicit enable request still fails until
enrollment is complete. Loopback health is retried within a bounded startup window.

# Installation Contract

## Supported base for Station 11.20

The current safe-kernel provider supports:

- Ubuntu or Debian;
- a running systemd Host;
- `apt-get`;
- the distribution Python 3.11 or newer for the repository CLI;
- root for kernel apply, protected identity readback and Zone-scoped Project/OS/gateway operations; run coding agents as the non-root operator.

Bootstrap also installs Python 3.14.7 user-locally as `python-latest`, plus Python 3.13.15 as `python-ai` for isolated AI packages that do not yet guarantee 3.14 wheels. It does not replace the distribution Python. Hermes owns a separate Python 3.11 environment because `v2026.8.31` currently requires Python `>=3.11,<3.14`. The default install adds Hermes' `voice,messaging` extras, OpenAI audio defaults, and the digest-pinned loopback Parakeet service; `--skip-voice` deliberately omits that layer.

Other distributions and init systems are not silently approximated.

## Before applying

```bash
cd agentik-station
./station doctor --repo
./station plan --host-id station-core-01 --role core
```

`plan` must be reviewed before mutation. It compiles the same typed `InstallSpec` and canonical `config/station.default.json` used by `apply`.

## Core Host

```bash
sudo ./install \
  --host-id station-core-01 \
  --role core
```

A successful base install ends at:

```text
READY_FOR_SETUP
```

It creates the Station safe kernel and desired Zone declarations. It does not enroll external accounts or declare OS packages operational.

## Team / organization Host

```bash
./station plan \
  --host-id organization-alpha-prod-01 \
  --role team \
  --seed-category ORGANIZATIONS \
  --seed-name organization-alpha \
  --seed-env production \
  --seed-organization organization-alpha \
  --seed-project platform

sudo ./install \
  --host-id organization-alpha-prod-01 \
  --role team \
  --seed-category ORGANIZATIONS \
  --seed-name organization-alpha \
  --seed-env production \
  --seed-organization organization-alpha \
  --seed-project platform
```

This Host receives System Zones plus `organization-alpha/prod`. It does not receive Operator Private, Agentik Development, Factory, LAB, or unrelated organization Projects.

`--seed-project` is optional. The Organization owns the environment Zone, OS
instances and Projects; it is not itself a Project. After the foundation passes,
register the existing matching Zone and install a client-owned instance:

```bash
sudo station organization register --id organization-alpha --zone organization-alpha-prod --plan
sudo station organization register --id organization-alpha --zone organization-alpha-prod
sudo station os instance install --organization organization-alpha --zone organization-alpha-prod \
  --instance engineering --id devops-os
```

This is an installation example, not permission to run production missions.
Registration cannot relabel or create a Zone. Instance installation does not
require a Project; `--allow-project platform` declares an existing Project as
intended work scope, not a Unix ACL. Follow [SETUP.md](SETUP.md) before activation.

## Personal project Host

```bash
sudo ./install \
  --host-id example-project-prod-01 \
  --role project \
  --seed-category PROJECTS \
  --seed-name example-project \
  --seed-env production \
  --seed-organization operator \
  --seed-project app
```

## InstallSpec workflow

For automation and remote bootstrap, use a versioned JSON spec rather than reconstructing a command from values:

```json
{
  "schema_version": 1,
  "release_version": "11.20",
  "operation_id": "op-organization-alpha-prod-001",
  "host_id": "organization-alpha-prod-01",
  "role": "team",
  "install_system_packages": true,
  "configure_fail2ban": true,
  "enable_doctor_timer": true,
  "seed": {
    "category": "ORGANIZATIONS",
    "name": "organization-alpha",
    "environment": "production",
    "organization": "organization-alpha",
    "project": "platform"
  }
}
```

```bash
./station plan --spec ./install-spec.json
sudo ./install --spec ./install-spec.json
```

Unknown fields, malformed booleans, path syntax, shell syntax, invalid environments, and role/category mismatches are rejected.

## What apply performs

1. validates repository version and supported Host;
2. acquires a single Station operation lock;
3. records an operation receipt;
4. installs an allowlisted base package set when requested;
5. creates/audits the `station-system` identity;
6. reconciles the FHS layout and permissions;
7. stages, freezes, and activates an immutable Station release;
8. writes canonical desired Host state under `/etc/station`;
9. creates/audits Zone identities and roots;
10. creates Project roots with the correct Zone owner;
11. writes desired OS packages with `runtime_state: NOT_INSTALLED`;
12. installs canonical systemd units;
13. configures only the safe local security step currently implemented;
14. writes observed state and module readiness;
15. runs full Station Doctor;
16. records `READY_FOR_SETUP` and explicit next actions.

## Kernel failure behavior

A failed operation:

- records a failed receipt;
- records `DEGRADED` when possible;
- rolls back Station-owned filesystem mutations best-effort;
- does not pretend package manager changes or Unix-user creation were fully reversible;
- requires repair and a fresh plan/Doctor before another completion claim.

Receipts live under:

```text
/var/lib/station/receipts/<operation-id>.json
```

These transactional claims apply to the **kernel operation**, not the entire
shell bootstrap. A later dependency/setup failure can occur after a successful
kernel receipt. The outer bootstrap now holds a separate singleton lock and records
selected stages under `/var/lib/station/bootstrap/attempts/<attempt-id>.json`, with
a root-owned `latest.json` pointer. It preserves the exact InstallSpec, selected
options, source fingerprint, stage results and original exit code; it does not
record credentials or native tool output.

Read `sudo station setup --json` after a failure. If the kernel/launcher was not
installed yet, run `sudo python3 scripts/station_bootstrap_state.py report` from
the reviewed checkout. An incomplete attempt blocks a
new mutating run even with `--yes`. Inspect and repair the failed stage, check for
surviving installer processes, then explicitly acknowledge that attempt:

```bash
sudo ./bootstrap.sh --mode full --acknowledge-incomplete <attempt-id>
```

Repeat the same reviewed feature flags, such as `--with-ai-stack`, where intended.
This starts a **new full attempt**, not a resume or a rollback; the previous receipt
survives. A forcibly killed shell may leave children running, especially across
sudo descriptor boundaries. Never acknowledge an incomplete attempt without
inspecting the Host. The bootstrap lock and kernel lock have distinct scopes;
standalone dependency installers are not one global transaction with bootstrap.

Interrupted optional runtime builds still require supervised repair. Do not move
a Python virtual environment from a staging path to its final path or overwrite a
published runtime to make a retry pass. OS profile retries use the more specific
tracked lifecycle below; neither mechanism claims automatic all-stage rollback.

## Immutable releases

```text
/opt/station/releases/<version>/
/opt/station/current -> releases/<version>
/usr/local/bin/station -> /opt/station/current/station
```

A version cannot be overwritten with different content. Bump `VERSION` for changed release content.

Rollback switches only to an already installed immutable release:

```bash
sudo station release rollback --to <version>
station doctor --full
```

Runtime migrations and external-module compatibility still require their own verification; a symlink switch alone is not accepted recovery.

## Remote bootstrap transport

```bash
station host bootstrap \
  --target operator@organization-alpha-prod-01 \
  --id organization-alpha-prod-01 \
  --role team \
  --zone-category ORGANIZATIONS \
  --zone-name organization-alpha \
  --env production \
  --organization organization-alpha \
  --project platform \
  --plan
```

Strict host-key checking is the default. First-use enrollment requires the explicit `--accept-new-host-key` flag.

The transport sends:

- a normalized release archive;
- a separate validated JSON `InstallSpec`;
- fixed remote executable paths and arguments.

It never concatenates user values into a remote shell command. In 11.12 the bootstrap performs remote status + full Doctor readback and may report `REMOTE_READBACK_VERIFIED`; continuous drift/rollback and external integration acceptance remain separate Fleet gates.

## External installers

The safe kernel does not execute unattended network scripts as root. The explicit operator-invoked `bootstrap.sh` downloads upstream installers first, executes Hermes and Composio installers under `agk-station`, pins reviewed versions/commits, and checks published checksums or package-manager integrity where available. Authentication and live service enrollment remain separate setup gates.

The pinned default toolchain is installed under `/home/agk-station/.local`:

```text
Python latest stable + uv
Node.js LTS + npm
GitHub CLI
Vercel CLI
Codex CLI
Composio CLI
shadcn CLI
```

After those operator checks pass, bootstrap publishes an explicit **software-only**
allowlist into `/opt/station/tools/toolchain/<pin-set-id>/`. Root-owned launchers
in `/usr/local/bin` make Node/npm, Python aliases, gh, uv/uvx, Vercel, Codex and
shadcn available through each Zone's normal PATH. Complete Python runtimes are
relocated and checked, not symlinked through the operator's private home.
Published bytes are immutable; unexpected existing public launchers or changed
same-pin content require review. Failed candidates are retained for inspection
without switching public commands. No account files, private configuration or
operator HOME permissions are shared. Project dependencies and CLI login/cache
state remain under the calling Zone/Project, not in the shared software tree.

Bootstrap also installs at least the reviewed Tailscale stable version from its signed Ubuntu/Debian repository after verifying the archive-key checksum. It starts `tailscaled` but never invents a tailnet identity or authentication; the human owner completes `sudo tailscale up`, checks the device in the admin console, and then enables Station's private Serve path.

Hermes code lives at `/opt/station/tools/hermes/current` with a shared `/usr/local/bin/hermes` launcher. Its managed Python lives under `/opt/station/tools/hermes/python`, so a Zone does not need access to the operator's private home to execute it. Runtime state never lives there. Zone-base state remains at `/var/lib/station/zones/<zone-id>/hermes`; named instances use `/var/lib/station/zones/<zone-id>/os-instances/<instance>/hermes` under that Zone's UID.

Once the Host is enrolled in Tailscale, enable the private guided-setup path:

```bash
sudo ./scripts/station_guided_setup_enable.sh
```

Bootstrap already calls it in non-failing `--if-enrolled` mode. Without Tailscale it keeps the broker on loopback and reports the missing enrollment; it never opens a public substitute. See [`docs/dependencies/VOICE_AND_GUIDED_SETUP.md`](docs/dependencies/VOICE_AND_GUIDED_SETUP.md).

## Recommended Bash entry point

For the typed kernel only (not the full dependency bootstrap):

```bash
./station.sh bootstrap --mode full --host-id station-core-01
```

For a generic team Host:

```bash
./station.sh bootstrap \
  --mode team \
  --host-id organization-alpha-prod-01 \
  --organization organization-alpha \
  --env production \
  --project platform
```

`station.sh` always creates one versioned `InstallSpec` first and uses that exact spec for both plan and apply. It never reconstructs remote commands from unvalidated values and never bypasses the Station kernel. Use `--yes` only after the plan is already trusted in non-interactive automation.

## AGK-TUI

Bootstrap installs AGK-TUI for `agk-station` (skip with `--skip-agk-tui`).
Then: `agk` or `station tui` for live sessions. Bootstrap synchronizes redacted
metadata into `/home/agk-station/.agentik/station-sync.json`: root reads the
protected metadata and the unprivileged operator writes its own snapshot. A
missing or unreadable source is a reported failure, not an empty success. To
repeat that metadata-only handoff from the reviewed checkout:

```bash
set -o pipefail
sudo python3 -B scripts/station_agk_sync.py --export | \
  sudo -u agk-station -H python3 -B scripts/station_agk_sync.py --from-stdin
```

The snapshot does not enroll accounts or turn the legacy AGK client UI into the
canonical Organization/instance registry.


## Optional dependency stack + Hermes auto-update

After bootstrap (`READY_FOR_SETUP`):

```bash
./scripts/station_hermes_update.sh check
./scripts/station_hermes_update.sh update
sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update
station deps toolchain-check
./scripts/station_deps_install.sh --list
sudo ./scripts/station_deps_install.sh --all   # optional; installs/stages, then awaits configuration/readback
```

`station hermes update` requests an upstream backup, runs Hermes Doctor after a successful update, observes gateway status and writes a receipt under the owning `HERMES_HOME`. Bootstrap enables the weekly timer by default; pass `--skip-hermes-auto-update` to opt out. A failed update or Doctor returns non-zero with a repair action. The pinned Hermes CLI has no supported automatic state-restore command: preserve its native backup and review state/code recovery explicitly. Station does not claim that a backup was restored or that code compatibility was recovered.

Multi-platform bots are executed under the owning Zone identity:

```bash
sudo station platform setup --zone organization-alpha-dev --instance engineering --platform slack
sudo station platform install --zone organization-alpha-dev --instance engineering
sudo station platform status --zone organization-alpha-dev --instance engineering
```

See [`docs/dependencies/HERMES_PLATFORMS.md`](docs/dependencies/HERMES_PLATFORMS.md).

## Security assessment resource and post-audit migration

`sudo station deps install --component strix` installs the reviewed security CLI;
`--all` / `--with-ai-stack` includes it. No scan or Docker permission is automatic.
Use the [Strix guide](resources/strix/README.md) to enroll an isolated disposable
LAB and the existing Hermes DevOps mission team. Never grant its Docker access on
the core or a shared/production Host.

The September 5 audit corrected FHS parent traversal and OS compilation/publication.
Existing Hosts need the new release reconciled to generate root-owned Zone binding
projections, then OS profiles recompiled/reinstalled. Inspect preserved Hermes
configuration before enabling the generated plugin sections. Compiled distributions
now belong under `/opt/station/os-distributions`, not a Zone-writable Hermes parent.
Do not overwrite an already published same-version release: choose a new reviewed
release ID and retain the previous release/backup for rollback.

Station 11.20 publishes beside earlier releases; it never overwrites an old
immutable release. New schema-3 instance ledgers live under
`/var/lib/station/registry/os-instances/<zone>/<instance>.json`; compiled bundles
live under `/opt/station/os-instance-distributions/<zone>/<instance>/<os>/<version>/`.
The full `role_profile_map` names every native Director/specialist by Zone,
instance and role. Client runtime never enters reusable `os/` package source.

Instance commands do not automatically adopt or migrate legacy schema-2
Project-bound ledgers, Zone-owned receipts or untracked native profiles. Back up
and inspect the existing installation before designing migration. See
[the instance contract](docs/organization/05_OS_INSTANCES.md).

For **legacy schema-2 installations** tracked by their ledger, `station os install` can retry the
**same OS, version, Zone, Project and compiled bytes**: complete profiles are read
back and preserved; missing profiles are installed and checkpointed. An occupied
untracked name, partial profile, tombstone, changed bundle or different owning
Project is a repair/migration boundary. Native `--force` is never used.

Legacy `sudo station os verify --zone <zone-id> --id <os-id>` checks the entire expected
team and persists local Doctor evidence. Provider configuration changes make prior
verification stale; rerun verification after setup. A failed Doctor can be repaired
through `station os setup` and verified again without reinstalling the team.
Gateway startup remains blocked while that local OS record is degraded.

For full/core Zones with no Project yet, use `sudo station project create --zone <zone-id>
--id <project-id> --plan`, then the same command without `--plan`. This preview is
read-only but needs privileged access to protected local identity records.
Project creation reuses the canonical kernel layout/rules but does not reinstall
the Host, create a Unix account or restart services. Existing human/runtime Project
roots are refused, never overwritten. See the [first-mission sequence](docs/operations/06_FIRST_MISSION.md).

Fresh ScrapeGraphAI installs include verified tokenizer assets. For an older
published runtime missing those assets, inspect and archive that exact runtime,
then rebuild and pass `station deps web-check`. Paid extraction, voice messages,
chat/provider enrollment and Strix worker isolation still need live acceptance.
