#!/usr/bin/env bash
# Optional dependency installer for Agentik Station power stack.
# Does NOT claim OPERATIONAL. Installation remains below VERIFIED until Doctor/readback.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
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

Components: strix scrapegraphai ponytail langfuse honcho hindsight tigervnc crawl4ai parakeet
USAGE
}

COMPONENTS=()
ENABLE_AUTO=0
LIST_ONLY=0
PLATFORMS=0
ALL=0
CHECK_WEB=0

while (($#)); do
  case "$1" in
    --all) ALL=1; shift;;
    --check-web) CHECK_WEB=1; shift;;
    --list) LIST_ONLY=1; shift;;
    --component) COMPONENTS+=("$2"); shift 2;;
    --enable-hermes-auto-update) ENABLE_AUTO=1; shift;;
    --platforms-guide) PLATFORMS=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "unknown: $1" >&2; usage; exit 2;;
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
    env HOME="$STATION_HOME" HERMES_HOME="${HERMES_HOME:-$STATION_HOME/.hermes}" \
      PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  else
    sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" \
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
  as_station "$venv/bin/python" -c "import $module; print('$id import OK')"
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
    as_station "$venv/bin/strix" --version
    echo 'Strix CLI only: no Docker grant, image pull, cloud connection or scan was performed.'
    return
  fi
  check_web_runtime "$component" "$version"
  echo "$component $version is installed; Zone credentials and live extraction remain separate."
}

check_web_runtime() {
  local component="$1" version="$2"
  local runtime="/opt/station/tools/web/${component}-${version}-py${AI_PYTHON_VERSION}-pw${PLAYWRIGHT_VERSION}"
  local venv="$runtime/venv" runner="$ROOT/components/agk-tui/hermes/plugins/agentik_os/scrapegraph_runner.py"
  printf '{"component":"%s","health":true}\n' "$component" | \
    as_station env PLAYWRIGHT_BROWSERS_PATH="$runtime/browsers" TIKTOKEN_CACHE_DIR="$runtime/tokenizers" PYTHONDONTWRITEBYTECODE=1 \
      "$venv/bin/python" "$runner"
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
  echo "Honcho SDK $HONCHO_PYTHON_VERSION installed; API/self-hosted service credentials remain unconfigured."
}

install_hindsight() {
  install_python_sdk hindsight hindsight-client "$HINDSIGHT_PYTHON_VERSION" hindsight_client
  echo "Hindsight client $HINDSIGHT_PYTHON_VERSION installed. Configure the native Hermes provider with: hermes memory setup"
}

install_ponytail() {
  local hermes="$STATION_HOME/.local/bin/hermes"
  [[ -x "$hermes" ]] || hermes="$(command -v hermes || true)"
  [[ -x "$hermes" ]] || { echo "ERROR: Hermes is required for the Ponytail plugin" >&2; return 2; }
  as_station "$hermes" plugins install "$PONYTAIL_REPOSITORY" --ref "$PONYTAIL_COMMIT" --enable
  as_station "$hermes" plugins list
  echo "Ponytail installed through the native Hermes plugin protocol (pinned release: $PONYTAIL_RELEASE / $PONYTAIL_COMMIT)."
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
  echo "Langfuse $LANGFUSE_RELEASE staged at $dest; compose services and secrets are not auto-started."
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

enable_hermes_auto_update() {
  [[ "$(id -u)" -eq 0 ]] || { echo "enabling timer needs root" >&2; return 2; }
  unit_dir=/etc/systemd/system
  install -d -m 0755 /usr/local/libexec
  install -m 0755 "$ROOT/scripts/station_hermes_update.sh" /usr/local/libexec/station-hermes-update
  install -m 0644 "$ROOT/scripts/systemd/station-hermes-update.service" "$unit_dir/"
  install -m 0644 "$ROOT/scripts/systemd/station-hermes-update.timer" "$unit_dir/"
  systemctl daemon-reload
  systemctl enable --now station-hermes-update.timer
  systemctl list-timers station-hermes-update.timer --no-pager || true
  echo "Hermes weekly auto-update timer enabled."
}

if [[ "$CHECK_WEB" -eq 1 ]]; then
  check_web_runtime scrapegraphai "$SCRAPEGRAPHAI_VERSION"
  check_web_runtime crawl4ai "$CRAWL4AI_PYTHON_VERSION"
  exit 0
fi

if [[ "$ENABLE_AUTO" -eq 1 ]]; then
  enable_hermes_auto_update
fi

if [[ "$ALL" -eq 1 ]]; then
  COMPONENTS=(strix scrapegraphai ponytail langfuse honcho hindsight tigervnc crawl4ai parakeet)
fi

for id in "${COMPONENTS[@]}"; do
  case "$id" in
    strix) install_strix;;
    scrapegraphai) install_scrapegraphai;;
    ponytail) install_ponytail;;
    langfuse) install_langfuse;;
    honcho) install_honcho;;
    hindsight) install_hindsight;;
    tigervnc) install_tigervnc;;
    crawl4ai) install_crawl4ai;;
    parakeet) install_parakeet;;
    *) echo "unknown component: $id" >&2; exit 2;;
  esac
done

echo
echo "Done. Runtime remains unverified until component Doctor and external readback."
echo "Platforms: hermes gateway setup && hermes gateway start"
echo "Guide: $ROOT/docs/dependencies/HERMES_PLATFORMS.md"
