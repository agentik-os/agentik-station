#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATION="$ROOT/station"

usage() {
  cat <<'USAGE'
Agentik Station orchestration wrapper

Primary workflows:
  ./station.sh bootstrap --mode full [--host-id station-core-01] [--yes]
  ./station.sh bootstrap --mode team --organization ORG --project PROJECT [--env development] [--yes]
  ./station.sh plan ...
  ./station.sh spec ... [--output PATH]
  ./station.sh doctor
  ./station.sh status
  ./station.sh setup

Modes:
  full  Full operator/Agentik Station (Host role core).
  team  Organization/team Station (Host role team, no Station-wide Private Zone).

The wrapper always creates one typed InstallSpec, shows the exact plan, then applies that same spec.
USAGE
}

require_station(){ [[ -x "$STATION" ]] || { echo "ERROR: missing $STATION" >&2; exit 2; }; }

build_desired(){
  local mode="full" host="" org="" project="" env="development"
  local -a passthrough=()
  # The caller owns this dynamically scoped array. Do not consume this function
  # through process substitution: that discards validation failures.
  desired=()
  while (($#)); do
    case "$1" in
      --mode|--host-id|--organization|--project|--env)
        [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || {
          echo "ERROR: $1 requires a value." >&2; return 2;
        };;
    esac
    case "$1" in
      --mode) mode="$2"; shift 2;;
      --host-id) host="$2"; shift 2;;
      --organization) org="$2"; shift 2;;
      --project) project="$2"; shift 2;;
      --env) env="$2"; shift 2;;
      *) passthrough+=("$1"); shift;;
    esac
  done
  case "$mode" in
    full)
      [[ -z "$org" && -z "$project" && "$env" == development ]] || {
        echo 'ERROR: organization/project/environment options require --mode team.' >&2; return 2;
      }
      desired=(--host-id "${host:-station-core-01}" --role core)
      ((${#passthrough[@]} == 0)) || desired+=("${passthrough[@]}")
      ;;
    team)
      [[ -n "$org" ]] || { echo "ERROR: --organization is required for --mode team" >&2; return 2; }
      desired=(--host-id "${host:-${org}-station-01}" --role team --seed-category ORGANIZATIONS --seed-name "$org" --seed-env "$env" --seed-organization "$org")
      [[ -z "$project" ]] || desired+=(--seed-project "$project")
      ((${#passthrough[@]} == 0)) || desired+=("${passthrough[@]}")
      ;;
    *) echo "ERROR: --mode must be full or team" >&2; return 2;;
  esac
}

bootstrap()(
  local yes=0; local -a raw=()
  while (($#)); do case "$1" in --yes) yes=1; shift;; -h|--help) usage; return 0;; *) raw+=("$1"); shift;; esac; done
  require_station
  local -a desired=(); build_desired ${raw[@]+"${raw[@]}"} || return $?
  "$STATION" doctor --repo --full
  local tmpdir spec; tmpdir="$(mktemp -d "${TMPDIR:-/tmp}/agentik-station-bootstrap.XXXXXX")"; spec="$tmpdir/install-spec.json"
  trap 'rm -f -- "$spec"; rmdir -- "$tmpdir"' EXIT
  "$STATION" spec "${desired[@]}" --output "$spec" >/dev/null
  echo '==> Plan • not run'; "$STATION" plan --spec "$spec"
  if [[ "$yes" -ne 1 ]]; then
    [[ -t 0 ]] || { echo 'ERROR: non-interactive bootstrap requires --yes.' >&2; return 2; }
    read -r -p 'Apply this exact plan with sudo? [y/N] ' answer
    [[ "$answer" =~ ^([yY]|yes|YES)$ ]] || { echo 'Cancelled. Nothing applied.'; return 0; }
  fi
  sudo "$STATION" apply --spec "$spec"
  sudo "$STATION" doctor --full --record
  "$STATION" status || true
  "$STATION" setup
)

main(){
  require_station
  local cmd="${1:-help}"; shift || true
  case "$cmd" in
    bootstrap) bootstrap "$@";;
    plan|spec)
      local -a desired=(); build_desired "$@" || return $?
      if [[ "$cmd" == plan ]]; then "$STATION" doctor --repo --full || return $?; fi
      "$STATION" "$cmd" "${desired[@]}";;
    doctor) "$STATION" doctor --repo --full; [[ ! -e /etc/station/station.json ]] || sudo "$STATION" doctor --full;;
    status) "$STATION" status "$@";;
    setup) "$STATION" setup "$@";;
    help|-h|--help) usage;;
    *) exec "$STATION" "$cmd" "$@";;
  esac
}
main "$@"
