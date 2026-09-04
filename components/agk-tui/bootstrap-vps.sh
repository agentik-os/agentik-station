#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
dry_run=false
skip_packages=false
core_only=false
profiles=(operator agentik mission private)
install_root=/usr/local/lib/agk-terminal

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=true; shift ;;
    --skip-packages) skip_packages=true; shift ;;
    --core-only) core_only=true; shift ;;
    -h|--help)
      echo "usage: sudo ./bootstrap-vps.sh [--dry-run] [--skip-packages] [--core-only]"
      exit 0
      ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

if [ "$dry_run" = false ] && [ "$(id -u)" -ne 0 ]; then
  echo "bootstrap-vps.sh must run as root (use sudo)" >&2
  exit 1
fi

phase() { printf '\n==> %s\n' "$1"; }
run() {
  if [ "$dry_run" = true ]; then
    printf '  +'
    printf ' %q' "$@"
    printf '\n'
  else
    "$@"
  fi
}

phase "Validate a supported fresh Linux host"
if [ "$dry_run" = true ]; then
  echo "  + require Linux x86_64 or aarch64 at apply time"
else
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64|Linux-aarch64) ;;
    *) echo "AGK fresh bootstrap supports Linux x86_64 and aarch64" >&2; exit 1 ;;
  esac
fi
if [ "$skip_packages" = false ]; then
  command -v apt-get >/dev/null || {
    echo "automatic package provisioning currently supports Debian/Ubuntu (apt-get)" >&2
    exit 1
  }
  run apt-get update
  run env DEBIAN_FRONTEND=noninteractive apt-get install -y \
    build-essential ca-certificates curl git jq nodejs npm pkg-config \
    python3 python3-pip python3-venv sudo unzip libssl-dev
fi

phase "Create or preserve the four Linux runtime boundaries"
for profile in "${profiles[@]}"; do
  if id "$profile" >/dev/null 2>&1; then
    echo "  = preserve existing user $profile"
  else
    run useradd --create-home --shell /bin/bash --user-group "$profile"
  fi
  run install -d -m 0700 -o "$profile" -g "$profile" "/home/$profile"
  if command -v loginctl >/dev/null 2>&1; then
    run loginctl enable-linger "$profile"
  fi
done

phase "Install the current Rust toolchain for the AGK TUI builder"
if [ ! -x /home/operator/.cargo/bin/cargo ]; then
  if [ "$dry_run" = true ]; then
    echo "  + official rustup installer -> /home/operator/.cargo"
  else
    rustup_installer=$(mktemp -t agk-rustup.XXXXXX)
    trap 'rm -f "$rustup_installer"' EXIT
    curl --proto '=https' --tlsv1.2 -fsS https://sh.rustup.rs -o "$rustup_installer"
    chown operator:operator "$rustup_installer"
    sudo -u operator env HOME=/home/operator CARGO_HOME=/home/operator/.cargo \
      RUSTUP_HOME=/home/operator/.rustup sh "$rustup_installer" -y --profile minimal
    rm -f "$rustup_installer"
    trap - EXIT
  fi
else
  echo "  = preserve existing Operator Rust toolchain"
fi

phase "Install uv once for the shared official Hermes runtime"
if ! command -v uv >/dev/null 2>&1; then
  if [ "$dry_run" = true ]; then
    echo "  + official uv installer -> /usr/local/bin"
  else
    uv_installer=$(mktemp -t agk-uv.XXXXXX)
    trap 'rm -f "$uv_installer"' EXIT
    curl -LsSf https://astral.sh/uv/install.sh -o "$uv_installer"
    env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh "$uv_installer"
    rm -f "$uv_installer"
    trap - EXIT
  fi
else
  echo "  = preserve existing uv installation"
fi

phase "Install the Composio CLI independently for every profile"
if [ "$dry_run" = true ]; then
  for profile in "${profiles[@]}"; do
    echo "  + official Composio CLI -> /home/$profile/.composio (credentials remain local)"
  done
else
  composio_installer=$(mktemp -t agk-composio.XXXXXX)
  trap 'rm -f "$composio_installer"' EXIT
  curl -fsSL https://composio.dev/install -o "$composio_installer"
  for profile in "${profiles[@]}"; do
    sudo -u "$profile" env \
      HOME="/home/$profile" \
      USER="$profile" \
      SHELL=/bin/bash \
      COMPOSIO_INSTALL_SHELL=none \
      sh "$composio_installer"
  done
  rm -f "$composio_installer"
  trap - EXIT
fi

phase "Stage AGK-TUI without activating topology prematurely"
if [ "$dry_run" = true ]; then
  echo "  + $repo_root/install.sh --system --user operator --without-hermes --defer-topology"
else
  sudo -u operator test -r "$repo_root/apps/agk-tui/Cargo.toml" || {
    echo "Operator cannot read the repository at $repo_root" >&2
    echo "Clone or copy it to an operator-readable path before running the bootstrap." >&2
    exit 1
  }
  "$repo_root/install.sh" --system --user operator --without-hermes --defer-topology
fi

phase "Install one shared official Hermes checkout and synchronize extensions"
if [ "$dry_run" = true ]; then
  echo "  + official NousResearch Hermes -> /opt/agk-terminal/hermes-agent"
  echo "  + Agentik OS, Discord and Master OS Builder -> four profile homes"
else
  AGK_TERMINAL_ROOT="$install_root" \
    "$install_root/scripts/install-shared-hermes.sh"
fi

phase "Apply profile topology and stable Hermes runtime identities"
if [ "$dry_run" = true ]; then
  echo "  + TopologyManager apply: operator agentik mission private"
else
  "$install_root/scripts/topology.py" apply --yes
  systemctl daemon-reload
  systemctl enable --now agk-topology-refresh.timer
  for profile in "${profiles[@]}"; do
    sudo -u "$profile" env \
      HOME="/home/$profile" \
      HERMES_HOME="/home/$profile/.hermes" \
      PATH="/home/$profile/.local/bin:/usr/local/bin:/usr/bin:/bin" \
      hermes config set runtime_identity.machine_id agk-core >/dev/null
    sudo -u "$profile" env \
      HOME="/home/$profile" \
      HERMES_HOME="/home/$profile/.hermes" \
      PATH="/home/$profile/.local/bin:/usr/local/bin:/usr/bin:/bin" \
      hermes config set runtime_identity.environment_id "$profile" >/dev/null
  done
fi

phase "Initialize the client-organization control plane without external writes"
if [ "$dry_run" = true ]; then
  echo "  + mission: agk client bootstrap --upgrade (0 clients provisioned)"
else
  sudo -u mission env \
    HOME=/home/mission \
    USER=mission \
    AGK_TERMINAL_ROOT="$install_root" \
    PATH="/home/mission/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    /usr/local/bin/agk client bootstrap --upgrade
fi

if [ "$core_only" = false ]; then
  phase "Install optional provider binaries for every profile"
  if [ "$dry_run" = true ]; then
    echo "  + Claude Code + Codex + OpenCode for operator/agentik/mission/private"
  else
    for profile in "${profiles[@]}"; do
      for provider in claude codex opencode; do
        sudo -u "$profile" env \
          HOME="/home/$profile" \
          HERMES_HOME="/home/$profile/.hermes" \
          AGK_TERMINAL_ROOT="$install_root" \
          PATH="/home/$profile/.local/bin:/usr/local/bin:/usr/bin:/bin" \
          "$install_root/scripts/provider.sh" install "$provider" --no-login
      done
    done
  fi
fi

phase "Verify local services and public control-plane reachability"
if [ "$dry_run" = true ]; then
  echo "  + agk topology status"
  echo "  + HTTPS https://agentik-os.com"
else
  "$install_root/scripts/topology.py" status
  curl -fsSIL --max-time 15 https://agentik-os.com >/dev/null
  sudo -u operator env \
    HOME=/home/operator \
    HERMES_HOME=/home/operator/.hermes \
    PATH="/home/operator/.local/bin:/usr/local/bin:/usr/bin:/bin" \
    "$install_root/scripts/doctor.sh" || true
fi

cat <<'EOF'

AGK fresh-VPS bootstrap complete.

Credentials were not copied. Complete each profile explicitly:
  sudo -u <profile> -H hermes portal
  sudo -u <profile> -H agk composio connect <toolkit> --no-browser
  sudo -u <profile> -H agk hermes gateway install --force --start-now

Open the control plane with: agk
EOF
