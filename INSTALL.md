# Installation Contract

## Supported base for v11

The current safe-kernel provider supports:

- Ubuntu or Debian;
- a running systemd Host;
- `apt-get`;
- Python 3.11 or newer for the repository CLI;
- root only for `station apply` / `./install`.

Other distributions and init systems are not silently approximated.

## Before applying

```bash
cd agentik-station
./station doctor --repo
./station plan --host-id gareth-core-01 --role core
```

`plan` must be reviewed before mutation. It compiles the same typed `InstallSpec` and canonical `config/station.default.json` used by `apply`.

## Core Host

```bash
sudo ./install \
  --host-id gareth-core-01 \
  --role core
```

A successful base install ends at:

```text
READY_FOR_SETUP
```

It creates the Station safe kernel and desired Zone declarations. It does not enroll external accounts or declare OS packages operational.

## Client production Host

```bash
./station plan \
  --host-id moonbase-prod-01 \
  --role client \
  --seed-category CLIENTS \
  --seed-name moonbase \
  --seed-env production \
  --seed-organization moonbase \
  --seed-project platform

sudo ./install \
  --host-id moonbase-prod-01 \
  --role client \
  --seed-category CLIENTS \
  --seed-name moonbase \
  --seed-env production \
  --seed-organization moonbase \
  --seed-project platform
```

This Host receives System Zones plus `moonbase/prod`. It does not receive Gareth Private, Agentik Development, Factory, LAB, or unrelated client Projects.

## Personal project Host

```bash
sudo ./install \
  --host-id verba-prod-01 \
  --role project \
  --seed-category PROJECTS \
  --seed-name verba \
  --seed-env production \
  --seed-organization gareth \
  --seed-project app
```

## InstallSpec workflow

For automation and remote bootstrap, use a versioned JSON spec rather than reconstructing a command from values:

```json
{
  "schema_version": 1,
  "release_version": "0.2.0-alpha.11",
  "operation_id": "op-moonbase-prod-001",
  "host_id": "moonbase-prod-01",
  "role": "client",
  "install_system_packages": true,
  "configure_fail2ban": true,
  "enable_doctor_timer": true,
  "seed": {
    "category": "CLIENTS",
    "name": "moonbase",
    "environment": "production",
    "organization": "moonbase",
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
  --target operator@moonbase-prod-01 \
  --id moonbase-prod-01 \
  --role client \
  --zone-category CLIENTS \
  --zone-name moonbase \
  --env production \
  --organization moonbase \
  --project platform \
  --plan
```

Strict host-key checking is the default. First-use enrollment requires the explicit `--accept-new-host-key` flag.

The transport sends:

- a normalized release archive;
- a separate validated JSON `InstallSpec`;
- fixed remote executable paths and arguments.

It never concatenates user values into a remote shell command. In v11 it remains a bootstrap transport; it reports execution but does not claim Fleet verification or acceptance.

## External installers

The safe kernel does not execute unattended network scripts as root. Tailscale, Hermes, Composio, and other external modules are enrolled in the separate setup phase with explicit provenance, policy, and readback gates.
