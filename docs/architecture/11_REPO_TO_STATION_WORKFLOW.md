# Repository → Station workflow

## Objective

One repository must be enough for an AI coding agent to reproduce the Station foundation on a fresh Linux Host.

```text
Fresh VPS
  ↓
Coding agent installed by operator
  ↓
Clone Station repository
  ↓
Read AGENTS + Architecture + Install
  ↓
station plan
  ↓
install
  ↓
Linux foundation
  ↓
Station Control
  ↓
Base Zones for Host role
  ↓
Hermes + Composio + host dependencies
  ↓
Systemd services/timers
  ↓
OS package library
  ↓
Doctor
  ↓
READY_FOR_SETUP
```

## Why setup is separate

The repository can install software and policies, but it must not embed:

- model/provider API secrets;
- Discord bot tokens;
- OAuth consent;
- Composio connected accounts;
- organization production credentials;
- GitHub private credentials;
- Tailscale enrollment credentials.

Those are enrolled after installation against explicit Zone/Project identities.

## Root files are authoritative

An installer agent reads, in order:

1. `AGENTS.md`
2. `README.md`
3. `ARCHITECTURE.md`
4. `INSTALL.md`
5. `AI_INSTALL_PROMPT.md`
6. `config/station.yaml`

Historical documents never override these files.

## Core Host

```bash
sudo ./install --host-id station-core-01 --role core
```

This creates System, Private, Agentik, Factory and Lab base Zones.

## Remote team Host

```bash
sudo ./install \
  --host-id organization-alpha-prod-01 \
  --role team \
  --seed-category ORGANIZATIONS \
  --seed-name organization-alpha \
  --seed-env production \
  --seed-organization organization-alpha \
  --seed-project platform
```

This does not install Operator Private, Agentik Development or OS Factory Zones.

## Remote personal project Host

```bash
sudo ./install \
  --host-id example-project-prod-01 \
  --role project \
  --seed-category PROJECTS \
  --seed-name example-project \
  --seed-env production \
  --seed-organization operator \
  --seed-project example-project
```

## Desired state and idempotence

Repeated installation reconciles the same known directories/users/packages instead of creating alternate structures. Host-specific setup values live under `/etc/station`; operational data lives under `/srv/station`; repository software lives under `/opt/station/repo`.

## Completion claim

Successful package installation means `READY_FOR_SETUP`, not `OPERATIONAL`.

`OPERATIONAL` requires external integration enrollment, Doctor/readback, Discord provisioning where applicable, and fresh-session acceptance.
