#!/usr/bin/env bash
# Update Hermes to latest on the Station account (non-root). Opt-in auto-update target.
set -Eeuo pipefail

STATION_USER="${STATION_USER:-agk-station}"
STATION_HOME="${STATION_HOME:-/home/${STATION_USER}}"
MODE="${1:-update}"  # check | update | backup-update

run_as_station() {
  if [[ "$(id -un)" == "$STATION_USER" ]]; then
    env HOME="$STATION_HOME" HERMES_HOME="${HERMES_HOME:-$STATION_HOME/.hermes}" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  else
    sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" \
      HERMES_HOME="${HERMES_HOME:-$STATION_HOME/.hermes}" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  fi
}

command -v hermes >/dev/null 2>&1 || run_as_station bash -lc 'command -v hermes' >/dev/null \
  || { echo "ERROR: hermes not on PATH for ${STATION_USER}. Run bootstrap or hermes install first." >&2; exit 2; }

case "$MODE" in
  check)
    run_as_station bash -lc 'hermes update --check'
    ;;
  update)
    # Prefer non-interactive where Hermes supports it; still operator-owned.
    run_as_station bash -lc 'hermes update'
    run_as_station bash -lc 'hermes doctor' || true
    ;;
  backup-update)
    run_as_station bash -lc 'hermes update --backup'
    run_as_station bash -lc 'hermes doctor' || true
    ;;
  *)
    echo "usage: $0 {check|update|backup-update}" >&2
    exit 2
    ;;
esac

# Refresh bootstrap-tools.json hermes field when root can write /etc/station
if [[ -d /etc/station ]] && [[ "$(id -u)" -eq 0 || -w /etc/station/bootstrap-tools.json ]]; then
  hermes_version="$(run_as_station bash -lc 'hermes --version 2>/dev/null || true' | head -1)"
  if [[ -f /etc/station/bootstrap-tools.json ]] && command -v jq >/dev/null; then
    tmp="$(mktemp)"
    jq --arg hermes "$hermes_version" --arg updated "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
      '.hermes=$hermes | .hermes_updated_at=$updated' \
      /etc/station/bootstrap-tools.json > "$tmp" \
      && mv "$tmp" /etc/station/bootstrap-tools.json
  fi
fi
