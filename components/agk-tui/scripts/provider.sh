#!/usr/bin/env bash
set -euo pipefail

provider=${2:-}
action=${1:-list}
install_mode=${3:-}
hermes_home=${HERMES_HOME:-${HOME:?}/.hermes}

if [ -n "${STATION_WORKSTATION_ROOT:-}" ]; then
  workstation_component=${AGK_TERMINAL_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)}
  /usr/bin/python3 -I -S "$workstation_component/hermes/plugins/agentik_os/workstation.py" --validate >/dev/null || exit 2
  if [ "$action" = install ]; then
    echo 'Station Workstation owns pinned dependencies: use agentik-station repair --root PATH; model enrollment uses agentik-station model --root PATH. Installed CLIs retain their scoped login commands.' >&2
    exit 2
  fi
fi

installed() { command -v "$1" >/dev/null 2>&1; }

hermes_is_official() {
  installed hermes || return 1
  local install_dir origin
  install_dir=$(hermes --version 2>/dev/null | awk -F': ' '/^Install directory:/ {print $2; exit}')
  [ -n "$install_dir" ] && [ -d "$install_dir/.git" ] || return 1
  origin=$(git -c safe.directory="$install_dir" -C "$install_dir" remote get-url origin 2>/dev/null || true)
  [ "$origin" = "https://github.com/NousResearch/hermes-agent.git" ] \
    || [ "$origin" = "https://github.com/NousResearch/hermes-agent" ]
}

openrouter_ready() {
  [ -n "${OPENROUTER_API_KEY:-}" ] && return 0
  [ -f "$hermes_home/.env" ] || return 1
  awk -F= '/^[[:space:]]*OPENROUTER_API_KEY=/ {value=$0; sub(/^[^=]*=/, "", value); gsub(/^[[:space:]"'\'' ]+|[[:space:]"'\'' ]+$/, "", value); if (length(value)) found=1} END {exit !found}' "$hermes_home/.env"
}

claude_ready() {
  installed claude || return 1
  claude auth status 2>/dev/null | grep -F '"loggedIn": true' >/dev/null
}

codex_ready() {
  installed codex || return 1
  codex login status >/dev/null 2>&1
}

state() {
  local id=$1 binary=$2
  if [ "$id" = openrouter ]; then
    if ! installed hermes; then echo "NOT INSTALLED"; elif openrouter_ready; then echo READY; else echo "SETUP REQUIRED"; fi
  elif [ "$id" = claude ] && installed claude; then
    if claude_ready; then echo READY; else echo "SETUP REQUIRED"; fi
  elif [ "$id" = codex ] && installed codex; then
    if codex_ready; then echo READY; else echo "SETUP REQUIRED"; fi
  elif installed "$binary"; then
    echo READY
  else
    echo "NOT INSTALLED"
  fi
}

list() {
  printf '%-12s %-18s %s\n' PROVIDER COMMAND STATUS
  printf '%-12s %-18s %s\n' hermes hermes "$(state hermes hermes)"
  printf '%-12s %-18s %s\n' claude claude "$(state claude claude)"
  printf '%-12s %-18s %s\n' codex codex "$(state codex codex)"
  printf '%-12s %-18s %s\n' openrouter 'hermes --provider' "$(state openrouter hermes)"
  printf '%-12s %-18s %s\n' opencode opencode "$(state opencode opencode)"
}

verify() {
  case "$1" in
    hermes)
      hermes_is_official || {
        echo "Hermes is installed but is not the official NousResearch checkout" >&2
        return 1
      }
      hermes --version
      ;;
    claude) claude --version && claude_ready ;;
    codex) codex --version && codex_ready ;;
    openrouter) hermes_is_official; hermes --version; openrouter_ready ;;
    opencode) opencode --version ;;
    *) echo "unknown provider: $1" >&2; return 2 ;;
  esac
}

download_and_run() {
  local url=$1
  shift
  local installer
  installer=$(mktemp -t agk-provider-installer.XXXXXX)
  trap 'rm -f "$installer"' RETURN
  curl -fsSL "$url" -o "$installer"
  bash "$installer" "$@"
  rm -f "$installer"
  trap - RETURN
}

install_provider() {
  case "$1" in
    hermes)
      if hermes_is_official; then
        hermes --version
      else
        download_and_run https://hermes-agent.nousresearch.com/install.sh --skip-setup --non-interactive
        if [ "$install_mode" != "--no-login" ]; then
          hermes setup --quick
        fi
      fi
      ;;
    claude)
      if ! installed claude; then download_and_run https://claude.ai/install.sh; fi
      if [ "$install_mode" != "--no-login" ]; then
        claude_ready || claude auth login
      fi
      ;;
    codex)
      if ! installed codex; then download_and_run https://chatgpt.com/codex/install.sh; fi
      if [ "$install_mode" != "--no-login" ]; then
        codex_ready || codex login
      fi
      ;;
    openrouter)
      installed hermes || install_provider hermes
      if [ "$install_mode" = "--no-login" ] || openrouter_ready; then
        hermes --version
      else
        hermes setup model
      fi
      ;;
    opencode)
      if ! installed opencode; then download_and_run https://opencode.ai/install; fi
      opencode --version
      ;;
    *)
      echo "unknown provider: $1" >&2
      return 2
      ;;
  esac
}

verify_installed() {
  case "$1" in
    hermes|openrouter) hermes_is_official; hermes --version ;;
    claude) claude --version ;;
    codex) codex --version ;;
    opencode) opencode --version ;;
    *) echo "unknown provider: $1" >&2; return 2 ;;
  esac
}

case "$action" in
  list) list ;;
  verify) [ -n "$provider" ] || { echo "usage: provider.sh verify PROVIDER" >&2; exit 2; }; verify "$provider" ;;
  install)
    [ -n "$provider" ] || { echo "usage: provider.sh install PROVIDER [--no-login]" >&2; exit 2; }
    [ -z "$install_mode" ] || [ "$install_mode" = "--no-login" ] || {
      echo "unknown install option: $install_mode" >&2
      exit 2
    }
    install_provider "$provider"
    if [ "$install_mode" = "--no-login" ]; then
      verify_installed "$provider"
    else
      verify "$provider"
    fi
    if { [ "$provider" = hermes ] || [ "$provider" = openrouter ]; } \
      && [ -x "${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}/scripts/sync-hermes.sh" ]
    then
      "${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}/scripts/sync-hermes.sh"
    fi
    ;;
  *) echo "usage: provider.sh {list|verify|install} [provider]" >&2; exit 2 ;;
esac
