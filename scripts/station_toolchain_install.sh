#!/usr/bin/env bash
# Install the pinned Station operator toolchain without authenticating accounts.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/config/versions.lock"
STATION_USER="${STATION_USER:-agk-station}"
STATION_HOME="${STATION_HOME:-/home/${STATION_USER}}"
MODE="install"
INSTALL_CODEX=1
CHECK_HERMES=1

usage() {
  cat <<'USAGE'
usage: station_toolchain_install.sh [--plan|--install|--check] [--without-codex] [--without-hermes]

Installs pinned, user-local Python, Node.js, GitHub CLI, Vercel CLI,
Codex CLI and Composio CLI. Hermes is installed separately by bootstrap.sh.
Account login and external connections are never performed automatically.
USAGE
}

while (($#)); do
  case "$1" in
    --plan) MODE="plan"; shift;;
    --install) MODE="install"; shift;;
    --check) MODE="check"; shift;;
    --without-codex) INSTALL_CODEX=0; shift;;
    --without-hermes) CHECK_HERMES=0; shift;;
    -h|--help) usage; exit 0;;
    *) echo "unknown option: $1" >&2; usage; exit 2;;
  esac
done

[[ -r "$LOCK" ]] || { echo "ERROR: missing $LOCK" >&2; exit 2; }
# shellcheck disable=SC1090
source "$LOCK"

tool_path="$STATION_HOME/.local/bin"
export PATH="$tool_path:$PATH"

as_station() {
  if [[ "$(id -un)" == "$STATION_USER" ]]; then
    env HOME="$STATION_HOME" PATH="$tool_path:$PATH" NPM_CONFIG_PREFIX="$STATION_HOME/.local" "$@"
  else
    sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" PATH="$tool_path:$PATH" \
      NPM_CONFIG_PREFIX="$STATION_HOME/.local" "$@"
  fi
}

print_plan() {
  cat <<EOF
Station pinned operator toolchain
  Python latest stable: ${PYTHON_VERSION} (operator default)
  Python AI runtime:    ${AI_PYTHON_VERSION} (isolated SDK/tool compatibility)
  Python Hermes:       ${HERMES_PYTHON_VERSION} (Hermes-managed environment)
  Node.js LTS:          ${NODE_VERSION}
  npm:                  ${NPM_VERSION}
  GitHub CLI:           ${GITHUB_CLI_VERSION}
  Vercel CLI:           ${VERCEL_CLI_VERSION}
  Codex CLI:            $([[ "$INSTALL_CODEX" -eq 1 ]] && printf '%s' "$CODEX_CLI_VERSION" || printf 'skipped')
  Composio CLI:         ${COMPOSIO_CLI_VERSION}

Install root: ${STATION_HOME}/.local
Authentication: NOT PERFORMED
EOF
}

check_tool() {
  local label="$1"
  local binary="$2"
  shift 2
  if [[ ! -x "$binary" ]]; then
    printf 'MISSING %-12s %s\n' "$label" "$binary"
    return 1
  fi
  local output
  output="$(as_station "$binary" "$@" 2>&1 | head -1)" || {
    printf 'FAILED  %-12s %s\n' "$label" "$output"
    return 1
  }
  printf 'READY   %-12s %s\n' "$label" "$output"
}

check_pinned_tool() {
  local label="$1"
  local binary="$2"
  local expected="$3"
  shift 3
  if [[ ! -x "$binary" ]]; then
    printf 'MISSING %-12s %s\n' "$label" "$binary"
    return 1
  fi
  local output
  output="$(as_station "$binary" "$@" 2>&1 | head -1)" || {
    printf 'FAILED  %-12s %s\n' "$label" "$output"
    return 1
  }
  if [[ "$output" != *"$expected"* ]]; then
    printf 'DRIFT   %-12s expected=%s observed=%s\n' "$label" "$expected" "$output"
    return 1
  fi
  printf 'PINNED  %-12s %s\n' "$label" "$output"
}

check_toolchain() {
  local failures=0
  check_pinned_tool python "$tool_path/python-latest" "$PYTHON_VERSION" --version || failures=$((failures + 1))
  check_pinned_tool python-ai "$tool_path/python-ai" "$AI_PYTHON_VERSION" --version || failures=$((failures + 1))
  check_pinned_tool node "$tool_path/node" "$NODE_VERSION" --version || failures=$((failures + 1))
  check_pinned_tool npm "$tool_path/npm" "$NPM_VERSION" --version || failures=$((failures + 1))
  check_pinned_tool uv "$tool_path/uv" "$UV_VERSION" --version || failures=$((failures + 1))
  check_pinned_tool github "$tool_path/gh" "$GITHUB_CLI_VERSION" --version || failures=$((failures + 1))
  check_pinned_tool vercel "$tool_path/vercel" "$VERCEL_CLI_VERSION" --version || failures=$((failures + 1))
  if [[ "$INSTALL_CODEX" -eq 1 ]]; then
    check_pinned_tool codex "$tool_path/codex" "$CODEX_CLI_VERSION" --version || failures=$((failures + 1))
  fi
  check_pinned_tool composio "$tool_path/composio" "$COMPOSIO_CLI_VERSION" --version || failures=$((failures + 1))
  if [[ "$CHECK_HERMES" -eq 1 ]]; then
    if command -v hermes >/dev/null 2>&1 || [[ -x "$tool_path/hermes" ]]; then
      check_tool hermes "$(command -v hermes 2>/dev/null || printf '%s' "$tool_path/hermes")" version \
        || failures=$((failures + 1))
    else
      printf 'MISSING %-12s install through bootstrap.sh\n' hermes
      failures=$((failures + 1))
    fi
  fi
  echo "AUTH    GitHub/Vercel/Composio/Hermes login remains operator-owned."
  ((failures == 0))
}

linux_arches() {
  case "$(uname -m)" in
    x86_64) NODE_ARCH="x64"; GH_ARCH="amd64"; UV_ARCH="x86_64";;
    aarch64|arm64) NODE_ARCH="arm64"; GH_ARCH="arm64"; UV_ARCH="aarch64";;
    *) echo "ERROR: unsupported architecture: $(uname -m)" >&2; exit 2;;
  esac
}

verify_checksum_file() {
  local checksums="$1"
  local archive="$2"
  local directory="$3"
  local expected
  expected="$(awk -v name="$archive" '$2 == name || $2 == "*" name {print $1; exit}' "$checksums")"
  [[ "$expected" =~ ^[0-9a-fA-F]{64}$ ]] || {
    echo "ERROR: checksum for $archive was not published" >&2
    return 1
  }
  (cd "$directory" && printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status)
}

install_node() {
  local version="${NODE_VERSION#v}"
  local base="node-v${version}-linux-${NODE_ARCH}"
  local archive="${base}.tar.xz"
  local dest="$STATION_HOME/.local/lib/$base"
  if [[ ! -x "$dest/bin/node" ]]; then
    local tmp
    tmp="$(mktemp -d)"
    curl --fail --silent --show-error --location "https://nodejs.org/dist/v${version}/${archive}" --output "$tmp/$archive"
    curl --fail --silent --show-error --location "https://nodejs.org/dist/v${version}/SHASUMS256.txt" --output "$tmp/SHASUMS256.txt"
    verify_checksum_file "$tmp/SHASUMS256.txt" "$archive" "$tmp"
    tar -xJf "$tmp/$archive" -C "$tmp"
    install -d -m 0755 -o "$STATION_USER" -g "$STATION_USER" "$STATION_HOME/.local/lib"
    mv "$tmp/$base" "$dest"
    chown -R "$STATION_USER:$STATION_USER" "$dest"
    rm "$tmp/$archive" "$tmp/SHASUMS256.txt"
    rmdir "$tmp"
  fi
  install -d -m 0755 -o "$STATION_USER" -g "$STATION_USER" "$tool_path"
  for binary in node npm npx corepack; do
    ln -sfn "$dest/bin/$binary" "$tool_path/$binary"
    chown -h "$STATION_USER:$STATION_USER" "$tool_path/$binary"
  done
}

install_github_cli() {
  local version="${GITHUB_CLI_VERSION#v}"
  local base="gh_${version}_linux_${GH_ARCH}"
  local archive="${base}.tar.gz"
  local tmp
  tmp="$(mktemp -d)"
  curl --fail --silent --show-error --location \
    "https://github.com/cli/cli/releases/download/v${version}/${archive}" --output "$tmp/$archive"
  curl --fail --silent --show-error --location \
    "https://github.com/cli/cli/releases/download/v${version}/gh_${version}_checksums.txt" --output "$tmp/checksums.txt"
  verify_checksum_file "$tmp/checksums.txt" "$archive" "$tmp"
  tar -xzf "$tmp/$archive" -C "$tmp"
  install -m 0755 -o "$STATION_USER" -g "$STATION_USER" "$tmp/$base/bin/gh" "$tool_path/gh"
  rm -r "$tmp/$base"
  rm "$tmp/$archive" "$tmp/checksums.txt"
  rmdir "$tmp"
}

install_uv() {
  local version="${UV_VERSION#v}"
  local base="uv-${UV_ARCH}-unknown-linux-gnu"
  local archive="${base}.tar.gz"
  local tmp
  tmp="$(mktemp -d)"
  curl --fail --silent --show-error --location \
    "https://github.com/astral-sh/uv/releases/download/${version}/${archive}" --output "$tmp/$archive"
  curl --fail --silent --show-error --location \
    "https://github.com/astral-sh/uv/releases/download/${version}/${archive}.sha256" --output "$tmp/checksums.txt"
  verify_checksum_file "$tmp/checksums.txt" "$archive" "$tmp"
  tar -xzf "$tmp/$archive" -C "$tmp"
  install -m 0755 -o "$STATION_USER" -g "$STATION_USER" "$tmp/$base/uv" "$tool_path/uv"
  install -m 0755 -o "$STATION_USER" -g "$STATION_USER" "$tmp/$base/uvx" "$tool_path/uvx"
  rm -r "$tmp/$base"
  rm "$tmp/$archive" "$tmp/checksums.txt"
  rmdir "$tmp"
}

install_python() {
  local uv="$tool_path/uv"
  local version alias python_path
  for version in "$PYTHON_VERSION" "$AI_PYTHON_VERSION"; do
    as_station "$uv" python install "$version"
    python_path="$(as_station "$uv" python find "$version")"
    [[ "$python_path" == "$STATION_HOME"/* ]] || {
      echo "ERROR: uv returned Python outside Station home: $python_path" >&2
      return 1
    }
    if [[ "$version" == "$PYTHON_VERSION" ]]; then
      alias=python-latest
    else
      alias=python-ai
    fi
    ln -sfn "$python_path" "$tool_path/$alias"
    chown -h "$STATION_USER:$STATION_USER" "$tool_path/$alias"
  done
}

verify_npm_integrity() {
  local package="$1"
  local version="$2"
  local expected="$3"
  local actual
  actual="$(as_station "$tool_path/npm" view "${package}@${version}" dist.integrity)"
  [[ "$actual" == "$expected" ]] || {
    echo "ERROR: npm integrity drift for ${package}@${version}" >&2
    return 1
  }
}

install_node_clis() {
  verify_npm_integrity vercel "$VERCEL_CLI_VERSION" "$VERCEL_CLI_INTEGRITY"
  as_station "$tool_path/npm" install --global "npm@${NPM_VERSION}"
  as_station "$tool_path/npm" install --global "vercel@${VERCEL_CLI_VERSION}"
  if [[ "$INSTALL_CODEX" -eq 1 ]]; then
    verify_npm_integrity @openai/codex "$CODEX_CLI_VERSION" "$CODEX_CLI_INTEGRITY"
    as_station "$tool_path/npm" install --global "@openai/codex@${CODEX_CLI_VERSION}"
  fi
}

install_composio() {
  local tmp
  tmp="$(mktemp)"
  curl --fail --silent --show-error --location https://composio.dev/install --output "$tmp"
  printf '%s  %s\n' "$COMPOSIO_INSTALL_SHA256" "$tmp" | sha256sum --check --status || {
    echo "ERROR: Composio installer checksum drifted; review upstream and update the lock intentionally." >&2
    rm -f "$tmp"
    return 1
  }
  chown "$STATION_USER:$STATION_USER" "$tmp"
  as_station env COMPOSIO_INSTALL_VERSION="$COMPOSIO_CLI_VERSION" \
    COMPOSIO_INSTALL_SHELL=none COMPOSIO_INSTALL_HELP=0 sh "$tmp"
  rm "$tmp"
}

case "$MODE" in
  plan) print_plan; exit 0;;
  check) print_plan; check_toolchain; exit $?;;
esac

[[ "$(uname -s)" == "Linux" ]] || { echo "ERROR: toolchain installer currently supports Linux" >&2; exit 2; }
[[ "$(id -u)" -eq 0 ]] || { echo "ERROR: --install requires root" >&2; exit 2; }
id "$STATION_USER" >/dev/null 2>&1 || { echo "ERROR: missing user $STATION_USER" >&2; exit 2; }
linux_arches
print_plan
install_node
install_github_cli
install_uv
install_python
install_node_clis
install_composio
check_toolchain
