#!/usr/bin/env bash
set -Eeuo pipefail
export PYTHONDONTWRITEBYTECODE=1

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
PLAN_ONLY=0
ACKNOWLEDGE_INCOMPLETE=""
INSTALL_HERMES=1
INSTALL_HERMES_AUTO_UPDATE=1
INSTALL_CODEX=1
INSTALL_AGK_TUI=1
INSTALL_TOOLCHAIN=1
INSTALL_AI_STACK=0
INSTALL_VOICE=1
INSTALL_SCRAPEGRAPHAI=1
INSTALL_CRAWL4AI=1

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
  --plan                  validate and show the complete plan without Host changes
  --acknowledge-incomplete ATTEMPT
                          start a reviewed fresh run after inspecting that failed attempt
  --skip-hermes
  --skip-hermes-auto-update
  --skip-codex
  --skip-toolchain         skip Python/Node/GitHub/Vercel/Composio/Codex/shadcn toolchain
  --skip-agk-tui
  --skip-voice           skip Hermes voice extras and local Parakeet service
  --with-ai-stack        install all optional pinned AI services/clients/plugins
  --skip-scrapegraphai   skip the default Hermes web-extraction tool and Chromium browser
  --skip-crawl4ai        skip the default Hermes Markdown extraction tool
  --yes

Creates the dedicated sudo account `agk-station`. Source and user tools live under
/home/agk-station, while Station operational state uses /etc, /opt, /srv, /var and /run.
Nothing is installed into /root except the shell history of the administrator who invoked this command.
USAGE
}

while (($#)); do
  case "$1" in
    --mode|--host-id|--organization|--project|--env|--sudo-mode|--acknowledge-incomplete)
      [[ $# -ge 2 && -n "$2" && "$2" != --* ]] || {
        echo "ERROR: $1 requires a value." >&2; exit 2;
      };;
  esac
  case "$1" in
    --mode) MODE="$2"; shift 2;;
    --host-id) HOST_ID="$2"; shift 2;;
    --organization) ORGANIZATION="$2"; shift 2;;
    --project) PROJECT="$2"; shift 2;;
    --env) ENVIRONMENT="$2"; shift 2;;
    --sudo-mode) SUDO_MODE="$2"; shift 2;;
    --plan) PLAN_ONLY=1; shift;;
    --acknowledge-incomplete) ACKNOWLEDGE_INCOMPLETE="$2"; shift 2;;
    --skip-hermes) INSTALL_HERMES=0; INSTALL_HERMES_AUTO_UPDATE=0; INSTALL_VOICE=0; shift;;
    --skip-hermes-auto-update) INSTALL_HERMES_AUTO_UPDATE=0; shift;;
    --skip-codex) INSTALL_CODEX=0; shift;;
    --skip-toolchain) INSTALL_TOOLCHAIN=0; INSTALL_CODEX=0; INSTALL_SCRAPEGRAPHAI=0; INSTALL_CRAWL4AI=0; shift;;
    --skip-agk-tui) INSTALL_AGK_TUI=0; shift;;
    --skip-voice) INSTALL_VOICE=0; shift;;
    --with-ai-stack) INSTALL_AI_STACK=1; shift;;
    --skip-scrapegraphai) INSTALL_SCRAPEGRAPHAI=0; shift;;
    --skip-crawl4ai) INSTALL_CRAWL4AI=0; shift;;
    --yes) YES=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "Unknown option: $1" >&2; usage; exit 2;;
  esac
done

[[ "${EUID}" -eq 0 || "$PLAN_ONLY" -eq 1 ]] || { echo 'ERROR: run with sudo; use --plan for unprivileged preflight.' >&2; exit 2; }
[[ "$MODE" == full || "$MODE" == team ]] || { echo 'ERROR: --mode must be full or team.' >&2; exit 2; }
[[ "$SUDO_MODE" == passwordless || "$SUDO_MODE" == password ]] || { echo 'ERROR: invalid --sudo-mode.' >&2; exit 2; }
[[ -z "$ACKNOWLEDGE_INCOMPLETE" || "$ACKNOWLEDGE_INCOMPLETE" =~ ^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$ ]] || {
  echo 'ERROR: invalid incomplete bootstrap attempt identifier.' >&2; exit 2;
}
[[ "$INSTALL_AI_STACK" -eq 0 || "$INSTALL_TOOLCHAIN" -eq 1 ]] || {
  echo 'ERROR: --with-ai-stack requires the Station toolchain; remove --skip-toolchain.' >&2
  exit 2
}
[[ "$INSTALL_AI_STACK" -eq 0 || ( "$INSTALL_HERMES" -eq 1 && "$INSTALL_VOICE" -eq 1 ) ]] || {
  echo 'ERROR: --with-ai-stack requires Hermes and the default voice stack.' >&2
  exit 2
}
[[ "$INSTALL_AI_STACK" -eq 0 || ( "$INSTALL_SCRAPEGRAPHAI" -eq 1 && "$INSTALL_CRAWL4AI" -eq 1 ) ]] || {
  echo 'ERROR: --with-ai-stack conflicts with --skip-scrapegraphai or --skip-crawl4ai.' >&2
  exit 2
}
if [[ "$MODE" == team && -z "$ORGANIZATION" ]]; then echo 'ERROR: --organization is required in team mode.' >&2; exit 2; fi

source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ "$source_root" == /root || "$source_root" == /root/* ]]; then
  echo "ERROR: do not bootstrap from /root. Clone into your non-root user's workspace, then run sudo ./bootstrap.sh from there." >&2
  exit 2
fi
[[ -x "$source_root/station" ]] || { echo 'ERROR: run this from the Agentik Station repository.' >&2; exit 2; }

# Validate before apt, account/sudo edits, source copies, or upstream installers.
command -v python3 >/dev/null || { echo 'ERROR: distribution Python 3.11+ is required for preflight.' >&2; exit 2; }
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else "ERROR: Python 3.11+ is required")'
"$source_root/station" doctor --repo
python3 "$source_root/scripts/station_bootstrap_preflight.py"

bootstrap_plan_dir="$(mktemp -d /tmp/station-bootstrap-plan.XXXXXX)"
bootstrap_spec="$bootstrap_plan_dir/install-spec.json"
cleanup_bootstrap_plan(){ rm -f -- "$bootstrap_spec"; rmdir -- "$bootstrap_plan_dir"; }
trap cleanup_bootstrap_plan EXIT
plan_args=(--mode "$MODE")
[[ -z "$HOST_ID" ]] || plan_args+=(--host-id "$HOST_ID")
if [[ "$MODE" == team ]]; then
  plan_args+=(--organization "$ORGANIZATION" --env "$ENVIRONMENT")
  [[ -z "$PROJECT" ]] || plan_args+=(--project "$PROJECT")
else
  [[ -z "$ORGANIZATION" && -z "$PROJECT" && "$ENVIRONMENT" == development ]] || {
    echo 'ERROR: organization/project/environment options require --mode team.' >&2; exit 2;
  }
fi
"$source_root/station.sh" spec "${plan_args[@]}" --output "$bootstrap_spec" >/dev/null
echo '==> Typed kernel plan — this exact InstallSpec will be applied'
"$source_root/station" plan --spec "$bootstrap_spec"

distro_id=$(awk -F= '$1 == "ID" {gsub(/"/, "", $2); print $2}' /etc/os-release)
distro_codename=$(awk -F= '$1 == "VERSION_CODENAME" {gsub(/"/, "", $2); print $2}' /etc/os-release)
[[ "$distro_id" =~ ^(ubuntu|debian)$ && "$distro_codename" =~ ^[a-z][a-z0-9-]+$ ]] || {
  echo 'ERROR: Tailscale package repository requires a supported Ubuntu/Debian codename.' >&2; exit 2;
}
cat <<EOF
Additional bootstrap operations (outside the kernel InstallSpec)
  distro:       ${distro_id}/${distro_codename}
  account:      ${STATION_USER}
  home:         ${STATION_HOME}
  repository:   ${REPO_DIR}
  mode:         ${MODE}
  Hermes:       $([[ $INSTALL_HERMES -eq 1 ]] && echo install || echo skip)
  Hermes update:$([[ $INSTALL_HERMES_AUTO_UPDATE -eq 1 ]] && echo ' weekly backup/Doctor timer' || echo ' disabled')
  Codex:        $([[ $INSTALL_CODEX -eq 1 ]] && echo install || echo skip)
  Toolchain:    $([[ $INSTALL_TOOLCHAIN -eq 1 ]] && echo install || echo skip)
  AGK-TUI:      $([[ $INSTALL_AGK_TUI -eq 1 ]] && echo install || echo skip)
  Voice:        $([[ $INSTALL_VOICE -eq 1 ]] && echo 'OpenAI audio + local Parakeet' || echo skip)
  ScrapeGraphAI:$([[ $INSTALL_SCRAPEGRAPHAI -eq 1 ]] && echo 'install + Playwright Chromium' || echo skip)
  Crawl4AI:     $([[ $INSTALL_CRAWL4AI -eq 1 ]] && echo 'install + Markdown tool' || echo skip)
  AI stack:     $([[ $INSTALL_AI_STACK -eq 1 ]] && echo install-all || echo optional)
  sudo policy:  ${SUDO_MODE}
  packages:     apt dependencies + signed Tailscale repository
  enrollment:   human-owned; no provider credentials or bot tokens created
EOF
if [[ "$PLAN_ONLY" -eq 1 ]]; then echo 'PLAN_ONLY: no Host changes applied.'; exit 0; fi
if [[ "$YES" -ne 1 ]]; then
  read -r -p 'Continue? [y/N] ' answer
  [[ "$answer" =~ ^([yY]|yes|YES)$ ]] || { echo 'Cancelled.'; exit 0; }
fi

bootstrap_state(){ python3 "$source_root/scripts/station_bootstrap_state.py" "$@"; }
# Python creates and validates private ancestors and the regular, single-link
# lock before the shell opens it. The inherited descriptor is checked again
# before fcntl acquires it. Children may close inherited descriptors (sudo does),
# so interrupted attempts still require inspecting surviving installer processes.
bootstrap_lock_path="$(bootstrap_state prepare)"
[[ "$bootstrap_lock_path" == /run/station/bootstrap/bootstrap.lock ]] || { echo 'ERROR: unexpected bootstrap lock path.' >&2; exit 2; }
exec 9<>"$bootstrap_lock_path"
bootstrap_state acquire --fd 9
# State may have changed while the human reviewed the plan; recheck under lock.
"$source_root/station" doctor --repo
python3 "$source_root/scripts/station_bootstrap_preflight.py"
bootstrap_state_args=(begin --spec "$bootstrap_spec" --source "$source_root"
  --option "mode=$MODE" --option "sudo_mode=$SUDO_MODE"
  --option "hermes=$INSTALL_HERMES" --option "hermes_auto_update=$INSTALL_HERMES_AUTO_UPDATE"
  --option "codex=$INSTALL_CODEX" --option "agk_tui=$INSTALL_AGK_TUI"
  --option "toolchain=$INSTALL_TOOLCHAIN" --option "ai_stack=$INSTALL_AI_STACK"
  --option "voice=$INSTALL_VOICE" --option "scrapegraphai=$INSTALL_SCRAPEGRAPHAI"
  --option "crawl4ai=$INSTALL_CRAWL4AI")
[[ -z "$ACKNOWLEDGE_INCOMPLETE" ]] || bootstrap_state_args+=(--acknowledge "$ACKNOWLEDGE_INCOMPLETE")
bootstrap_attempt="$(bootstrap_state "${bootstrap_state_args[@]}")"
echo "BOOTSTRAP_ATTEMPT=$bootstrap_attempt"
echo "BOOTSTRAP_RECEIPT=/var/lib/station/bootstrap/attempts/$bootstrap_attempt.json"
bootstrap_interrupted=0
bootstrap_finished=0
bootstrap_checkpoint(){ bootstrap_state checkpoint --attempt "$bootstrap_attempt" --stage "$1" --status "$2" "${@:3}"; }
finish_bootstrap(){
  local original_rc=$?
  trap - EXIT INT TERM HUP
  set +e
  if [[ "$bootstrap_finished" -eq 0 ]]; then
    local finish_args=(finish --attempt "$bootstrap_attempt" --exit-code "$original_rc")
    [[ "$bootstrap_interrupted" -eq 0 ]] || finish_args+=(--interrupted)
    bootstrap_state "${finish_args[@]}" || echo 'ERROR: final bootstrap checkpoint could not be recorded; inspect the last durable stage.' >&2
  fi
  cleanup_bootstrap_plan
  exit "$original_rc"
}
trap finish_bootstrap EXIT
trap 'bootstrap_interrupted=1; exit 130' INT
trap 'bootstrap_interrupted=1; exit 143' TERM
trap 'bootstrap_interrupted=1; exit 129' HUP

bootstrap_checkpoint system-packages running
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git curl ca-certificates xz-utils sudo rsync jq unzip build-essential \
  python3 python3-venv python3-yaml python3-dev pkg-config libssl-dev libffi-dev \
  podman ffmpeg libopus0 portaudio19-dev
bootstrap_checkpoint system-packages success

# Install at least the reviewed Tailscale stable version through its signed
# distro repository. Enrollment remains a human-owned external setup gate.
bootstrap_checkpoint tailscale running
source "$source_root/config/versions.lock"
tailscale_key=$(mktemp)
curl --fail --silent --show-error --location \
  "https://pkgs.tailscale.com/${TAILSCALE_TRACK}/${distro_id}/${distro_codename}.noarmor.gpg" \
  --output "$tailscale_key"
printf '%s  %s\n' "$TAILSCALE_APT_KEY_SHA256" "$tailscale_key" | sha256sum --check --status || {
  echo 'ERROR: Tailscale apt signing key checksum drifted; review upstream before continuing.' >&2
  rm -f "$tailscale_key"
  exit 2
}
install -d -m 0755 /usr/share/keyrings
install -m 0644 "$tailscale_key" /usr/share/keyrings/tailscale-archive-keyring.gpg
rm -f "$tailscale_key"
printf 'deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/%s/%s %s main\n' \
  "$TAILSCALE_TRACK" "$distro_id" "$distro_codename" \
  > /etc/apt/sources.list.d/tailscale.list
apt-get update
installed_tailscale=$(dpkg-query -W -f='${Version}' tailscale 2>/dev/null || true)
if [[ -z "$installed_tailscale" ]] || dpkg --compare-versions "$installed_tailscale" lt "$TAILSCALE_MIN_VERSION"; then
  apt-get install -y --no-install-recommends "tailscale=${TAILSCALE_MIN_VERSION}"
fi
systemctl enable --now tailscaled
tailscale version | head -1
bootstrap_checkpoint tailscale success

bootstrap_checkpoint operator-account running
if ! id "$STATION_USER" >/dev/null 2>&1; then
  useradd --create-home --home-dir "$STATION_HOME" --shell /bin/bash --groups sudo --comment "Agk-Station" "$STATION_USER"
else
  usermod -aG sudo "$STATION_USER"
fi
# install -d only applies ownership to explicit operands, not intermediate
# parents. A root-owned .local prevents uv/npm from creating share/lib below it.
install -d -m 0750 -o "$STATION_USER" -g "$STATION_USER" \
  "$STATION_HOME/repos" "$STATION_HOME/.local" "$STATION_HOME/.local/bin" \
  "$STATION_HOME/.local/share" "$STATION_HOME/.local/lib" "$STATION_HOME/.config"
bootstrap_checkpoint operator-account success

bootstrap_checkpoint operator-sudo running
sudoers="/etc/sudoers.d/${STATION_USER}"
if [[ "$SUDO_MODE" == passwordless ]]; then
  printf '%s ALL=(ALL:ALL) NOPASSWD: ALL\n' "$STATION_USER" > "$sudoers"
  chmod 0440 "$sudoers"
  visudo -cf "$sudoers" >/dev/null
else
  rm -f "$sudoers"
  echo "INFO: set a password for ${STATION_USER} before relying on interactive sudo: passwd ${STATION_USER}" >&2
fi
bootstrap_checkpoint operator-sudo success

# Keep the working source out of /root even if the initial clone happened there.
bootstrap_checkpoint operator-checkout running
mkdir -p "$REPO_DIR"
if [[ "$source_root" != "$REPO_DIR" ]]; then
  # Preflight rejects a nonempty destination; never delete an operator's work.
  rsync -a --exclude '.pytest_cache' --exclude '__pycache__' --exclude '*.pyc' "$source_root/" "$REPO_DIR/"
fi
chown -R "$STATION_USER:$STATION_USER" "$REPO_DIR"
command -v loginctl >/dev/null 2>&1 && loginctl enable-linger "$STATION_USER" || true
bootstrap_checkpoint operator-checkout success

# Stable user-local PATH without touching root's profile.
bootstrap_checkpoint operator-profile running
profile="$STATION_HOME/.profile"
touch "$profile"; chown "$STATION_USER:$STATION_USER" "$profile"
for line in 'export PATH="$HOME/.local/bin:$PATH"' 'export NPM_CONFIG_PREFIX="$HOME/.local"'; do
  grep -Fqx "$line" "$profile" || echo "$line" >> "$profile"
done
bootstrap_checkpoint operator-profile success

if [[ "$INSTALL_HERMES" -eq 1 ]]; then
  bootstrap_checkpoint hermes running
  # shellcheck disable=SC1091
  source "$source_root/config/versions.lock"
  tmp="$(mktemp)"
  curl --fail --silent --show-error --location "$HERMES_INSTALL_URL" --output "$tmp"
  printf '%s  %s\n' "$HERMES_INSTALL_SHA256" "$tmp" | sha256sum --check --status || {
    echo 'ERROR: Hermes installer checksum drifted; review upstream and update the lock intentionally.' >&2
    rm -f "$tmp"
    exit 2
  }
  chmod 0755 "$tmp"
  hermes_install_dir="/opt/station/tools/hermes/current"
  hermes_python_dir="/opt/station/tools/hermes/python"
  install -d -m 0755 -o "$STATION_USER" -g "$STATION_USER" \
    /opt/station/tools/hermes "$hermes_python_dir" "$hermes_python_dir/bin"
  # Execute the downloaded upstream installer as the dedicated account, pinned to the reviewed release commit.
  # Its interpreter must be shared executable code, not a symlink into the
  # private operator home. Credentials and caches remain in the owning home.
  sudo -u "$STATION_USER" -H env HERMES_HOME="$STATION_HOME/.hermes" \
    UV_PYTHON_INSTALL_DIR="$hermes_python_dir" UV_PYTHON_BIN_DIR="$hermes_python_dir/bin" \
    UV_PYTHON_PREFERENCE=only-managed bash "$tmp" \
    --dir "$hermes_install_dir" --branch main --commit "$HERMES_COMMIT" --skip-setup --non-interactive
  [[ -x "$STATION_HOME/.local/bin/hermes" ]] || { echo 'ERROR: Hermes launcher was not created.' >&2; exit 2; }
  install -m 0755 -o root -g root "$STATION_HOME/.local/bin/hermes" /usr/local/bin/hermes
  rm -f "$tmp"
  bootstrap_checkpoint hermes success
fi

if [[ "$INSTALL_TOOLCHAIN" -eq 1 ]]; then
  bootstrap_checkpoint toolchain running
  toolchain_args=(--install)
  [[ "$INSTALL_CODEX" -eq 0 ]] && toolchain_args+=(--without-codex)
  [[ "$INSTALL_HERMES" -eq 0 ]] && toolchain_args+=(--without-hermes)
  STATION_USER="$STATION_USER" STATION_HOME="$STATION_HOME" \
    "$REPO_DIR/scripts/station_toolchain_install.sh" "${toolchain_args[@]}"
  bootstrap_checkpoint toolchain success
fi

if [[ "$INSTALL_SCRAPEGRAPHAI" -eq 1 ]]; then
  bootstrap_checkpoint scrapegraphai running
  STATION_USER="$STATION_USER" STATION_HOME="$STATION_HOME" \
    "$REPO_DIR/scripts/station_deps_install.sh" --component scrapegraphai
  bootstrap_checkpoint scrapegraphai success
fi

if [[ "$INSTALL_CRAWL4AI" -eq 1 ]]; then
  bootstrap_checkpoint crawl4ai running
  STATION_USER="$STATION_USER" STATION_HOME="$STATION_HOME" \
    "$REPO_DIR/scripts/station_deps_install.sh" --component crawl4ai
  bootstrap_checkpoint crawl4ai success
fi

if [[ "$INSTALL_VOICE" -eq 1 ]]; then
  bootstrap_checkpoint voice running
  hermes_uv="$STATION_HOME/.local/bin/uv"
  [[ -x "$hermes_uv" ]] || hermes_uv="$STATION_HOME/.hermes/bin/uv"
  [[ -x "$hermes_uv" ]] || { echo 'ERROR: uv is required to install Hermes voice dependencies.' >&2; exit 2; }
  [[ -x "$hermes_install_dir/venv/bin/python" ]] || { echo 'ERROR: Hermes virtual environment is missing.' >&2; exit 2; }
  sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" HERMES_HOME="$STATION_HOME/.hermes" \
    "$hermes_uv" pip install --python "$hermes_install_dir/venv/bin/python" \
    --editable "${hermes_install_dir}[voice,messaging]"
  sudo -u "$STATION_USER" -H "$hermes_install_dir/venv/bin/python" -c \
    'import discord, numpy, sounddevice; print("Hermes voice and messaging dependencies OK")'
  bootstrap_checkpoint voice success
fi

# AGK-TUI (RMUX session control plane) — vendored under components/agk-tui
if [[ "$INSTALL_AGK_TUI" -eq 1 ]]; then
  bootstrap_checkpoint agk-tui running
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
  # Bootstrap owns Hermes installation, including an explicit decision to skip it.
  sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" \
    PATH="$STATION_HOME/.cargo/bin:$STATION_HOME/.local/bin:$PATH" \
    CARGO_HOME="$STATION_HOME/.cargo" RUSTUP_HOME="$STATION_HOME/.rustup" \
    bash "$agk_src/install.sh" --prefix "$STATION_HOME/.local" --without-hermes
  bootstrap_checkpoint agk-tui success
fi
# Apply the exact reviewed spec using the already authorized bootstrap identity.
# This must not depend on the newly created operator having a sudo password.
bootstrap_checkpoint kernel-apply running
"$REPO_DIR/station" apply --spec "$bootstrap_spec"
bootstrap_checkpoint kernel-apply success
bootstrap_checkpoint kernel-readback running
"$REPO_DIR/station" doctor --full --record
"$REPO_DIR/station" status
"$REPO_DIR/station" setup
bootstrap_checkpoint kernel-readback success

# Runtime services are installed only after Station has reconciled the
# canonical Zones and systemd units. Parakeet is default voice infrastructure;
# the rest of the larger AI stack remains explicit.
if [[ "$INSTALL_AI_STACK" -eq 1 ]]; then
  bootstrap_checkpoint ai-stack running
  STATION_USER="$STATION_USER" STATION_HOME="$STATION_HOME" \
    "$REPO_DIR/scripts/station_deps_install.sh" --all
  bootstrap_checkpoint ai-stack success
elif [[ "$INSTALL_VOICE" -eq 1 ]]; then
  bootstrap_checkpoint parakeet running
  STATION_USER="$STATION_USER" STATION_HOME="$STATION_HOME" \
    "$REPO_DIR/scripts/station_deps_install.sh" --component parakeet
  bootstrap_checkpoint parakeet success
fi

if [[ "$INSTALL_HERMES" -eq 1 ]]; then
  bootstrap_checkpoint guided-setup running
  "$REPO_DIR/scripts/station_guided_setup_enable.sh" --if-enrolled
  bootstrap_checkpoint guided-setup success
fi

# Do not start an updater while the initial installation is still incomplete.
if [[ "$INSTALL_HERMES_AUTO_UPDATE" -eq 1 ]]; then
  bootstrap_checkpoint hermes-update-timer running
  STATION_USER="$STATION_USER" STATION_HOME="$STATION_HOME" \
    "$REPO_DIR/scripts/station_deps_install.sh" --enable-hermes-auto-update
  bootstrap_checkpoint hermes-update-timer success
fi

bootstrap_checkpoint tool-inventory running
mkdir -p /etc/station
hermes_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$HOME/.local/share/npm/bin:$PATH"; hermes --version 2>/dev/null || true' | head -1)"
codex_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$HOME/.local/share/npm/bin:$PATH"; codex --version 2>/dev/null || true' | head -1)"
python_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$PATH"; python-latest --version 2>/dev/null || true' | head -1)"
python_ai_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$PATH"; python-ai --version 2>/dev/null || true' | head -1)"
node_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$PATH"; node --version 2>/dev/null || true' | head -1)"
github_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$PATH"; gh --version 2>/dev/null || true' | head -1)"
vercel_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$PATH"; vercel --version 2>/dev/null || true' | head -1)"
composio_version="$(sudo -u "$STATION_USER" -H bash -lc 'export PATH="$HOME/.local/bin:$PATH"; composio --version 2>/dev/null || true' | head -1)"
pin_version="$(cat "$REPO_DIR/components/agk-tui/PIN" 2>/dev/null || true)"
jq -n --arg user "$STATION_USER" --arg hermes "$hermes_version" --arg codex "$codex_version" \
  --arg python "$python_version" --arg python_ai "$python_ai_version" --arg node "$node_version" --arg github "$github_version" \
  --arg vercel "$vercel_version" --arg composio "$composio_version" --arg repo "$REPO_DIR" \
  --arg mode "$MODE" --arg pin "$pin_version" \
  '{station_user:$user,hermes:$hermes,codex:$codex,python:$python,python_ai:$python_ai,node:$node,github_cli:$github,vercel_cli:$vercel,composio_cli:$composio,agk_tui:$pin,claude:"",agk_tui_pin:$pin,repository:$repo,mode:$mode,external_auth:"NOT_CONFIGURED"}' \
  > /etc/station/bootstrap-tools.json
chmod 0640 /etc/station/bootstrap-tools.json
bootstrap_checkpoint tool-inventory success

# Sync Station metadata into AGK home (best-effort).
bootstrap_checkpoint agk-metadata-sync running
if python3 -B "$REPO_DIR/scripts/station_agk_sync.py" --export | \
  sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" PATH="$STATION_HOME/.local/bin:$PATH" \
    python3 -B "$REPO_DIR/scripts/station_agk_sync.py" --from-stdin; then
  bootstrap_checkpoint agk-metadata-sync success
else
  sync_rc=$?
  bootstrap_checkpoint agk-metadata-sync failed --exit-code "$sync_rc"
  echo 'WARNING: AGK metadata sync failed; the bootstrap receipt includes its repair action.' >&2
fi

bootstrap_state finish --attempt "$bootstrap_attempt" --exit-code 0
bootstrap_finished=1

cat <<EOF

AGK Station bootstrap complete.

Dedicated account: ${STATION_USER}
Repository:        ${REPO_DIR}

Next login (Agk-Station session — dedicated sudo account, not root):
  sudo -iu ${STATION_USER}
  cd ${REPO_DIR}

Verify tools:
  hermes doctor
  systemctl status station-parakeet.service --no-pager
  ./scripts/station_toolchain_install.sh --check
  python-ai --version
  codex --version
  gh auth status
  vercel whoami
  composio --version
  ./station.sh doctor
  ./station.sh status
  agk doctor         # AGK-TUI / RMUX

Live sessions (Hermes, Codex, Claude Code, terminal):
  agk
  station tui

Authentication remains operator-controlled:
  hermes setup
  codex              # follow the current sign-in flow
  gh auth login
  vercel login
  composio login && composio setup --target auto
  # Claude Code: install/login separately, then open via agk
  ./scripts/station_hermes_update.sh update
  ./scripts/station_deps_install.sh --list
  hermes gateway setup   # multi-platform bots
  # After Tailscale enrollment: sudo ./scripts/station_guided_setup_enable.sh
EOF
