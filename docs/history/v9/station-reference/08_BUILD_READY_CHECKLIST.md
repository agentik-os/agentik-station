# Build-Ready Checklist

## Host
- [ ] fresh supported Linux image
- [ ] `station-admin` sudo account
- [ ] SSH key auth / hardened SSH
- [ ] Tailscale/private admin path
- [ ] firewall and fail2ban or equivalent
- [ ] time sync, disk monitoring, log rotation

## Trust zones
- [ ] system users/homes created
- [ ] separate HERMES_HOME per zone
- [ ] separate data/secret namespaces
- [ ] LAB contains no production credentials
- [ ] project containers/volumes created from descriptors

## Hermes
- [ ] LAB/edge checkout installed first
- [ ] Hermes smoke test + `hermes doctor`
- [ ] managed security baseline configured
- [ ] Station policy hooks tested with `hermes hooks doctor`
- [ ] stable commit pinned in Station lockfile
- [ ] updater watchdog timer enabled

## Core OSs
- [ ] Station Maintainer
- [ ] Discord Bootstrap
- [ ] Builder
- [ ] Librarian
- [ ] DevOps + Ponytail
- [ ] every OS contract/doctor passes

## Discord
- [ ] bootstrap app authorized temporarily for provisioning
- [ ] desired server structure plan reviewed/applied
- [ ] dedicated Nano Director bot credential enrolled for every canonical OS
- [ ] bot/channel/command readback passes
- [ ] bootstrap Administrator removed

## Recovery
- [ ] offsite encrypted backup target configured
- [ ] Station desired state stored in Git
- [ ] secrets externally recoverable
- [ ] restore drill passes on disposable environment

## Final
- [ ] `python3 programs/station_cli.py doctor-pack`
- [ ] canonical E2E mission
- [ ] fresh-session acceptance
- [ ] Station version/evidence receipt produced


## OS v2 / Composio
- [ ] OS v2 contract schema is the Builder default.
- [ ] Composio CLI adapter is available where required.
- [ ] No production Composio subject uses `default` or email as primary identity.
- [ ] Personal/company/client connected-account scopes are separate.
- [ ] Trigger routes enter through Station policy before Mission/Kanban.
- [ ] Critical external actions pass fresh-session acceptance.
