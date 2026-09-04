#!/usr/bin/env bash
set -euo pipefail

install_root=${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}
failed=0
hermes_home=${HERMES_HOME:-$HOME/.hermes}
export PATH="$HOME/.local/bin:$install_root/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

check() {
  local name=$1
  shift
  if "$@" >/dev/null 2>&1; then
    printf '✓ %s\n' "$name"
  else
    printf '✗ %s\n' "$name"
    failed=1
  fi
}

discord_connected() {
  python3 - "$hermes_home/gateway_state.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    state = json.load(handle)
discord = state.get("platforms", {}).get("discord", {})
raise SystemExit(
    0
    if state.get("gateway_state") == "running"
    and discord.get("state") == "connected"
    and not discord.get("error_code")
    else 1
)
PY
}

composio_authenticated() {
  python3 - "$HOME/.composio/user_data.json" <<'PY'
import json
import sys

try:
    value = json.load(open(sys.argv[1], encoding="utf-8")).get("api_key")
except (OSError, ValueError, AttributeError):
    raise SystemExit(1)
raise SystemExit(0 if isinstance(value, str) and value.strip() else 1)
PY
}

portal_authenticated() {
  hermes portal info 2>/dev/null | grep -F '✓ logged in' >/dev/null
}

portal_ready_for_selected_provider() {
  local provider
  provider=$(python3 - "$hermes_home/config.yaml" <<'PY'
import sys
import yaml

try:
    config = yaml.safe_load(open(sys.argv[1], encoding="utf-8")) or {}
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
model = config.get("model") or {}
print(str(model.get("provider") or "nous").strip().lower())
PY
  ) || return 1
  [ "$provider" != nous ] || portal_authenticated
}

check 'RMUX binary' rmux -V
check 'RMUX daemon' rmux list-sessions
check 'AGK TUI' test -x "$install_root/bin/agk-tui"
check 'AGK controller' test -x "$install_root/scripts/agk_control.py"
check 'Global rules registry' test -r "$install_root/config/rules.yaml"
check 'Claude global rules' grep -Fq '<!-- AGK MANAGED RULES: START -->' "$HOME/.claude/CLAUDE.md"
check 'Codex global rules' grep -Fq '<!-- AGK MANAGED RULES: START -->' "$HOME/.codex/AGENTS.md"
check 'OpenCode global rules' grep -Fq '<!-- AGK MANAGED RULES: START -->' "$HOME/.config/opencode/AGENTS.md"
check 'Hermes plugin' hermes plugins doctor --ci "$hermes_home/plugins/agentik_os"
check 'AGK Discord plugin' hermes plugins doctor --ci "$hermes_home/plugins/platforms/discord"
check 'Master OS Builder' test -f "$hermes_home/agents/master-os-builder/agent.yaml"
check 'Official Hermes' "$install_root/scripts/provider.sh" verify hermes
check 'Hermes configuration' hermes config check
check 'Nous Portal authentication (when selected)' portal_ready_for_selected_provider
check 'Discord gateway' discord_connected
check 'Agentik OS cloud' curl -fsSIL --max-time 10 https://agentik-os.com
check 'Chrome browser engine' google-chrome --version
check 'Claude Code' "$install_root/scripts/provider.sh" verify claude
check 'Codex' "$install_root/scripts/provider.sh" verify codex
check 'OpenCode' "$install_root/scripts/provider.sh" verify opencode
check 'OpenRouter' "$install_root/scripts/provider.sh" verify openrouter
check 'Composio CLI' composio --version
check 'Composio authentication' composio_authenticated

"$install_root/scripts/provider.sh" list
exit "$failed"
