#!/usr/bin/env bash
# Update Hermes as the Station account with backup, Doctor and durable receipt.
set -Eeuo pipefail

STATION_USER="${STATION_USER:-agk-station}"
STATION_HOME="${STATION_HOME:-/home/${STATION_USER}}"
HERMES_HOME_VALUE="${HERMES_HOME:-$STATION_HOME/.hermes}"
MODE="${1:-update}" # check | update | auto
HERMES_BIN="${HERMES_BIN:-$STATION_HOME/.local/bin/hermes}"
RECEIPT_ROOT="${HERMES_UPDATE_RECEIPTS:-$HERMES_HOME_VALUE/station-update-receipts}"
HERMES_INSTALL_DIR="${HERMES_INSTALL_DIR:-/opt/station/tools/hermes/current}"

run_as_station() {
  if [[ "$(id -un)" == "$STATION_USER" ]]; then
    env HOME="$STATION_HOME" HERMES_HOME="$HERMES_HOME_VALUE" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  else
    sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" HERMES_HOME="$HERMES_HOME_VALUE" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  fi
}

probe_version() {
  local output
  # Failed probes may emit diagnostics, not a version. Keep those out of the
  # receipt; preserve their return code and only publish successful first lines.
  output="$(run_as_station "$HERMES_BIN" --version 2>/dev/null)" || return $?
  output="${output%%$'\n'*}"
  [[ -n "$output" ]] || return 2
  printf '%s' "$output"
}

if [[ ! -x "$HERMES_BIN" ]]; then
  fallback="$(command -v hermes || true)"
  [[ -n "$fallback" && -x "$fallback" ]] || {
    echo "ERROR: Hermes is not installed for $STATION_USER" >&2
    exit 2
  }
  HERMES_BIN="$fallback"
fi

case "$MODE" in
  check|update|auto) ;;
  *) echo "usage: $0 {check|update|auto}" >&2; exit 2;;
esac

run_as_station mkdir -p "$RECEIPT_ROOT"
timestamp="$(date -u +%Y%m%d-%H%M%S)"
work="$(mktemp -d)"
if [[ "$(id -u)" -eq 0 ]]; then
  chown "$STATION_USER:$(id -gn "$STATION_USER")" "$work"
fi
chmod 0700 "$work"
trap 'rm -r "$work"' EXIT
before_version_rc=0
after_version_rc=-1
before_version=""
after_version=""
if before_version="$(probe_version)"; then
  :
else
  before_version_rc=$?
fi
before_sha=""
install_repo="$HERMES_INSTALL_DIR"
if [[ -d "$install_repo/.git" ]]; then
  before_sha="$(run_as_station git -C "$install_repo" rev-parse HEAD 2>/dev/null || true)"
fi

status="CHECK_FAILED"
update_rc=0
doctor_rc=-1
gateway_rc=-1
rollback_rc=-1
next_repair_action=""

if [[ "$before_version_rc" -ne 0 ]]; then
  status="VERSION_PROBE_FAILED"
  update_rc=-1
  next_repair_action="Repair the Hermes --version probe before retrying; no update was attempted."
elif [[ "$MODE" == "check" ]]; then
  if run_as_station "$HERMES_BIN" update --check >"$work/update.log" 2>&1; then
    status="CHECKED_NOT_APPLIED"
  else
    update_rc=$?
    next_repair_action="Inspect the native Hermes update check log and repair upstream access before retrying."
  fi
else
  if run_as_station "$HERMES_BIN" update --backup --yes >"$work/update.log" 2>&1; then
    status="UPDATED_UNVERIFIED"
    if run_as_station "$HERMES_BIN" doctor >"$work/doctor.log" 2>&1; then
      doctor_rc=0
      status="VERIFIED_UPDATED"
    else
      doctor_rc=$?
      status="DEGRADED_DOCTOR_FAILED"
      # The pinned CLI can create backups but exposes no supported restore
      # command. State recovery and code compatibility require reviewed repair.
      next_repair_action="Inspect the native Hermes backup and review state and code recovery; no automatic restore was attempted."
    fi
  else
    update_rc=$?
    status="UPDATE_FAILED"
    next_repair_action="Inspect the native Hermes update log and available backups; review state and code recovery before retrying."
  fi
  if run_as_station "$HERMES_BIN" gateway status >"$work/gateway.log" 2>&1; then
    gateway_rc=0
  else
    gateway_rc=$?
    if [[ "$status" == "VERIFIED_UPDATED" ]]; then
      status="DEGRADED_GATEWAY_FAILED"
      next_repair_action="Inspect the owning Hermes gateway and restore its expected service configuration before accepting the update."
    fi
  fi
fi

if [[ "$before_version_rc" -eq 0 ]]; then
  if after_version="$(probe_version)"; then
    after_version_rc=0
  else
    after_version_rc=$?
    case "$status" in
      CHECKED_NOT_APPLIED|VERIFIED_UPDATED) status="VERSION_READBACK_FAILED";;
    esac
    if [[ -n "$next_repair_action" ]]; then
      next_repair_action+=" "
    fi
    next_repair_action+="Repair Hermes --version readback and review the recorded update result before retrying."
  fi
fi
after_sha=""
if [[ -d "$install_repo/.git" ]]; then
  after_sha="$(run_as_station git -C "$install_repo" rev-parse HEAD 2>/dev/null || true)"
fi

for name in update doctor gateway rollback; do
  [[ -f "$work/$name.log" ]] || : >"$work/$name.log"
done

receipt="$RECEIPT_ROOT/${timestamp}-${MODE}.json"
jq -n \
  --arg schema_version "1" --arg checked_at "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg mode "$MODE" --arg status "$status" \
  --arg next_repair_action "$next_repair_action" \
  --arg before_version "$before_version" --arg after_version "$after_version" \
  --arg before_sha "$before_sha" --arg after_sha "$after_sha" \
  --argjson update_rc "$update_rc" --argjson doctor_rc "$doctor_rc" \
  --argjson gateway_rc "$gateway_rc" --argjson rollback_rc "$rollback_rc" \
  --argjson before_version_rc "$before_version_rc" --argjson after_version_rc "$after_version_rc" \
  --rawfile update_log "$work/update.log" --rawfile doctor_log "$work/doctor.log" \
  --rawfile gateway_log "$work/gateway.log" --rawfile rollback_log "$work/rollback.log" \
  '{schema_version:($schema_version|tonumber),checked_at:$checked_at,mode:$mode,status:$status,next_repair_action:$next_repair_action,before:{version:$before_version,commit:$before_sha},after:{version:$after_version,commit:$after_sha},returncodes:{update:$update_rc,doctor:$doctor_rc,gateway:$gateway_rc,rollback:$rollback_rc,before_version:$before_version_rc,after_version:$after_version_rc},logs:{update:$update_log,doctor:$doctor_log,gateway:$gateway_log,rollback:$rollback_log},operational_claim:false}' \
  >"$work/receipt.json"
if [[ "$(id -u)" -eq 0 ]]; then
  chown "$STATION_USER:$(id -gn "$STATION_USER")" "$work/receipt.json"
fi
chmod 0600 "$work/receipt.json"
run_as_station install -m 0600 "$work/receipt.json" "$receipt"
run_as_station ln -sfn "$(basename "$receipt")" "$RECEIPT_ROOT/latest.json"

cat "$work/update.log"
[[ -s "$work/doctor.log" ]] && cat "$work/doctor.log"
echo "HERMES_UPDATE_STATUS=$status"
if [[ -n "$next_repair_action" ]]; then
  echo "NEXT_REPAIR_ACTION=$next_repair_action"
fi
echo "RECEIPT=$receipt"

case "$status" in
  CHECKED_NOT_APPLIED|VERIFIED_UPDATED) exit 0;;
  *) exit 1;;
esac
