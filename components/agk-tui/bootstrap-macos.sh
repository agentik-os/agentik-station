#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
dry_run=false
skip_packages=false
core_only=false
prefix=${AGK_TUI_PREFIX:-$HOME/.local}
rmux_version=${RMUX_VERSION:-0.10.0}

usage() {
  cat <<'EOF'
AGK-TUI macOS bootstrap

Usage:
  ./bootstrap-macos.sh [--dry-run] [--skip-packages] [--core-only]

Options:
  --core-only      Skip optional Claude Code, Codex and OpenCode installation
  --skip-packages  Require preinstalled Rust and uv instead of installing them
  --dry-run        Print the installation plan without changing the Mac
  -h, --help       Show this help
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=true; shift ;;
    --skip-packages) skip_packages=true; shift ;;
    --core-only) core_only=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

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

phase "Validate this Mac"
if [ "$(uname -s)" != Darwin ]; then
  echo "bootstrap-macos.sh supports macOS only" >&2
  exit 1
fi
case "$(uname -m)" in
  arm64|x86_64) ;;
  *) echo "unsupported macOS architecture: $(uname -m)" >&2; exit 1 ;;
esac
if [ "$dry_run" = false ] && [ "$(id -u)" -eq 0 ]; then
  echo "Run the macOS installer as your normal user, without sudo." >&2
  exit 1
fi
for command in curl tar awk shasum install; do
  command -v "$command" >/dev/null || {
    echo "required macOS command is missing: $command" >&2
    exit 1
  }
done
if ! xcode-select -p >/dev/null 2>&1; then
  if [ "$dry_run" = true ]; then
    echo "  + xcode-select --install (then rerun this bootstrap)"
  else
    xcode-select --install || true
    echo "Complete the Command Line Tools dialog, then rerun the AGK installer." >&2
    exit 1
  fi
else
  echo "  = preserve existing Command Line Tools"
fi

bin_dir=$prefix/bin
install_root=$prefix/lib/agk-terminal
cache_root=${XDG_CACHE_HOME:-$HOME/.cache}/agk-tui
temporary=
cleanup() {
  if [ -n "${temporary:-}" ] && [ -d "$temporary" ]; then
    rm -rf -- "$temporary"
  fi
}
trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

phase "Install the Rust toolchain"
if command -v cargo >/dev/null 2>&1; then
  echo "  = preserve existing Rust toolchain"
elif [ "$skip_packages" = true ]; then
  echo "Rust/Cargo is required when --skip-packages is used" >&2
  exit 1
elif [ "$dry_run" = true ]; then
  echo "  + official rustup minimal profile -> $HOME/.cargo"
else
  temporary=$(mktemp -d -t agk-macos-rust.XXXXXX)
  curl --proto '=https' --tlsv1.2 -fsSL https://sh.rustup.rs -o "$temporary/rustup.sh"
  sh "$temporary/rustup.sh" -y --profile minimal
  cleanup
  temporary=
fi
export PATH="$bin_dir:$HOME/.cargo/bin:$PATH"

phase "Install uv and a private Python runtime"
if command -v uv >/dev/null 2>&1; then
  echo "  = preserve existing uv installation"
elif [ "$skip_packages" = true ]; then
  echo "uv is required when --skip-packages is used" >&2
  exit 1
elif [ "$dry_run" = true ]; then
  echo "  + official uv installer -> $bin_dir"
else
  temporary=$(mktemp -d -t agk-macos-uv.XXXXXX)
  curl --proto '=https' --tlsv1.2 -fsSL https://astral.sh/uv/install.sh \
    -o "$temporary/uv-install.sh"
  env UV_INSTALL_DIR="$bin_dir" UV_NO_MODIFY_PATH=1 sh "$temporary/uv-install.sh"
  cleanup
  temporary=
fi
run mkdir -p "$bin_dir" "$install_root" "$cache_root"
run uv python install 3.12
run uv venv --python 3.12 "$install_root/venv"
run uv pip install --python "$install_root/venv/bin/python" \
  --disable-pip-version-check -r "$repo_root/requirements.txt"

phase "Install the verified RMUX release"
if command -v rmux >/dev/null 2>&1 \
  && [ "$(rmux -V 2>/dev/null || true)" = "rmux $rmux_version" ] \
  && rmux list-sessions >/dev/null 2>&1
then
  echo "  = preserve compatible RMUX: $(rmux -V 2>/dev/null || true)"
elif [ "$dry_run" = true ]; then
  echo "  + RMUX $rmux_version signed release for macOS -> $prefix"
else
  machine=$(uname -m)
  case "$machine" in
    arm64) machine=aarch64 ;;
    x86_64) machine=x86_64 ;;
  esac
  archive="rmux-$rmux_version-macos-$machine.tar.gz"
  release_url="https://github.com/Helvesec/rmux/releases/download/v$rmux_version"
  temporary=$(mktemp -d -t agk-macos-rmux.XXXXXX)
  curl --proto '=https' --tlsv1.2 --retry 3 -fsSL \
    "$release_url/$archive" -o "$temporary/$archive"
  curl --proto '=https' --tlsv1.2 --retry 3 -fsSL \
    "$release_url/SHA256SUMS" -o "$temporary/SHA256SUMS"
  checksum=$(awk -v archive="$archive" '$2 == archive || $2 == "*" archive {print}' \
    "$temporary/SHA256SUMS")
  [ -n "$checksum" ] || { echo "RMUX checksum is missing for $archive" >&2; exit 1; }
  (cd "$temporary" && printf '%s\n' "$checksum" | shasum -a 256 -c -)
  tar -xzf "$temporary/$archive" -C "$temporary"
  package_installer=$(find "$temporary" -type f -name install.sh -print | head -n 1)
  [ -n "$package_installer" ] || { echo "RMUX package layout is invalid" >&2; exit 1; }
  bash "$package_installer" --prefix "$prefix"
  cleanup
  temporary=
  "$repo_root/scripts/repair-rmux-daemon.sh" "$bin_dir/rmux"
fi

phase "Build and stage AGK-TUI"
if [ "$dry_run" = true ]; then
  echo "  + cargo build --locked --release (native macOS target)"
else
  cargo build --locked --release --manifest-path "$repo_root/apps/agk-tui/Cargo.toml"
fi
run mkdir -p \
  "$install_root/bin" "$install_root/scripts" "$install_root/config" \
  "$install_root/rmux" "$install_root/client" \
  "$install_root/hermes/plugins/platforms" \
  "$install_root/agents" "$bin_dir"
run install -m 0755 "$repo_root/apps/agk-tui/target/release/agk-tui" \
  "$install_root/bin/agk-tui"
for script in agk_control.py provider.sh doctor.sh sync-hermes.sh topology.py composio_inventory.py client_control.py; do
  run install -m 0755 "$repo_root/scripts/$script" "$install_root/scripts/$script"
done
for config in topology.yaml providers.yaml rules.yaml hermes.env.example; do
  run install -m 0644 "$repo_root/config/$config" "$install_root/config/$config"
done
run rm -rf -- "$install_root/client"
run cp -R "$repo_root/client" "$install_root/client"
run install -m 0644 "$repo_root/rmux/rmux.conf" "$install_root/rmux/rmux.conf"
run install -m 0755 "$repo_root/bin/agk" "$bin_dir/agk"
run install -m 0755 "$repo_root/bin/agk-terminal" "$bin_dir/agk-terminal"
for client_launcher in client-init client-doctor client-status client-env provision-client; do
  run install -m 0755 "$repo_root/bin/$client_launcher" "$bin_dir/$client_launcher"
done
restrict_plugin_modes() {
  # Copied public software must not inherit group/world write from a checkout.
  # Restrict existing modes only; never traverse symlink entries or HOME/config.
  find "$@" \( -type d -o -type f \) -exec chmod go-w {} +
}
if [ "$dry_run" = true ]; then
  echo "  + synchronize Hermes plugins and Master OS Builder catalog"
else
  rm -rf -- "$install_root/hermes/plugins/agentik_os" \
    "$install_root/hermes/plugins/platforms/discord" \
    "$install_root/agents/master-os-builder"
  cp -R "$repo_root/hermes/plugins/agentik_os" "$install_root/hermes/plugins/"
  cp -R "$repo_root/hermes/plugins/platforms/discord" \
    "$install_root/hermes/plugins/platforms/"
  restrict_plugin_modes "$install_root/hermes/plugins/agentik_os" \
    "$install_root/hermes/plugins/platforms/discord"
  cp -R "$repo_root/hermes/agents/master-os-builder" "$install_root/agents/"
  mkdir -p "$HOME/.config/rmux"
  if [ ! -e "$HOME/.config/rmux/rmux.conf" ]; then
    install -m 0644 "$repo_root/rmux/rmux.conf" "$HOME/.config/rmux/rmux.conf"
  fi
fi

phase "Install Hermes, Composio and optional providers"
export AGK_TERMINAL_ROOT=$install_root
export HERMES_HOME=${HERMES_HOME:-$HOME/.hermes}
if command -v composio >/dev/null 2>&1; then
  echo "  = preserve existing Composio CLI"
elif [ "$dry_run" = true ]; then
  echo "  + official Composio CLI -> current macOS profile"
else
  temporary=$(mktemp -d -t agk-macos-composio.XXXXXX)
  curl --proto '=https' --tlsv1.2 -fsSL https://composio.dev/install \
    -o "$temporary/composio-install.sh"
  env COMPOSIO_INSTALL_SHELL=none sh "$temporary/composio-install.sh"
  cleanup
  temporary=
fi
if [ "$dry_run" = true ]; then
  echo "  + official Hermes + AGK extensions (authentication deferred)"
else
  "$install_root/scripts/provider.sh" install hermes --no-login
fi
if [ "$core_only" = false ]; then
  if [ "$dry_run" = true ]; then
    echo "  + Claude Code + Codex + OpenCode (authentication deferred)"
  else
    for provider in claude codex opencode; do
      "$install_root/scripts/provider.sh" install "$provider" --no-login
    done
  fi
fi

phase "Expose AGK in future zsh sessions"
path_line='export PATH="$HOME/.local/bin:$PATH"'
zprofile=${ZDOTDIR:-$HOME}/.zprofile
if [ "$prefix" = "$HOME/.local" ]; then
  if [ "$dry_run" = true ]; then
    echo "  + ensure ~/.local/bin is exported from $zprofile"
  elif ! grep -Fqx "$path_line" "$zprofile" 2>/dev/null; then
    mkdir -p "$(dirname "$zprofile")"
    printf '\n# AGK-TUI\n%s\n' "$path_line" >>"$zprofile"
  fi
fi

phase "Verify the native installation"
if [ "$dry_run" = true ]; then
  echo "  + rmux -V"
  echo "  + agk --help"
  echo "  + agk provider list"
else
  rmux -V
  "$bin_dir/agk" --help >/dev/null
  "$bin_dir/agk" provider list
fi

cat <<EOF

AGK-TUI macOS installation complete.

Open a new Terminal, then run:
  agk

Finish only the accounts you use:
  hermes setup
  agk composio login
  claude auth login
  codex login

Installation root: $install_root
EOF
