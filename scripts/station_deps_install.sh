#!/usr/bin/env bash
# Required full Host dependency installer; independent failures are aggregated.
# Does NOT claim OPERATIONAL. Installation remains below VERIFIED until Doctor/readback.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
STATION_USER="${STATION_USER:-agk-station}"
STATION_HOME="${STATION_HOME:-/home/${STATION_USER}}"
STACK="$ROOT/config/deps/stack.yaml"
LOCK="$ROOT/config/versions.lock"
# shellcheck disable=SC1090
source "$LOCK"

usage() {
  cat <<'USAGE'
usage: station_deps_install.sh [--all] [--list]
       station_deps_install.sh --component ID [--component ID ...]
       station_deps_install.sh --enable-hermes-auto-update
       station_deps_install.sh --platforms-guide
       station_deps_install.sh --check-web
       station_deps_install.sh --check-hermes-clients|--check-memory|--check-strix|--check-voice

Components: toolchain hermes-clients hermes-voice hermes-updater strix scrapegraphai ponytail langfuse honcho hindsight tigervnc crawl4ai parakeet chatbotx
USAGE
}

COMPONENTS=()
ENABLE_AUTO=0
LIST_ONLY=0
PLATFORMS=0
ALL=0
CHECK_WEB=0
PROBE=""
PROBE_COUNT=0

while (($#)); do
  case "$1" in
    --all) ALL=1; shift;;
    --check-web) CHECK_WEB=1; shift;;
    --check-hermes-clients) PROBE=hermes-clients; PROBE_COUNT=$((PROBE_COUNT + 1)); shift;;
    --check-memory) PROBE=memory; PROBE_COUNT=$((PROBE_COUNT + 1)); shift;;
    --check-strix) PROBE=strix; PROBE_COUNT=$((PROBE_COUNT + 1)); shift;;
    --check-voice) PROBE=voice; PROBE_COUNT=$((PROBE_COUNT + 1)); shift;;
    --list) LIST_ONLY=1; shift;;
    --component) [[ $# -ge 2 && "$2" != --* ]] || { usage >&2; exit 2; }; COMPONENTS+=("$2"); shift 2;;
    --enable-hermes-auto-update) ENABLE_AUTO=1; shift;;
    --platforms-guide) PLATFORMS=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "unknown: $1" >&2; usage; exit 2;;
  esac
done

# Reject invalid selections before any action (including timer installation),
# and never silently discard a misspelled component supplied alongside --all.
if [[ "$ALL" -eq 1 && "${#COMPONENTS[@]}" -ne 0 ]]; then
  echo 'Choose --all OR explicit --component IDs' >&2
  exit 2
fi
action_count=$((ENABLE_AUTO + LIST_ONLY + PLATFORMS + CHECK_WEB))
action_count=$((action_count + PROBE_COUNT))
if [[ "$action_count" -gt 1 || ( "$action_count" -ne 0 && ( "$ALL" -ne 0 || "${#COMPONENTS[@]}" -ne 0 ) ) ]]; then
  echo 'Choose one action; do not combine probes, timer changes and component installs' >&2
  exit 2
fi
if [[ "$action_count" -eq 0 && "$ALL" -eq 0 && "${#COMPONENTS[@]}" -eq 0 ]]; then
  usage >&2
  exit 2
fi
for id in ${COMPONENTS[@]+"${COMPONENTS[@]}"}; do
  case "$id" in
    toolchain|hermes-clients|hermes-voice|hermes-updater|strix|scrapegraphai|ponytail|langfuse|honcho|hindsight|tigervnc|crawl4ai|parakeet|chatbotx) ;;
    *) echo "unknown component: $id" >&2; exit 2;;
  esac
done

if [[ "$LIST_ONLY" -eq 1 ]]; then
  echo "Declared stack: $STACK"
  if command -v python3 >/dev/null; then
    python3 - <<PY
import pathlib
try:
    import yaml
except ImportError:
    print(pathlib.Path("$STACK").read_text())
    raise SystemExit
data = yaml.safe_load(pathlib.Path("$STACK").read_text())
for c in data.get("components", []):
    print(f"{c['id']:12} {c['maturity']:12} {c['role']}")
print("platforms:", ", ".join(data.get("platforms", {}).get("surfaces", [])[:8]), "...")
PY
  else
    cat "$STACK"
  fi
  exit 0
fi

if [[ "$PLATFORMS" -eq 1 ]]; then
  cat "$ROOT/docs/dependencies/HERMES_PLATFORMS.md"
  exit 0
fi

as_station() {
  if [[ "$(id -un)" == "$STATION_USER" ]]; then
    env --chdir="$STATION_HOME" HOME="$STATION_HOME" HERMES_HOME="${HERMES_HOME:-$STATION_HOME/.hermes}" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  else
    sudo -u "$STATION_USER" -H env --chdir="$STATION_HOME" HOME="$STATION_HOME" \
      HERMES_HOME="${HERMES_HOME:-$STATION_HOME/.hermes}" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  fi
}

require_uv() {
  [[ -x "$STATION_HOME/.local/bin/uv" ]] || {
    echo "ERROR: pinned uv is missing; run scripts/station_toolchain_install.sh first" >&2
    return 2
  }
}

probe_dependency() {
  # Run under the operator, but imports happen only inside a disposable,
  # credential-free HOME supervised by Station's bounded Linux runner.
  local runner=(/usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8
    /usr/bin/python3 -I -S -B "$ROOT/scripts/station_dependency_probe.py" "$ROOT" "$1")
  if [[ "$(/usr/bin/id -un)" != "$STATION_USER" ]]; then
    runner=(/usr/bin/sudo -n -u "$STATION_USER" -H "${runner[@]}")
  fi
  "${runner[@]}"
}

install_service_software() {
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" /usr/bin/python3 - "$ROOT" "$1" <<'PY'
import json, pathlib, sys
from agentik_station.service_software import install_bundle
result = install_bundle(pathlib.Path(sys.argv[1]), sys.argv[2])
print(json.dumps(result, indent=2))
if not result['software_installed']:
    raise SystemExit(1)
PY
}

install_hermes_clients() {
  require_uv
  local runtime=/opt/station/tools/hermes/current
  [[ -x "$runtime/venv/bin/python" ]] || { echo 'ERROR: install Hermes foundation first' >&2; return 2; }
  # Additional native clients must match this Hermes release, not the independent
  # operator SDK versions. Never prune its existing provider/voice packages.
  local actual
  actual="$(as_station git -C "$runtime" rev-parse HEAD)"
  [[ "$actual" == "$HERMES_COMMIT" ]] || { echo 'ERROR: review native client compatibility for the installed Hermes revision first' >&2; return 2; }
  as_station "$runtime/venv/bin/python" -I -B -c 'import sys; assert sys.version_info[:2] == (3, 11)'
  as_station "$STATION_HOME/.local/bin/uv" pip install --python "$runtime/venv/bin/python" \
    --editable "$runtime[mcp,honcho,hindsight]" \
    "${LANGFUSE_PYTHON_WHEEL_URL}#sha256=${LANGFUSE_PYTHON_WHEEL_SHA256}"
  probe_dependency hermes-clients
  echo 'Native Hermes clients installed; memory selection and observability enrollment remain profile-scoped.'
}

install_toolchain() {
  if "$ROOT/scripts/station_toolchain_install.sh" --check; then
    return 0
  fi
  "$ROOT/scripts/station_toolchain_install.sh" --install
}

install_hermes_voice() {
  require_uv
  local runtime=/opt/station/tools/hermes/current
  [[ -x "$runtime/venv/bin/python" ]] || { echo 'ERROR: install Hermes foundation first' >&2; return 2; }
  local actual
  actual="$(as_station git -C "$runtime" rev-parse HEAD)"
  [[ "$actual" == "$HERMES_COMMIT" ]] || { echo 'ERROR: review voice compatibility for the installed Hermes revision first' >&2; return 2; }
  as_station "$STATION_HOME/.local/bin/uv" pip install --python "$runtime/venv/bin/python" \
    --editable "$runtime[voice,messaging]"
  probe_dependency voice
}

install_python_sdk() {
  local id="$1"
  local package="$2"
  local version="$3"
  local module="$4"
  local venv="$STATION_HOME/.local/share/agentik-station/venvs/${id}-py${AI_PYTHON_VERSION}"
  require_uv
  as_station mkdir -p "$STATION_HOME/.local/share/agentik-station/venvs"
  if [[ ! -x "$venv/bin/python" ]]; then
    as_station "$STATION_HOME/.local/bin/uv" venv --python "$AI_PYTHON_VERSION" "$venv"
  fi
  as_station "$STATION_HOME/.local/bin/uv" pip install --python "$venv/bin/python" "$package==$version"
  probe_dependency "$id"
}

install_scrapegraphai() {
  install_web_runtime scrapegraphai "$SCRAPEGRAPHAI_VERSION"
}

install_strix() {
  install_web_runtime strix "$STRIX_VERSION"
}

install_web_runtime() {
  require_uv
  [[ "$(id -u)" -eq 0 ]] || { echo 'Shared web runtimes require sudo' >&2; return 2; }
  local component="$1" version="$2" base=/opt/station/tools/web
  local runtime="$base/${component}-${version}-py${AI_PYTHON_VERSION}-pw${PLAYWRIGHT_VERSION}"
  local package="$component==$version"
  if [[ "$component" == strix ]]; then
    base=/opt/station/tools/security
    runtime="$base/strix-${version}-py${AI_PYTHON_VERSION}"
    [[ "$(uname -s)" == Linux ]] || { echo 'Station Strix installation requires Linux' >&2; return 2; }
    case "$(uname -m)" in
      x86_64) package="${STRIX_WHEEL_AMD64_URL}#sha256=${STRIX_WHEEL_AMD64_SHA256}";;
      aarch64|arm64) package="${STRIX_WHEEL_ARM64_URL}#sha256=${STRIX_WHEEL_ARM64_SHA256}";;
      *) echo 'Unsupported Strix architecture' >&2; return 2;;
    esac
  fi
  local venv="$runtime/venv" runner="$ROOT/components/agk-tui/hermes/plugins/agentik_os/scrapegraph_runner.py"
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" python3 - "$runtime" "$STATION_USER" <<'PY'
import pathlib, pwd, sys
from agentik_station.filesystem import SafeFS
runtime = pathlib.Path(sys.argv[1])
base = runtime.parent
account = pwd.getpwnam(sys.argv[2])
fs = SafeFS([base])
fs.mkdir(base)
if runtime.exists() or runtime.is_symlink():
    fs.mkdir(runtime)
    marker = runtime / 'BUILT'
    if marker.is_symlink() or not marker.is_file() or marker.stat().st_uid != 0:
        raise SystemExit('Incomplete/unsafe web runtime: inspect and archive that version directory before retrying: ' + str(runtime))
else:
    fs.mkdir(runtime, owner=(account.pw_uid, account.pw_gid))
    fs.mkdir(runtime / 'python', owner=(account.pw_uid, account.pw_gid))
PY
  if [[ ! -f "$runtime/BUILT" ]]; then
    # Download/build as the dedicated account; published code is then root-owned.
    as_station env UV_PYTHON_INSTALL_DIR="$runtime/python" "$STATION_HOME/.local/bin/uv" python install "$AI_PYTHON_VERSION"
    as_station env UV_PYTHON_INSTALL_DIR="$runtime/python" "$STATION_HOME/.local/bin/uv" venv --python "$AI_PYTHON_VERSION" "$venv"
    if [[ "$component" == strix ]]; then
      as_station "$STATION_HOME/.local/bin/uv" pip install --python "$venv/bin/python" "$package"
    else
      as_station "$STATION_HOME/.local/bin/uv" pip install --python "$venv/bin/python" \
        "$component==$version" "playwright==$PLAYWRIGHT_VERSION"
      # Browser system libraries are the only root package-manager operation here.
      "$venv/bin/python" -m playwright install-deps chromium
      as_station env PLAYWRIGHT_BROWSERS_PATH="$runtime/browsers" "$venv/bin/python" -m playwright install chromium
      if [[ "$component" == scrapegraphai ]]; then
        as_station env TIKTOKEN_CACHE_DIR="$runtime/tokenizers" "$venv/bin/python" -c \
          'import tiktoken; tiktoken.get_encoding("o200k_base"); tiktoken.get_encoding("cl100k_base")'
      fi
    fi
    chown -R root:root "$runtime"
    chmod -R a+rX,go-w "$runtime"
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" python3 - "$runtime" <<'PY'
import pathlib, sys
from agentik_station.filesystem import SafeFS
runtime = pathlib.Path(sys.argv[1])
SafeFS([runtime]).write_text(runtime / 'BUILT', 'INSTALLED_NOT_VERIFIED\n', mode=0o644)
PY
  fi
  if [[ "$component" == strix ]]; then
    probe_dependency strix
    echo 'Strix CLI only: no Docker grant, image pull, cloud connection or scan was performed.'
    return
  fi
  check_web_runtime "$component" "$version"
  echo "$component $version is installed; Zone credentials and live extraction remain separate."
}

check_web_runtime() {
  local component="$1" version="$2"
  probe_dependency "$component"
}

check_dependencies() {
  # Preserve each structured probe result. One missing runtime must not hide
  # independent later checks, but an explicit interruption stops the batch.
  local failed=0 component status
  for component in "$@"; do
    status=0
    probe_dependency "$component" || status=$?
    [[ "$status" -ne 130 && "$status" -ne 143 ]] || return "$status"
    [[ "$status" -eq 0 ]] || failed=1
  done
  return "$failed"
}

install_tigervnc() {
  [[ "$(id -u)" -eq 0 ]] || { echo "tigervnc apt install needs root" >&2; return 2; }
  apt-get update
  env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    tigervnc-standalone-server tigervnc-viewer
  dpkg-query -W -f='TigerVNC package ${Version}\n' tigervnc-standalone-server
  echo "TigerVNC installed (configure private-network display + auth before use)."
}

install_crawl4ai() {
  install_web_runtime crawl4ai "$CRAWL4AI_PYTHON_VERSION"
}

install_honcho() {
  install_python_sdk honcho honcho-ai "$HONCHO_PYTHON_VERSION" honcho
  install_service_software honcho
  echo "Honcho SDK and server software installed; service and Hermes profile enrollment remain unconfigured."
}

install_hindsight() {
  install_python_sdk hindsight hindsight-client "$HINDSIGHT_PYTHON_VERSION" hindsight_client
  install_service_software hindsight
  echo "Hindsight client and server software installed. Configure one profile's native memory provider separately."
}

install_ponytail() {
  # The reviewed native full-tree scan rejected this exact distribution. Native
  # Hermes permits an account's plugins.scan_on_install=false to skip its guard;
  # do not let that persisted setting publish/enable a known-rejected plugin.
  # A pin bump is NOT acceptance: future distributions need new immutable-source
  # review, a full native scan and a deliberately reviewed installer path here.
  # Never edit account config, filter the tree, copy an active plugin, or force it.
  local reviewed_repository=DietrichGebert/ponytail
  local reviewed_release=v4.9.0
  local reviewed_commit=0a4dd63ad4541f4f655c4108a295916f3c1d8fda
  if [[ "${PONYTAIL_REPOSITORY:-}" == "$reviewed_repository" &&
        "${PONYTAIL_RELEASE:-}" == "$reviewed_release" &&
        "${PONYTAIL_COMMIT:-}" == "$reviewed_commit" ]]; then
    printf 'BLOCKED: Ponytail %s (%s@%s) was rejected by the reviewed native full-tree security scan.\n' \
      "$reviewed_release" "$reviewed_repository" "$reviewed_commit" >&2
    echo 'No plugin was installed or enabled; account scan settings cannot override this Station gate. See docs/audit/2026-09-05-ponytail-native-scan.md.' >&2
    return 1
  fi
  echo 'NOT_VERIFIED: this Ponytail source pin has no accepted Station installation path. A pin change requires a new immutable-source review and full native security acceptance; it does not clear the existing block.' >&2
  echo 'No plugin was installed or enabled, and no account configuration was changed.' >&2
  return 2
}

install_langfuse() {
  local dest="$STATION_HOME/repos/langfuse-$LANGFUSE_RELEASE"
  as_station mkdir -p "$STATION_HOME/repos"
  if [[ ! -d "$dest/.git" ]]; then
    as_station git clone --depth 1 --branch "$LANGFUSE_RELEASE" \
      "https://github.com/$LANGFUSE_REPOSITORY.git" "$dest"
  fi
  local actual
  actual="$(as_station git -C "$dest" describe --tags --exact-match HEAD)"
  [[ "$actual" == "$LANGFUSE_RELEASE" ]] || {
    echo "ERROR: Langfuse checkout is $actual, expected $LANGFUSE_RELEASE" >&2
    return 1
  }
  as_station ln -sfn "$dest" "$STATION_HOME/repos/langfuse-current"
  install_service_software langfuse
  echo "Langfuse source and complete server software installed; service secrets and profile tracing enrollment remain unconfigured."
}

install_parakeet() {
  [[ "$(id -u)" -eq 0 ]] || { echo "Parakeet service install needs root" >&2; return 2; }
  command -v podman >/dev/null 2>&1 || { echo "ERROR: podman is required for Parakeet" >&2; return 2; }
  command -v systemctl >/dev/null 2>&1 || { echo "ERROR: systemd is required for Parakeet" >&2; return 2; }
  grep -Fq "$PARAKEET_IMAGE" "$ROOT/runtime/systemd/station-parakeet.service" || {
    echo "ERROR: Parakeet unit does not match the immutable image lock" >&2
    return 2
  }
  podman pull "$PARAKEET_IMAGE"
  podman image exists "$PARAKEET_IMAGE"
  install -d -m 0755 /usr/local/libexec /etc/systemd/system
  install -m 0755 "$ROOT/scripts/station_parakeet_transcribe.sh" \
    /usr/local/libexec/station-parakeet-transcribe
  install -m 0644 "$ROOT/runtime/systemd/station-parakeet.service" \
    /etc/systemd/system/station-parakeet.service
  systemctl daemon-reload
  systemctl enable --now station-parakeet.service
  for _attempt in $(seq 1 30); do
    if curl --fail --silent --show-error --max-time 2 \
      http://127.0.0.1:"$PARAKEET_PORT"/health >/dev/null; then
      systemctl is-active --quiet station-parakeet.service
      echo "Parakeet $PARAKEET_RELEASE is healthy on loopback port $PARAKEET_PORT."
      return 0
    fi
    sleep 2
  done
  systemctl status station-parakeet.service --no-pager >&2 || true
  echo "ERROR: Parakeet did not pass its loopback health check" >&2
  return 1
}

install_hermes_updater() {
  [[ "$(id -u)" -eq 0 ]] || { echo "installing updater software needs root" >&2; return 2; }
  unit_dir=/etc/systemd/system
  install -d -m 0755 /usr/local/libexec
  install -m 0755 "$ROOT/scripts/station_hermes_update.sh" /usr/local/libexec/station-hermes-update
  install -m 0644 "$ROOT/scripts/systemd/station-hermes-update.service" "$unit_dir/"
  install -m 0644 "$ROOT/scripts/systemd/station-hermes-update.timer" "$unit_dir/"
  systemctl daemon-reload
  echo "Hermes updater software installed; existing timer activation was not changed."
}

enable_hermes_auto_update() {
  install_hermes_updater
  systemctl enable --now station-hermes-update.timer
  systemctl list-timers station-hermes-update.timer --no-pager || true
  echo "Station weekly dependency discovery timer enabled; deployment requires a reviewed compatible release."
}

if [[ "$CHECK_WEB" -eq 1 ]]; then
  check_dependencies scrapegraphai crawl4ai
  exit 0
fi

if [[ -n "$PROBE" ]]; then
  if [[ "$PROBE" == memory ]]; then
    check_dependencies honcho hindsight
    exit 0
  fi
  probe_dependency "$PROBE"
  exit 0
fi

if [[ "$ENABLE_AUTO" -eq 1 ]]; then
  enable_hermes_auto_update
fi

if [[ "$ALL" -eq 1 ]]; then
  COMPONENTS=(toolchain hermes-clients hermes-voice hermes-updater strix scrapegraphai ponytail langfuse honcho hindsight tigervnc crawl4ai parakeet chatbotx)
fi

# Validate the complete selection before any mutation. A child process per
# component is essential: testing an installer FUNCTION in `if`/`||` disables
# its internal errexit and can turn a partial install into a false success.
for id in ${COMPONENTS[@]+"${COMPONENTS[@]}"}; do
  case "$id" in
    toolchain|hermes-clients|hermes-voice|hermes-updater|strix|scrapegraphai|ponytail|langfuse|honcho|hindsight|tigervnc|crawl4ai|parakeet|chatbotx) ;;
    *) echo "unknown component: $id" >&2; exit 2;;
  esac
done
if [[ "$ALL" -eq 1 || "${#COMPONENTS[@]}" -gt 1 ]]; then
  [[ "$(id -u)" -eq 0 && "$(uname -s)" == Linux ]] || { echo 'Full Host dependency installation requires Linux sudo' >&2; exit 2; }
  failed=0
  outcomes=()
  for id in "${COMPONENTS[@]}"; do
    status=0
    /bin/bash "$ROOT/scripts/station_deps_install.sh" --component "$id" || status=$?
    outcomes+=("$id:$status")
    printf 'COMPONENT %s EXIT %s\n' "$id" "$status"
    [[ "$status" -eq 0 ]] || failed=1
    # A user interruption stops the batch, rather than unexpectedly starting
    # more installers after Ctrl-C. Ordinary component failures do not.
    [[ "$status" -ne 130 && "$status" -ne 143 ]] || break
  done
  PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$ROOT/src" /usr/bin/python3 - "$ALL" "${outcomes[@]}" <<'PY'
import json, pathlib, sys
from datetime import datetime, timezone
from agentik_station.bootstrap_state import _secure_chain
from agentik_station.filesystem import SafeFS
rows = [dict(zip(('component', 'exit_code'), (item.rsplit(':', 1)[0], int(item.rsplit(':', 1)[1])))) for item in sys.argv[2:]]
root = pathlib.Path('/var/lib/station/dependency-install')
_secure_chain(root, 0, allow_missing=True)
fs = SafeFS([root])
fs.mkdir(root, mode=0o700, owner=(0, 0))
record = {'schema_version': 1, 'full_selection': sys.argv[1] == '1',
          'recorded_at': datetime.now(timezone.utc).isoformat(), 'components': rows,
          'installation_steps_passed': all(row['exit_code'] == 0 for row in rows),
          'operational': False, 'next': 'station deps full-check'}
target = root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json')
fs.write_text(target, json.dumps(record, indent=2) + '\n', mode=0o600, owner=(0, 0))
print('Dependency receipt: ' + str(target))
PY
  if [[ "$failed" -ne 0 ]]; then
    echo 'INCOMPLETE: one or more required components failed; successful independent components were retained.' >&2
  fi
  exit "$failed"
fi

for id in ${COMPONENTS[@]+"${COMPONENTS[@]}"}; do
  case "$id" in
    toolchain) install_toolchain;;
    hermes-clients) install_hermes_clients;;
    hermes-voice) install_hermes_voice;;
    hermes-updater) install_hermes_updater;;
    strix) install_strix;;
    scrapegraphai) install_scrapegraphai;;
    ponytail) install_ponytail;;
    langfuse) install_langfuse;;
    honcho) install_honcho;;
    hindsight) install_hindsight;;
    tigervnc) install_tigervnc;;
    crawl4ai) install_crawl4ai;;
    parakeet) install_parakeet;;
    chatbotx) install_service_software chatbotx;;
    *) echo "unknown component: $id" >&2; exit 2;;
  esac
done

echo
echo "Done. Runtime remains unverified until component Doctor and external readback."
echo "Platforms: use station platform setup --zone <zone> --instance <instance>, then verify, install and start separately."
echo "Guide: $ROOT/docs/dependencies/HERMES_PLATFORMS.md"
