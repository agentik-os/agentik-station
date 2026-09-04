# Bootstrap entrypoint

The preferred first install on a fresh Host is `bootstrap.sh`. It creates the dedicated `agk-station` sudo account, keeps the repository and user tools outside `/root`, installs the pinned operator toolchain and reviewed Hermes release, and then delegates to the typed Station kernel.

```bash
sudo ./bootstrap.sh --mode full
sudo ./bootstrap.sh --mode team --organization organization-alpha --project platform
sudo ./bootstrap.sh --mode full --with-ai-stack  # includes every optional AI component
```

Use the lower-level `station` / `install` commands below when you need explicit release engineering control.

# Installation Contract

## Supported base for Station 11.12

The current safe-kernel provider supports:

- Ubuntu or Debian;
- a running systemd Host;
- `apt-get`;
- the distribution Python 3.11 or newer for the repository CLI;
- root only for `station apply` / `./install`.

Bootstrap also installs Python 3.14.7 user-locally as `python-latest`, plus Python 3.13.15 as `python-ai` for isolated AI packages that do not yet guarantee 3.14 wheels. It does not replace the distribution Python. Hermes owns a separate Python 3.11 environment because `v2026.8.31` currently requires Python `>=3.11,<3.14`.

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
  "release_version": "11.12",
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

## Failure behavior

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

Hermes code lives at `/opt/station/tools/hermes/current` with a shared `/usr/local/bin/hermes` launcher. Runtime state never lives there: each Zone uses its own `/var/lib/station/zones/<zone-id>/hermes`.

## Recommended Bash entry point

The simplest supported workflow is:

```bash
./station.sh bootstrap --host-id station-core-01 --role core
```

For a generic team Host:

```bash
./station.sh bootstrap \
  --host-id organization-alpha-prod-01 \
  --role team \
  --seed-category ORGANIZATIONS \
  --seed-name organization-alpha \
  --seed-env production \
  --seed-organization organization-alpha \
  --seed-project platform
```

`station.sh` always creates one versioned `InstallSpec` first and uses that exact spec for both plan and apply. It never reconstructs remote commands from unvalidated values and never bypasses the Station kernel. Use `--yes` only after the plan is already trusted in non-interactive automation.

## AGK-TUI

Bootstrap installs AGK-TUI for `agk-station` (skip with `--skip-agk-tui`).
Then: `agk` or `station tui` for live sessions. Sync metadata: `~/.agentik/station-sync.json`.


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

`station hermes update` always requests an upstream backup, runs Hermes Doctor, observes gateway status and writes a receipt under the owning `HERMES_HOME`. Bootstrap enables the weekly timer by default; pass `--skip-hermes-auto-update` to opt out. A failed Doctor restores the pre-update Hermes state when upstream supports it and returns non-zero; code compatibility still requires operator review.

Multi-platform bots are executed under the owning Zone identity:

```bash
sudo station platform setup --zone organization-alpha-dev --platform slack
sudo station platform install --zone organization-alpha-dev
sudo station platform status --zone organization-alpha-dev
```

See [`docs/dependencies/HERMES_PLATFORMS.md`](docs/dependencies/HERMES_PLATFORMS.md).
