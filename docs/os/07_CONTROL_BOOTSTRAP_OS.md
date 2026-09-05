# Control / Bootstrap OS

This is a **system OS package**, not a normal marketplace business OS or a
preauthenticated administrator. Its definition describes an intended team and
workflow; installation, credentials and accepted capabilities are separate facts.

## Purpose

Own installation finalization and organization cockpit reconciliation.

## Director

```text
discord-bootstrap-director
```

This is the canonical role, not a native profile name to guess. An installed
instance maps it to its own profile in the root-owned `role_profile_map` ledger.
Instances and Projects are siblings inside their owning Zone; this system OS
does not need to live inside a Project.

## Responsibilities

```text
read organization desired state
read installed OS surface manifests
inspect Discord guild
plan safe reconciliation
apply allowed changes
bind Discord IDs to teams/profiles/projects/boards
verify routing
remove bootstrap Administrator privilege
emit evidence
```

## Runtime mode

Declaring `requested_os: discord-bootstrap-os` for the System Zone does not
install the OS. Until there is an explicit installation record and native
readback, the package remains desired / `NOT_INSTALLED`.

For a deliberately separate control instance in an already reconciled
`discord-bootstrap` Zone:

```bash
sudo station setup --zone discord-bootstrap --instance control --json
sudo station os instance install --zone discord-bootstrap --instance control --id discord-bootstrap-os
sudo station os instance show --zone discord-bootstrap --instance control
sudo station os instance setup --zone discord-bootstrap --instance control --plan
sudo station os instance setup --zone discord-bootstrap --instance control
sudo station platform setup --zone discord-bootstrap --instance control --platform discord --plan
sudo station platform setup --zone discord-bootstrap --instance control --platform discord
```

The first command is a read-only setup report, not an installation dry run;
`os instance install` has no `--plan` flag. The install command creates the native
team; it does not enroll a provider,
create a Discord application or grant its Director Administrator or Linux sudo.
A human owns the bot identity and enters its token only in the masked native
wizard. Configure explicit human and channel allowlists, decline the wizard's
early service-start/install/restart offers, then follow the
[verify → install → start → live acceptance sequence](../dependencies/HERMES_PLATFORMS.md)
with `--zone discord-bootstrap --instance control`.

By contrast, `station platform setup --zone discord-bootstrap --platform discord`
without `--instance` selects that Zone's explicit **default** profile. It does
not install this package or select `discord-bootstrap-director`. A business
instance such as `dev / engineering` has its own Director, Atlas, and its own
onboarding route; connecting that bot does not require this control instance.

An existing token in the Zone-base `hermes/.env` belongs to that existing default
route. Keep it there; do not move it into `control` or Atlas or run a second
gateway with the same token. The
[existing first-bot walkthrough](../dependencies/HERMES_PLATFORMS.md#keep-the-existing-first-station-bot-in-discord-bootstrap--default)
configures that exact Zone-base provider and gateway without pretending this
system OS instance was installed.

Once explicitly installed, configured and accepted, the control instance may
serve the following approved purposes:

- drift detection
- explicit reconciliation
- adding new OS surfaces
- organization migrations

The responsibilities above are not proof that every provisioning workflow is
implemented or externally accepted. Privileged changes require an authorized
maintenance window and a concrete scoped capability; a role name, prompt or bot
token does not grant one. Any temporary Discord elevation must be removed by
the human server owner and verified before normal runtime acceptance.

## Not allowed

It is not allowed to:

- become a generic root shell agent
- inspect unrelated client Hosts or Zones
- access arbitrary business data
- retain permanent Discord Administrator simply for convenience
- create or copy credentials for other instances without explicit enrollment
