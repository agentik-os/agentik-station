#!/usr/bin/env bash
set -Eeuo pipefail

STATION_USER="agk-station"
STATION_HOME="/home/${STATION_USER}"
REPO_DIR="${STATION_HOME}/repos/agentik-station"
SUDO_MODE="passwordless"
MODE="full"
HOST_ID=""
ORGANIZATION=""
PROJECT=""
ENVIRONMENT="development"
YES=0
INSTALL_HERMES=1
INSTALL_CODEX=1
INSTALL_AGK_TUI=1

usage(){ cat <<'USAGE'
Agentik Station host bootstrap

Run from the cloned Agentik Station repository with sudo/root:
  sudo ./bootstrap.sh --mode full
  sudo ./bootstrap.sh --mode team --organization organization-alpha --project platform

Options:
  --mode full|team
  --host-id ID
  --organization ID        required in team mode
  --project ID             optional in team mode
  --env development|staging|production
  --sudo-mode passwordless|password
  --skip-hermes
  --skip-codex
  --skip-agk-tui
  --yes

Creates the dedicated sudo account `agk-station`. Source and user tools live under
/home/agk-station, while Station operational state uses /etc, /opt, /srv, /var and /run.
Nothing is installed into /root except the shell history of the administrator who invoked this command.
USAGE
}

while (($#)); do
  case "$1" in
    --mode) MODE="$2"; shift 2;;
    --host-id) HOST_ID="$2"; shift 2;;
    --organization) ORGANIZATION="$2"; shift 2;;
    --project) PROJECT="$2"; shift 2;;
    --env) ENVIRONMENT="$2"; shift 2;;
    --sudo-mode) SUDO_MODE="$2"; shift 2;;
    --skip-hermes) INSTALL_HERMES=0; shift;;
    --skip-codex) INSTALL_CODEX=0; shift;;
    --skip-agk-tui) INSTALL_AGK_TUI=0; shift;;
    --yes) YES=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 2;;
  esac
done

[[ "${EUID}" -eq 0 ]] || { echo 'ERROR: run with sudo or as root.' >&2; exit 2; }
[[ "$MODE" == full || "$MODE" == team ]] || { echo 'ERROR: --mode must be full or team.' >&2; exit 2; }
[[ "$SUDO_MODE" == passwordless || "$SUDO_MODE" == password ]] || { echo 'ERROR: invalid --sudo-mode.' >&2; exit 2; }
if [[ "$MODE" == team && -z "$ORGANIZATION" ]]; then echo 'ERROR: --organization is required in team mode.' >&2; exit 2; fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$source_root" == /root || "$source_root" == /root/* ]]; then
  echo "ERROR: do not bootstrap from /root. Clone the repository under /tmp/agentik-station, then run sudo ./bootstrap.sh from there." >&2
  exit 2
fi
[[ -x "$source_root/station" ]] || { echo 'ERROR: run this from the Agentik Station repository.' >&2; exit 2; }

if [[ "$YES" -ne 1 ]]; then
  cat <<EOF
Bootstrap plan
  account:      ${STATION_USER}
  home:         ${STATION_HOME}
  repository:   ${REPO_DIR}
  mode:         ${MODE}
  Hermes:       $([[ $INSTALL_HERMES -eq 1 ]] && echo install || echo skip)
  Codex:        $([[ $INSTALL_CODEX -eq 1 ]] && echo install || echo skip)
  AGK-TUI:      $([[ $INSTALL_AGK_TUI -eq 1 ]] && echo install || echo skip)
  sudo policy:  ${SUDO_MODE}
EOF
  read -r -p 'Continue? [y/N] ' answer
  [[ "$answer" =~ ^([yY]|yes|YES)$ ]] || { echo 'Cancelled.'; exit 0; }
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git curl ca-certificates xz-utils sudo rsync jq unzip build-essential nodejs npm

if ! id "$STATION_USER" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$STATION_HOME" --shell /bin/bash --groups sudo --comment "Agk-Station" "$STATION_USER"
else
  usermod -aG sudo "$STATION_USER"
fi
install -d -m 0750 -o "$STATION_USER" -g "$STATION_USER" "$STATION_HOME/repos" "$STATION_HOME/.local/bin" "$STATION_HOME/.local/share/npm" "$STATION_HOME/.config"

sudoers="/etc/sudoers.d/${STATION_USER}"
if [[ "$SUDO_MODE" == passwordless ]]; then
  printf '%s ALL=(ALL:ALL) NOPASSWD: ALL\n' "$STATION_USER" > "$sudoers"
  chmod 0440 "$sudoers"
  visudo -cf "$sudoers" >/dev/null
else
  rm -f "$sudoers"
  echo "INFO: set a password for ${STATION_USER} before relying on interactive sudo: passwd ${STATION_USER}" >&2
fi

# Keep the working source out of /root even if the initial clone happened there.
mkdir -p "$REPO_DIR"
rsync -a --delete --exclude '.pytest_cache' --exclude '__pycache__' --exclude '*.pyc' "$source_root/" "$REPO_DIR/"
chown -R "$STATION_USER:$STATION_USER" "$REPO_DIR"
command -v loginctl >/dev/null 2>&1 && loginctl enable-linger "$STATION_USER" || true

# Stable user-local PATH without touching root's profile.
profile="$STATION_HOME/.profile"
touch "$profile"; chown "$STATION_USER:$STATION_USER" "$profile"
for line in 'export PATH="$HOME/.local/bin:$HOME/.local/share/npm/bin:$PATH"' 'export NPM_CONFIG_PREFIX="$HOME/.local/share/npm"'; do
  grep -Fqx "$line" "$profile" || echo "$line" >> "$profile"
done

if [[ "$INSTALL_HERMES" -eq 1 ]]; then
  tmp="$(mktemp)"
  curl --fail --silent --show-error --location https://hermes-agent.nousresearch.com/install.sh --output "$tmp"
  chmod 0755 "$tmp"
  # Execute the downloaded upstream installer as the dedicated account, never as root.
  sudo -u "$STATION_USER" -H env HERMES_HOME="$STATION_HOME/.hermes" bash "$tmp" --skip-setup --non-interactive
  rm -f "$tmp"
fi

if [[ "$INSTALL_CODEX" -eq 1 ]]; then
  sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$HOME/.local/share/npm/bin:$PATH"; export NPM_CONFIG_PREFIX="$HOME/.local/share/npm"; npm install -g @openai/codex'
fi

# AGK-TUI (RMUX session control plane) — vendored under components/agk-tui
if [[ "$INSTALL_AGK_TUI" -eq 1 ]]; then
  agk_src="$REPO_DIR/components/agk-tui"
  [[ -x "$agk_src/install.sh" ]] || { echo "ERROR: missing $agk_src/install.sh" >&2; exit 2; }
  # Rust toolchain for building the native TUI (user-local, not under /root).
  if [[ ! -x "$STATION_HOME/.cargo/bin/cargo" ]]; then
    tmp="$(mktemp)"
    curl --proto '=https' --tlsv1.2 --fail --silent --show-error -o "$tmp" https://sh.rustup.rs
    chown "$STATION_USER:$STATION_USER" "$tmp"
    sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" CARGO_HOME="$STATION_HOME/.cargo" \
      RUSTUP_HOME="$STATION_HOME/.rustup" sh "$tmp" -y --profile minimal
    rm -f "$tmp"
  fi
  if command -v apt-get >/dev/null 2>&1; then
    env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
      build-essential pkg-config libssl-dev ca-certificates curl git jq unzip >/dev/null
  fi
  hermes_flag=()
  [[ "$INSTALL_HERMES" -eq 1 ]] && hermes_flag+=(--without-hermes)
  sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" \
    PATH="$STATION_HOME/.cargo/bin:$STATION_HOME/.local/bin:$PATH" \
    CARGO_HOME="$STATION_HOME/.cargo" RUSTUP_HOME="$STATION_HOME/.rustup" \
    bash "$agk_src/install.sh" --prefix "$STATION_HOME/.local" "${hermes_flag[@]}"
fi
# Run Station from the dedicated account; sudo elevation happens only for the apply stage inside station.sh.
args=(bootstrap --mode "$MODE" --yes)
[[ -n "$HOST_ID" ]] && args+=(--host-id "$HOST_ID")
if [[ "$MODE" == team ]]; then
  args+=(--organization "$ORGANIZATION" --env "$ENVIRONMENT")
  [[ -n "$PROJECT" ]] && args+=(--project "$PROJECT")
fi
sudo -u "$STATION_USER" -H -- "$REPO_DIR/station.sh" "${args[@]}"

mkdir -p /etc/station
hermes_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$HOME/.local/share/npm/bin:$PATH"; hermes --version 2>/dev/null || true' | head -1)"
codex_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$HOME/.local/share/npm/bin:$PATH"; codex --version 2>/dev/null || true' | head -1)"
pin_version="$(cat "$REPO_DIR/components/agk-tui/PIN" 2>/dev/null || true)"
jq -n --arg user "$STATION_USER" --arg hermes "$hermes_version" --arg codex "$codex_version" --arg repo "$REPO_DIR" --arg mode "$MODE" --arg pin "$pin_version" '{station_user:$user,hermes:$hermes,codex:$codex,agk_tui:$pin,claude:"",agk_tui_pin:$pin,repository:$repo,mode:$mode}' > /etc/station/bootstrap-tools.json
chmod 0640 /etc/station/bootstrap-tools.json

# Sync Station metadata into AGK home (best-effort).
sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" PATH="$STATION_HOME/.local/bin:$PATH" \
  python3 "$REPO_DIR/scripts/station_agk_sync.py" || true

cat <<EOF

AGK Station bootstrap complete.

Dedicated account: ${STATION_USER}
Repository:        ${REPO_DIR}

Next login (Agk-Station session — dedicated sudo account, not root):
  sudo -iu ${STATION_USER}
  cd ${REPO_DIR}

Verify tools:
  hermes doctor
  codex --version
  ./station.sh doctor
  ./station.sh status
  agk doctor         # AGK-TUI / RMUX

Live sessions (Hermes, Codex, Claude Code, terminal):
  agk
  station tui

Authentication remains operator-controlled:
  hermes setup
  codex              # follow the current sign-in flow
  # Claude Code: install/login separately, then open via agk
EOF
