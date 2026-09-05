#!/usr/bin/env bash
set -euo pipefail

usage() {
  printf '%s\n' 'usage: agk doctor [--offline|--full]' \
    '  --offline  Static installation inventory; no runtime, account or service probes.' \
    '  --full     Existing strict runtime/integration checks (default; may contact services).'
}

# Parse before HOME/PATH resolution or any installed-code initialization.
mode=full
if [ "$#" -gt 1 ]; then
  usage >&2
  exit 2
fi
case "${1:---full}" in
  --offline) mode=offline ;;
  --full) ;;
  -h|--help) usage; exit 0 ;;
  *) usage >&2; exit 2 ;;
esac

if [ "$mode" = offline ]; then
  # Do not import the component venv (including .pth startup hooks), execute
  # installed binaries, or load account/runtime state. This is NOT acceptance.
  exec /usr/bin/python3 -I -S - "${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}" <<'PY'
import os
from pathlib import Path
import signal
import stat
import sys

LIMIT = 1024 * 1024
root = Path(sys.argv[1])
failed = False


def expired(_signum, _frame):
    print("FAIL: installation inventory exceeded its 10-second budget", flush=True)
    raise SystemExit(1)


signal.signal(signal.SIGALRM, expired)
signal.alarm(10)
print("SCOPE: INSTALLATION_ONLY (static file inventory)", flush=True)
print("NOT_CHECKED: executable behavior, dependency imports, configuration semantics, TUI rendering")
print("NOT_CHECKED: RMUX daemon/protocol, Hermes/provider authentication, Discord/chat, external services")


def bounded_text(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= LIMIT:
            raise ValueError("invalid inventory file")
        with os.fdopen(fd, "rb", closefd=False) as handle:
            data = handle.read(LIMIT + 1)
        if not data or len(data) > LIMIT:
            raise ValueError("invalid inventory file")
        return data.decode("utf-8")
    finally:
        os.close(fd)


def executable(path):
    # Native RMUX and venv Python legitimately use installed symlinks.
    info = path.stat()
    return stat.S_ISREG(info.st_mode) and info.st_size > 0 and os.access(path, os.X_OK)


def directories(path, maximum):
    result = []
    with os.scandir(path) as entries:
        for count, entry in enumerate(entries, 1):
            if count > maximum:
                raise ValueError("inventory directory limit")
            if entry.is_dir(follow_symlinks=False):
                result.append(Path(entry.path))
    return result


def dependency(name, version, module):
    # Read only fixed distribution metadata and package source, never import it.
    for library in (root / "venv/lib", root / "venv/Lib"):
        if not library.is_dir():
            continue
        if library.name == "Lib":
            sites = [library / "site-packages"]
        else:
            sites = [item / "site-packages" for item in directories(library, 32)
                     if item.name.startswith("python3.")]
        for site in sites:
            if not site.is_dir():
                continue
            for entry in directories(site, 512):
                if entry.name.lower() != f"{name.lower()}-{version}.dist-info":
                    continue
                fields = bounded_text(entry / "METADATA").splitlines()
                if f"Name: {name}" not in fields or f"Version: {version}" not in fields:
                    raise ValueError("distribution metadata mismatch")
                return bool(bounded_text(site / module).strip())
    return False


def check(label, probe):
    global failed
    try:
        present = probe()
    except (OSError, ValueError, UnicodeError):
        present = False
    print(f"{'PASS' if present else 'FAIL'}: {label}", flush=True)
    failed |= not present


prefix = root.parent.parent
for label, path in (
    ("AGK launcher file", prefix / "bin/agk"),
    ("AGK dispatcher file", prefix / "bin/agk-terminal"),
    ("native AGK TUI file", root / "bin/agk-tui"),
    ("AGK controller file", root / "scripts/agk_control.py"),
    ("provider dispatcher file", root / "scripts/provider.sh"),
    ("RMUX executable file", root / "bin/rmux"),
    ("component Python executable file", root / "venv/bin/python"),
):
    check(label, lambda path=path: executable(path))
for filename in ("rules.yaml", "providers.yaml", "topology.yaml"):
    check(f"bundled {filename} readable/nonempty",
          lambda filename=filename: bool(bounded_text(root / "config" / filename).strip()))
check("venv configuration readable/nonempty", lambda: bool(bounded_text(root / "venv/pyvenv.cfg").strip()))
check("PyYAML 6.0.3 distribution files", lambda: dependency("PyYAML", "6.0.3", "yaml/__init__.py"))
check("Pillow 12.3.0 distribution files", lambda: dependency("pillow", "12.3.0", "PIL/Image.py"))
print("RESULT: INSTALLATION_FILES_MISSING_OR_INVALID" if failed else "RESULT: INSTALLATION_FILES_PRESENT")
print("Next: verify TUI/RMUX in a terminal, then explicitly configured accounts/services; agk doctor --full is strict.")
raise SystemExit(1 if failed else 0)
PY
fi

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
