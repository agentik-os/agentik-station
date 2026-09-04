#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
prefix=${PREFIX:-$HOME/.local}
install_hermes=true
install_hermes_fleet=false
system_install=false
defer_topology=false
target_user=
rmux_version=${RMUX_VERSION:-0.10.0}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --prefix) prefix=${2:?missing prefix}; shift 2 ;;
    --system) prefix=/usr/local; system_install=true; shift ;;
    --without-hermes) install_hermes=false; shift ;;
    --with-hermes-fleet) install_hermes_fleet=true; shift ;;
    --defer-topology) defer_topology=true; shift ;;
    --user) target_user=${2:?missing target user}; shift 2 ;;
    --rmux-version) rmux_version=${2:?missing RMUX version}; shift 2 ;;
    -h|--help)
      echo "usage: ./install.sh [--system] [--user USER] [--prefix PATH] [--without-hermes] [--with-hermes-fleet] [--defer-topology] [--rmux-version VERSION]"
      echo "  --with-hermes-fleet  Build and expose the four-profile dashboard through Tailscale Serve (system install only)"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ "$system_install" = true ] && [ "$(id -u)" -ne 0 ]; then
  echo "--system must be run as root (use sudo ./install.sh --system)" >&2
  exit 1
fi
if [ "$defer_topology" = true ] && [ "$system_install" != true ]; then
  echo "--defer-topology is only valid with --system" >&2
  exit 2
fi
if [ "$install_hermes_fleet" = true ] && [ "$system_install" != true ]; then
  echo "--with-hermes-fleet is only valid with --system" >&2
  exit 2
fi

if [ -z "$target_user" ]; then
  if [ "$system_install" = true ]; then
    target_user=${SUDO_USER:-}
    [ -n "$target_user" ] || {
      echo "--system needs --user USER when SUDO_USER is unavailable" >&2
      exit 2
    }
  else
    target_user=$(id -un)
  fi
fi
target_home=$(getent passwd "$target_user" | cut -d: -f6)
[ -n "$target_home" ] || { echo "unknown target user: $target_user" >&2; exit 2; }

install_root=$prefix/lib/agk-terminal
bin_dir=$prefix/bin

expose_agk_launcher() {
  local installed=$bin_dir/agk
  local shadow=$target_home/.local/bin/agk
  local backup=$shadow.agk-shadowed

  [ "$installed" != "$shadow" ] || return 0
  if [ "$(id -u)" -eq 0 ]; then
    install -d -m 0755 -o "$target_user" -g "$(id -gn "$target_user")" \
      "$target_home/.local/bin"
  else
    install -d -m 0755 "$target_home/.local/bin"
  fi
  if [ -L "$shadow" ] \
    && [ "$(readlink -f "$shadow" 2>/dev/null || true)" = "$(readlink -f "$installed")" ]
  then
    return 0
  fi
  if [ -e "$shadow" ] || [ -L "$shadow" ]; then
    if [ -e "$backup" ] || [ -L "$backup" ]; then
      backup=$backup.$(date -u +%Y%m%dT%H%M%SZ)
    fi
    mv "$shadow" "$backup"
    echo "Preserved shadowing AGK launcher: $backup"
  fi
  ln -s "$installed" "$shadow"
  if [ "$(id -u)" -eq 0 ]; then
    chown -h "$target_user:$(id -gn "$target_user")" "$shadow"
  fi
}

rmux_works_for_target() {
  local candidate=$1
  if [ "$(id -un)" = "$target_user" ]; then
    env HOME="$target_home" "$candidate" list-sessions >/dev/null 2>&1
  else
    sudo -u "$target_user" env HOME="$target_home" \
      "$candidate" list-sessions >/dev/null 2>&1
  fi
}

expose_working_rmux() {
  local candidate=$1 shadow=$target_home/.local/bin/rmux
  install -d -m 0755 "$install_root/bin"
  if [ "$candidate" != "$install_root/bin/rmux" ]; then
    ln -sfn "$candidate" "$install_root/bin/rmux"
  fi

  # A stale user-local dispatcher wins over /usr/bin in normal shells and can
  # speak an older wire protocol than the live daemon. Preserve it, then make
  # the user's direct `rmux` command resolve to the verified executable too.
  if [ -x "$shadow" ] && [ "$shadow" != "$candidate" ] \
    && ! rmux_works_for_target "$shadow"
  then
    if [ ! -e "$shadow.agk-incompatible" ]; then
      mv "$shadow" "$shadow.agk-incompatible"
    fi
    ln -sfn "$candidate" "$shadow"
    if [ "$(id -u)" -eq 0 ]; then
      chown -h "$target_user:$(id -gn "$target_user")" "$shadow"
    fi
    echo "Replaced incompatible user-local RMUX; backup: $shadow.agk-incompatible"
  fi
}

install_rmux() {
  local candidate
  for candidate in "$(command -v rmux || true)" /usr/bin/rmux \
    /usr/local/bin/rmux /usr/libexec/rmux/rmux
  do
    [ -x "$candidate" ] || continue
    if rmux_works_for_target "$candidate"; then
      "$candidate" -V
      expose_working_rmux "$candidate"
      return
    fi
  done
  command -v curl >/dev/null
  command -v sha256sum >/dev/null
  local machine archive url temporary sums
  machine=$(uname -m)
  case "$machine" in
    x86_64|amd64) machine=x86_64 ;;
    aarch64|arm64) machine=aarch64 ;;
    *) echo "unsupported RMUX architecture: $machine" >&2; return 1 ;;
  esac
  archive="rmux-$rmux_version-linux-$machine.tar.gz"
  url="https://github.com/Helvesec/rmux/releases/download/v$rmux_version"
  temporary=$(mktemp -d -t agk-rmux.XXXXXX)
  trap 'rm -rf "$temporary"' RETURN
  curl -fsSL "$url/$archive" -o "$temporary/$archive"
  curl -fsSL "$url/SHA256SUMS" -o "$temporary/SHA256SUMS"
  sums=$(awk -v archive="$archive" '$2 == archive || $2 == "*" archive {print}' "$temporary/SHA256SUMS")
  [ -n "$sums" ] || { echo "RMUX checksum is missing" >&2; return 1; }
  (cd "$temporary" && printf '%s\n' "$sums" | sha256sum -c -)
  tar -xzf "$temporary/$archive" -C "$temporary"
  local package_root
  package_root=$(find "$temporary" -mindepth 1 -maxdepth 2 -type f -name install.sh -printf '%h\n' | head -1)
  [ -n "$package_root" ] || { echo "RMUX package layout is invalid" >&2; return 1; }
  "$package_root/install.sh" --prefix "$prefix"
  rmux_works_for_target "$bin_dir/rmux" || {
    echo "installed RMUX cannot communicate with the target user's daemon" >&2
    return 1
  }
  expose_working_rmux "$bin_dir/rmux"
  rm -rf "$temporary"
  trap - RETURN
}

install_rmux
command -v python3 >/dev/null || { echo "Python 3 is required for AGK session commands" >&2; exit 1; }
if [ "$(id -un)" = "$target_user" ]; then
  cargo_bin=$(command -v cargo || true)
  [ -n "$cargo_bin" ] || { echo "Rust/Cargo is required to build the AGK TUI" >&2; exit 1; }
  cargo_target_dir=$target_home/.cache/agk-terminal/cargo-target
  mkdir -p "$cargo_target_dir"
  CARGO_TARGET_DIR="$cargo_target_dir" "$cargo_bin" build --locked --release --manifest-path "$repo_root/apps/agk-tui/Cargo.toml"
  agk_tui_binary=$cargo_target_dir/release/agk-tui
else
  cargo_bin=$target_home/.cargo/bin/cargo
  [ -x "$cargo_bin" ] || { echo "Rust/Cargo is required for $target_user" >&2; exit 1; }
  cargo_target_dir=$target_home/.cache/agk-terminal/cargo-target
  install -d -m 0700 -o "$target_user" -g "$(id -gn "$target_user")" \
    "$target_home/.cache/agk-terminal" "$cargo_target_dir"
  sudo -u "$target_user" env \
    HOME="$target_home" \
    CARGO_TARGET_DIR="$cargo_target_dir" \
    PATH="$target_home/.cargo/bin:/usr/local/bin:/usr/bin:/bin" \
    "$cargo_bin" build --locked --release \
      --manifest-path "$repo_root/apps/agk-tui/Cargo.toml"
  agk_tui_binary=$cargo_target_dir/release/agk-tui
fi

install -d -m 0755 "$install_root/bin" "$install_root/scripts" "$install_root/config" "$install_root/rmux" \
  "$install_root/client" \
  "$install_root/hermes/plugins/platforms" "$install_root/hermes/dashboard-themes" \
  "$install_root/agents" "$bin_dir"
install -m 0755 "$agk_tui_binary" "$install_root/bin/agk-tui"
install -m 0755 "$repo_root/scripts/agk_control.py" "$install_root/scripts/agk_control.py"
install -m 0755 "$repo_root/scripts/provider.sh" "$install_root/scripts/provider.sh"
install -m 0755 "$repo_root/scripts/doctor.sh" "$install_root/scripts/doctor.sh"
install -m 0755 "$repo_root/scripts/sync-hermes.sh" "$install_root/scripts/sync-hermes.sh"
install -m 0755 "$repo_root/scripts/sync-rules.py" "$install_root/scripts/sync-rules.py"
install -m 0755 "$repo_root/scripts/install-shared-hermes.sh" \
  "$install_root/scripts/install-shared-hermes.sh"
install -m 0755 "$repo_root/scripts/topology.py" "$install_root/scripts/topology.py"
install -m 0755 "$repo_root/scripts/composio_inventory.py" \
  "$install_root/scripts/composio_inventory.py"
install -m 0755 "$repo_root/scripts/gateway_watchdog.py" \
  "$install_root/scripts/gateway_watchdog.py"
install -m 0755 "$repo_root/scripts/client_control.py" \
  "$install_root/scripts/client_control.py"
install -m 0755 "$repo_root/scripts/install-hermes-fleet-dashboard.sh" \
  "$install_root/scripts/install-hermes-fleet-dashboard.sh"
install -m 0644 "$repo_root/config/topology.yaml" "$install_root/config/topology.yaml"
install -m 0644 "$repo_root/config/providers.yaml" "$install_root/config/providers.yaml"
install -m 0644 "$repo_root/config/rules.yaml" "$install_root/config/rules.yaml"
install -m 0644 "$repo_root/config/hermes.env.example" "$install_root/config/hermes.env.example"
rm -rf "$install_root/hermes/plugins/agentik_os" \
  "$install_root/hermes/plugins/platforms/discord"
cp -a "$repo_root/hermes/plugins/agentik_os" "$install_root/hermes/plugins/"
cp -a "$repo_root/hermes/plugins/platforms/discord" \
  "$install_root/hermes/plugins/platforms/"
install -m 0644 "$repo_root/hermes/dashboard-themes/agentik-shadcn.yaml" \
  "$install_root/hermes/dashboard-themes/agentik-shadcn.yaml"
install -m 0644 "$repo_root/hermes/dashboard-themes/agentik-shadcn-light.yaml" \
  "$install_root/hermes/dashboard-themes/agentik-shadcn-light.yaml"
cp -a "$repo_root/hermes/agents/master-os-builder" "$install_root/agents/"
rm -rf "$install_root/client"
cp -a "$repo_root/client" "$install_root/client"
install -m 0644 "$repo_root/rmux/rmux.conf" "$install_root/rmux/rmux.conf"
install -m 0755 "$repo_root/bin/agk" "$bin_dir/agk"
install -m 0755 "$repo_root/bin/agk-terminal" "$bin_dir/agk-terminal"
for client_launcher in client-init client-doctor client-status client-env provision-client; do
  install -m 0755 "$repo_root/bin/$client_launcher" "$bin_dir/$client_launcher"
done
expose_agk_launcher

# Make the Composio executable available to every profile without sharing any
# profile's credentials. Each Linux user still authenticates in its own HOME.
composio_bin=$(command -v composio || true)
if [ -z "$composio_bin" ] && [ -x "$target_home/.local/bin/composio" ]; then
  composio_bin=$target_home/.local/bin/composio
fi
if [ -n "$composio_bin" ]; then
  install -m 0755 "$composio_bin" "$install_root/bin/composio"
fi

if [ ! -x "$install_root/venv/bin/python" ]; then
  python3 -m venv "$install_root/venv"
fi
"$install_root/venv/bin/python" -m pip install --disable-pip-version-check \
  -r "$repo_root/requirements.txt"

if [ "$system_install" = true ]; then
  install -m 0644 "$repo_root/rmux/rmux.conf" /etc/rmux.conf
  install -d -m 0755 /etc/agk-terminal
  install -m 0644 "$repo_root/config/topology.yaml" /etc/agk-terminal/topology.yaml
  install -m 0644 "$repo_root/config/providers.yaml" /etc/agk-terminal/providers.yaml
  install -m 0644 "$repo_root/config/rules.yaml" /etc/agk-terminal/rules.yaml
  install -m 0644 "$repo_root/systemd/agk-topology-refresh.service" \
    /etc/systemd/system/agk-topology-refresh.service
  install -m 0644 "$repo_root/systemd/agk-topology-refresh.timer" \
    /etc/systemd/system/agk-topology-refresh.timer
  install -m 0644 "$repo_root/systemd/agk-gateway-watchdog.service" \
    /etc/systemd/system/agk-gateway-watchdog.service
  install -m 0644 "$repo_root/systemd/agk-gateway-watchdog.timer" \
    /etc/systemd/system/agk-gateway-watchdog.timer
  install -d -m 0755 "$install_root/systemd"
  install -m 0644 "$repo_root/systemd/hermes-dashboard.service.in" \
    "$install_root/systemd/hermes-dashboard.service.in"
  install -m 0644 "$repo_root/systemd/hermes-fleet.service.in" \
    "$install_root/systemd/hermes-fleet.service.in"
  systemctl daemon-reload
  systemctl enable --now agk-gateway-watchdog.timer
  if [ "$defer_topology" = false ]; then
    "$install_root/scripts/topology.py" apply --yes
    systemctl enable --now agk-topology-refresh.timer
  else
    echo "Topology activation deferred until shared Hermes is installed"
  fi
fi

export AGK_TERMINAL_ROOT=$install_root
export PATH="$bin_dir:$PATH"
run_for_target() {
  if [ "$(id -un)" = "$target_user" ]; then
    env \
      HOME="$target_home" \
      HERMES_HOME="$target_home/.hermes" \
      AGK_TERMINAL_ROOT="$install_root" \
      PATH="$target_home/.local/bin:$bin_dir:/usr/local/bin:/usr/bin:/bin" \
      "$@"
  else
    sudo -u "$target_user" env \
      HOME="$target_home" \
      HERMES_HOME="$target_home/.hermes" \
      AGK_TERMINAL_ROOT="$install_root" \
      PATH="$target_home/.local/bin:$bin_dir:/usr/local/bin:/usr/bin:/bin" \
      "$@"
  fi
}

rules_python=python3
if [ -x "$install_root/venv/bin/python" ]; then
  rules_python=$install_root/venv/bin/python
fi
run_for_target "$rules_python" "$install_root/scripts/sync-rules.py"

if [ "$install_hermes" = true ]; then
  run_for_target "$install_root/scripts/provider.sh" install hermes
fi
if [ "$system_install" = true ]; then
  for profile_user in operator agentik mission private; do
    profile_home=$(getent passwd "$profile_user" | cut -d: -f6)
    [ -n "$profile_home" ] || continue
    if sudo -u "$profile_user" env HOME="$profile_home" \
      PATH="$profile_home/.local/bin:$bin_dir:/usr/local/bin:/usr/bin:/bin" \
      hermes --version >/dev/null 2>&1
    then
      sudo -u "$profile_user" env \
        HOME="$profile_home" \
        HERMES_HOME="$profile_home/.hermes" \
        AGK_TERMINAL_ROOT="$install_root" \
        PATH="$profile_home/.local/bin:$bin_dir:/usr/local/bin:/usr/bin:/bin" \
        "$install_root/scripts/sync-hermes.sh"
    fi
    if [ -x "$install_root/bin/composio" ]; then
      sudo -u "$profile_user" env \
        HOME="$profile_home" \
        USER="$profile_user" \
        PATH="$install_root/bin:$profile_home/.local/bin:$bin_dir:/usr/local/bin:/usr/bin:/bin" \
        "$install_root/scripts/composio_inventory.py" refresh >/dev/null || true
    fi
  done
  # Mission may host the optional collective gateway as a second Hermes
  # context while remaining inside the same Linux runtime boundary.
  if [ -d /home/mission/.hermes/profiles/collective ]; then
    sudo -u mission env \
      HOME=/home/mission \
      HERMES_HOME=/home/mission/.hermes/profiles/collective \
      AGK_TERMINAL_ROOT="$install_root" \
      PATH="/home/mission/.local/bin:$bin_dir:/usr/local/bin:/usr/bin:/bin" \
      "$install_root/scripts/sync-hermes.sh"
  fi
  if [ "$install_hermes_fleet" = true ]; then
    "$install_root/scripts/install-hermes-fleet-dashboard.sh" \
      --source-root "$repo_root"
  fi
elif run_for_target hermes --version >/dev/null 2>&1; then
  run_for_target "$install_root/scripts/sync-hermes.sh"
else
  echo "Hermes extension sync skipped: Hermes is not installed for $target_user"
fi
run_for_target "$install_root/scripts/doctor.sh" || true

echo "AGK-TUI installed in $install_root"
echo "Open it with: $bin_dir/agk"
