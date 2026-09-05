#!/usr/bin/env bash
# Install the pinned Station operator toolchain without authenticating accounts.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOCK="$ROOT/config/versions.lock"
DISCORD_SDK_SOURCE="$ROOT/resources/discord-js-sdk"
STATION_USER="${STATION_USER:-agk-station}"
STATION_HOME="${STATION_HOME:-/home/${STATION_USER}}"
MODE="install"
INSTALL_CODEX=1
CHECK_HERMES=1

usage() {
  cat <<'USAGE'
usage: station_toolchain_install.sh [--plan|--install|--check] [--without-codex] [--without-hermes]

Installs pinned, user-local Python, Node.js, GitHub CLI, Vercel CLI,
Codex CLI, Composio CLI and shadcn CLI. Hermes is installed separately by bootstrap.sh.
Also installs the pinned discord.js SDK into an isolated, non-gateway resource directory.
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
  discord.js SDK:       ${DISCORD_JS_VERSION} (isolated; no gateway)
  shadcn CLI:           ${SHADCN_CLI_VERSION}

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
  output="$(as_station "$binary" "$@" 2>&1)" || {
    output="${output%%$'\n'*}"
    printf 'FAILED  %-12s %s\n' "$label" "$output"
    return 1
  }
  output="${output%%$'\n'*}"
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
  output="$(as_station "$binary" "$@" 2>&1)" || {
    output="${output%%$'\n'*}"
    printf 'FAILED  %-12s %s\n' "$label" "$output"
    return 1
  }
  output="${output%%$'\n'*}"
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
  check_pinned_tool shadcn "$tool_path/shadcn" "$SHADCN_CLI_VERSION" --version || failures=$((failures + 1))
  local discord_sdk="$STATION_HOME/.local/share/station-sdk/discord-js/node_modules/discord.js/package.json"
  if [[ ! -f "$discord_sdk" ]]; then
    printf 'MISSING %-12s %s\n' discord.js "$discord_sdk"
    failures=$((failures + 1))
  else
    local observed_discord
    observed_discord="$(as_station "$tool_path/node" -e 'process.stdout.write(require(process.argv[1]).version)' "$discord_sdk")" || observed_discord="ERROR"
    if [[ "$observed_discord" != "$DISCORD_JS_VERSION" ]]; then
      printf 'DRIFT   %-12s expected=%s observed=%s\n' discord.js "$DISCORD_JS_VERSION" "$observed_discord"
      failures=$((failures + 1))
    else
      printf 'PINNED  %-12s %s\n' discord.js "$observed_discord"
    fi
  fi
  if [[ "$CHECK_HERMES" -eq 1 ]]; then
    if command -v hermes >/dev/null 2>&1 || [[ -x "$tool_path/hermes" ]]; then
      check_tool hermes "$(command -v hermes 2>/dev/null || printf '%s' "$tool_path/hermes")" --version \
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

manage_node_launchers() {
  # Python is a bootstrap prerequisite. Run this narrow filesystem handoff as
  # the operator, never root; preserve unrelated launchers and reject symlinked
  # parents. npm owns its global package, while Station owns these exact links.
  as_station /usr/bin/python3 -I - "$STATION_HOME" "$1" "$2" "$NPM_VERSION" <<'PY'
import contextlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import uuid

home, bundle, action, version = sys.argv[1:]
prefix = home + "/.local"
bins = prefix + "/bin"
npm_root = prefix + "/lib/node_modules/npm"
for value in (home, bundle):
    if not value.startswith("/") or os.path.normpath(value) != value or value == "/":
        sys.exit("ERROR: Node launcher paths must be canonical absolute paths")
if not re.fullmatch(re.escape(prefix) + r"/lib/node-v\d+\.\d+\.\d+-linux-(x64|arm64)", bundle):
    sys.exit("ERROR: unexpected Station Node bundle path")

@contextlib.contextmanager
def directory(path, *, missing=False):
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in Path(path).parts[1:]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            except FileNotFoundError:
                if missing:
                    yield None
                    return
                raise
            os.close(fd)
            fd = child
        yield fd
    finally:
        os.close(fd)

def regular(path, *, missing=False):
    with directory(str(Path(path).parent), missing=missing) as fd:
        if fd is None:
            return False
        try:
            value = os.stat(Path(path).name, dir_fd=fd, follow_symlinks=False)
        except FileNotFoundError:
            if missing:
                return False
            raise
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise ValueError("unsafe Node/npm executable or package metadata")
        return True

def recognized(fd, binary):
    try:
        value = os.stat(binary, dir_fd=fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if not stat.S_ISLNK(value.st_mode):
        raise ValueError("refusing unrelated existing launcher: " + binary)
    target = os.path.normpath(os.path.join(bins, os.readlink(binary, dir_fd=fd)))
    global_target = npm_root + "/bin/" + binary + "-cli.js"
    hermes_target = home + "/.hermes/node/bin/" + binary
    node_target = re.fullmatch(re.escape(prefix) + r"/lib/node-v\d+\.\d+\.\d+-linux-(x64|arm64)/bin/" + binary, target)
    if not (node_target or (binary in {"npm", "npx"} and target == global_target)
            or (binary in {"node", "npm", "npx"} and target == hermes_target)):
        raise ValueError("refusing unrelated existing launcher: " + binary)
    with directory(str(Path(target).parent), missing=True):
        pass
    return target

def publish(fd, binary, target):
    recognized(fd, binary)
    try:
        if os.readlink(binary, dir_fd=fd) == target:
            return
    except FileNotFoundError:
        pass
    temporary = ".station-launcher-" + uuid.uuid4().hex
    os.symlink(target, temporary, dir_fd=fd)
    try:
        recognized(fd, binary)
        os.rename(temporary, binary, src_dir_fd=fd, dst_dir_fd=fd)
    finally:
        try:
            os.unlink(temporary, dir_fd=fd)
        except FileNotFoundError:
            pass

def publish_npm(fd):
    with directory(bins) as current:
        if (os.fstat(current).st_dev, os.fstat(current).st_ino) != (os.fstat(fd).st_dev, os.fstat(fd).st_ino):
            raise ValueError("Node launcher directory changed during installation")
    for name in ("package.json", "bin/npm-cli.js", "bin/npx-cli.js"):
        regular(npm_root + "/" + name)
    with open(npm_root + "/package.json", encoding="utf-8") as source:
        package = json.load(source)
    if package.get("name") != "npm" or package.get("version") != version:
        raise ValueError("global npm package does not match the requested pin")
    for binary in ("npm", "npx"):
        publish(fd, binary, "../lib/node_modules/npm/bin/" + binary + "-cli.js")

def install_npm(fd):
    # Reify checks global bins before extraction, even when both lifecycle and
    # bin publication are disabled. Reserve ONLY known conflicting predecessors.
    # The private directory also preserves links after an uncatchable shutdown;
    # later invocations stop for reviewed recovery instead of deleting evidence.
    regular(bundle + "/bin/node")
    regular(bundle + "/lib/node_modules/npm/bin/npm-cli.js")
    reservation = ".station-npm-handoff-" + uuid.uuid4().hex
    os.mkdir(reservation, mode=0o700, dir_fd=fd)
    backup_fd = os.open(reservation, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
    moved = {}
    succeeded = False
    try:
        for binary in ("npm", "npx"):
            target = recognized(fd, binary)
            if target is None or target == npm_root + "/bin/" + binary + "-cli.js":
                continue
            original = os.stat(binary, dir_fd=fd, follow_symlinks=False)
            link = os.readlink(binary, dir_fd=fd)
            os.rename(binary, binary, src_dir_fd=fd, dst_dir_fd=backup_fd)
            moved[binary] = (original.st_dev, original.st_ino, link)
        completed = subprocess.run([
            bundle + "/bin/node", bundle + "/lib/node_modules/npm/bin/npm-cli.js",
            "install", "--global", "--ignore-scripts", "--bin-links=false", "npm@" + version,
        ], check=False)
        if completed.returncode:
            raise SystemExit(completed.returncode if completed.returncode > 0 else 128 - completed.returncode)
        publish_npm(fd)
        succeeded = True
    finally:
        failures = []
        for binary, identity in moved.items():
            try:
                saved = os.stat(binary, dir_fd=backup_fd, follow_symlinks=False)
                if (not stat.S_ISLNK(saved.st_mode)
                        or (saved.st_dev, saved.st_ino, os.readlink(binary, dir_fd=backup_fd)) != identity):
                    raise ValueError("reserved launcher changed")
                if succeeded:
                    os.unlink(binary, dir_fd=backup_fd)
                else:
                    current = recognized(fd, binary)
                    if current is not None:
                        if current != npm_root + "/bin/" + binary + "-cli.js":
                            raise ValueError("launcher was replaced during npm installation")
                        os.unlink(binary, dir_fd=fd)
                    os.rename(binary, binary, src_dir_fd=backup_fd, dst_dir_fd=fd)
            except (OSError, ValueError):
                failures.append(binary)
        os.close(backup_fd)
        if failures:
            raise ValueError("npm launcher recovery requires review; preserved " + ",".join(failures)
                             + " in " + bins + "/" + reservation)
        os.rmdir(reservation, dir_fd=fd)

def interrupted(signum, frame):
    raise SystemExit(128 + signum)

signal.signal(signal.SIGTERM, interrupted)

try:
    for path in (home, prefix, bins, prefix + "/lib", bundle, bundle + "/bin",
                 bundle + "/lib/node_modules/npm/bin", npm_root + "/bin"):
        with directory(path, missing=True):
            pass
    for name in ("package.json", "bin/npm-cli.js", "bin/npx-cli.js"):
        regular(npm_root + "/" + name, missing=True)
    regular(bundle + "/bin/node", missing=True)
    regular(bundle + "/lib/node_modules/npm/bin/npm-cli.js", missing=True)
    with directory(bins, missing=action == "check") as fd:
        if fd is not None:
            if any(name.startswith(".station-npm-handoff-") for name in os.listdir(fd)):
                raise ValueError("unfinished npm launcher reservation in " + bins
                                 + "; review and restore its preserved links before retrying")
            for binary in ("node", "npm", "npx", "corepack"):
                recognized(fd, binary)
        if action == "node":
            regular(bundle + "/bin/node")
            publish(fd, "node", bundle + "/bin/node")
            # Recent Node distributions do not necessarily include Corepack.
            if os.path.exists(bundle + "/bin/corepack"):
                corepack = os.path.realpath(bundle + "/bin/corepack")
                if not corepack.startswith(bundle + "/"):
                    raise ValueError("Corepack target escapes the pinned Node bundle")
                regular(corepack)
                publish(fd, "corepack", bundle + "/bin/corepack")
        elif action == "npm":
            publish_npm(fd)
        elif action == "npm-install":
            install_npm(fd)
        elif action != "check":
            raise ValueError("unknown Node launcher action")
except (OSError, ValueError) as exc:
    sys.exit("ERROR: safe Node/npm launcher handoff failed: " + str(exc))
PY
}

install_node() {
  local version="${NODE_VERSION#v}"
  local base="node-v${version}-linux-${NODE_ARCH}"
  local archive="${base}.tar.xz"
  local dest="$STATION_HOME/.local/lib/$base"
  manage_node_launchers "$dest" check
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
  manage_node_launchers "$dest" node
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
  local dest="$STATION_HOME/.local/lib/node-v${NODE_VERSION#v}-linux-${NODE_ARCH}"
  manage_node_launchers "$dest" check
  # One operator process owns reservation, native install, validation and either
  # publication or failure restoration. Never use --force to bypass npm checks.
  manage_node_launchers "$dest" npm-install
  verify_npm_integrity vercel "$VERCEL_CLI_VERSION" "$VERCEL_CLI_INTEGRITY"
  verify_npm_integrity shadcn "$SHADCN_CLI_VERSION" "$SHADCN_CLI_INTEGRITY"
  as_station "$tool_path/npm" install --global "vercel@${VERCEL_CLI_VERSION}"
  as_station "$tool_path/npm" install --global "shadcn@${SHADCN_CLI_VERSION}"
  if [[ "$INSTALL_CODEX" -eq 1 ]]; then
    verify_npm_integrity @openai/codex "$CODEX_CLI_VERSION" "$CODEX_CLI_INTEGRITY"
    as_station "$tool_path/npm" install --global "@openai/codex@${CODEX_CLI_VERSION}"
  fi
}

install_discord_sdk() {
  local destination="$STATION_HOME/.local/share/station-sdk/discord-js"
  [[ -f "$DISCORD_SDK_SOURCE/package.json" && -f "$DISCORD_SDK_SOURCE/package-lock.json" ]] || {
    echo "ERROR: bundled discord.js SDK lock is missing" >&2
    return 1
  }
  verify_npm_integrity discord.js "$DISCORD_JS_VERSION" "$DISCORD_JS_INTEGRITY"
  install -d -m 0755 -o "$STATION_USER" -g "$STATION_USER" "$destination"
  install -m 0644 -o "$STATION_USER" -g "$STATION_USER" \
    "$DISCORD_SDK_SOURCE/package.json" "$DISCORD_SDK_SOURCE/package-lock.json" "$destination/"
  as_station "$tool_path/npm" ci --ignore-scripts --omit=dev --prefix "$destination"
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
  local shared="/opt/station/tools/composio/${COMPOSIO_CLI_VERSION}"
  install -d -m 0755 -o root -g root "$shared" /usr/local/bin
  install -m 0755 -o root -g root "$tool_path/composio" "$shared/composio"
  ln -sfn "$shared/composio" /usr/local/bin/composio
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
install_discord_sdk
install_composio
check_toolchain
