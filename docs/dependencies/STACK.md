# Station dependency stack

Declarative optional stack for Agentik Station 11.12+.

Pinned Hermes release: see `config/versions.lock` (`HERMES_RELEASE`).
Declared components: `config/deps/stack.yaml`.

## Install

```bash
# List
./scripts/station_deps_install.sh --list

# Optional components (operator-owned; not OPERATIONAL by install alone)
sudo ./scripts/station_deps_install.sh --component tigervnc
sudo -u agk-station -H ./scripts/station_deps_install.sh --component crawl4ai
sudo -u agk-station -H ./scripts/station_deps_install.sh --component ponytail
sudo -u agk-station -H ./scripts/station_deps_install.sh --component langfuse
sudo -u agk-station -H ./scripts/station_deps_install.sh --component honcho
sudo -u agk-station -H ./scripts/station_deps_install.sh --component hindsight

# Or all scaffolded installs
sudo ./scripts/station_deps_install.sh --all
```

## Hermes latest + auto-update

```bash
# Check / apply (as root or agk-station)
./scripts/station_hermes_update.sh check
./scripts/station_hermes_update.sh update

# Opt-in weekly timer
sudo ./scripts/station_deps_install.sh --enable-hermes-auto-update
```

Upstream: `hermes update` tracks `main` with rollback on broken pulls.
Docs: https://hermes-agent.nousresearch.com/docs/getting-started/updating

## Maturity

Install leaves modules at **SCAFFOLDED** / **INSTALLABLE**. Do not claim OPERATIONAL until Doctor + readback for that component.
