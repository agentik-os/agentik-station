#!/usr/bin/env bash
set -euo pipefail

[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
install_root=${AGK_TERMINAL_ROOT:-/usr/local/lib/agk-terminal}
official_dir=${HERMES_OFFICIAL_DIR:-/opt/agk-terminal/hermes-agent}
official_commit=${HERMES_OFFICIAL_COMMIT:-}
bootstrap_home=${HERMES_BOOTSTRAP_HOME:-/var/lib/agk-terminal/hermes-bootstrap}
official_python_dir=${HERMES_PYTHON_DIR:-/opt/agk-terminal/python}
browser_home=${HERMES_BROWSER_HOME:-/opt/agk-terminal/browser-home}
reuse_official=${HERMES_REUSE_OFFICIAL:-false}
migration_root=${AGK_MIGRATION_ROOT:-/srv/agk/migrations}
stamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_dir=$migration_root/$stamp
users=(operator agentik mission private)
discord_state=(
  discord_threads.json
  gateway/discord_command_sync_state.json
  gateway/discord_message_recovery.db
  gateway/discord_nonconversational_messages.json
  gateway_state.json
)

case "$official_dir" in ""|/) echo "unsafe official directory" >&2; exit 2 ;; esac
install -d -m 0700 "$backup_dir"
install -d -m 0755 "$bootstrap_home" "$official_python_dir" "$browser_home"

for user_name in "${users[@]}"; do
  home_dir=$(getent passwd "$user_name" | cut -d: -f6)
  [ -n "$home_dir" ] || continue
  install -d -m 0700 "$backup_dir/$user_name"
  for source in "$home_dir/.hermes" "$home_dir/.agentik" "$home_dir/.config/systemd/user"; do
    [ -e "$source" ] || continue
    tar -C "$home_dir" -cpf "$backup_dir/$user_name/$(basename "$source").tar" "${source#$home_dir/}"
  done
  while IFS= read -r -d '' source; do
    tar -C "$home_dir" -cpf \
      "$backup_dir/$user_name/$(basename "$source").tar" \
      "${source#$home_dir/}"
  done < <(find "$home_dir" -maxdepth 1 -mindepth 1 -type d \
    -name '.hermes-*' -print0)
  : > "$backup_dir/$user_name/discord-state.before.sha256"
  for relative in "${discord_state[@]}"; do
    [ -f "$home_dir/.hermes/$relative" ] || continue
    sha256sum "$home_dir/.hermes/$relative" \
      >> "$backup_dir/$user_name/discord-state.before.sha256"
  done
done

if [ -d "$official_dir/.git" ]; then
  {
    printf 'origin='
    git -c safe.directory="$official_dir" -C "$official_dir" remote get-url origin
    printf 'head='
    git -c safe.directory="$official_dir" -C "$official_dir" rev-parse HEAD
  } > "$backup_dir/official-runtime.before"
fi

for launcher in hermes hermes-agent hermes-acp; do
  [ -e "/usr/local/bin/$launcher" ] || continue
  cp -a "/usr/local/bin/$launcher" "$backup_dir/$launcher.launcher.before"
done

if [ -x "$official_dir/venv/bin/python" ] \
  && ! sudo -u operator "$official_dir/venv/bin/python" --version >/dev/null 2>&1
then
  mv "$official_dir/venv" "$backup_dir/official-venv.inaccessible"
fi

if [ "$reuse_official" != true ]; then
  installer=$(mktemp -t hermes-official.XXXXXX)
  trap 'rm -f "$installer"' EXIT
  curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o "$installer"
  installer_args=(
    --dir "$official_dir"
    --hermes-home "$bootstrap_home/.hermes"
    --skip-setup
    --non-interactive
  )
  if [ -n "$official_commit" ]; then
    installer_args+=(--commit "$official_commit" --force-commit)
  fi
  env \
    HOME="$bootstrap_home" \
    HERMES_HOME="$bootstrap_home/.hermes" \
    UV_PYTHON_INSTALL_DIR="$official_python_dir" \
    bash "$installer" "${installer_args[@]}"
fi

git -c safe.directory="$official_dir" -C "$official_dir" remote get-url origin \
  | grep -Fx 'https://github.com/NousResearch/hermes-agent.git'
if [ -n "$official_commit" ]; then
  installed_commit=$(git -c safe.directory="$official_dir" \
    -C "$official_dir" rev-parse HEAD)
  [ "$installed_commit" = "$official_commit" ] || {
    echo "Hermes commit mismatch: expected $official_commit, got $installed_commit" >&2
    exit 1
  }
fi
"$official_dir/venv/bin/hermes" --version
sudo -u operator "$official_dir/venv/bin/python" --version >/dev/null

# The non-interactive official bootstrap deliberately skips messaging setup.
# Install the exact Discord versions pinned by Hermes so existing gateway units
# can reconnect immediately after their configuration is remapped.
/usr/local/bin/uv pip install \
  --python "$official_dir/venv/bin/python" \
  --overrides <(printf '%s\n' 'pynacl>=1.6,<1.7') \
  'anthropic==0.87.0' \
  'discord.py[voice]==2.7.1' \
  'pynacl>=1.6,<1.7'

ln -sfn "$official_dir/venv/bin/hermes" /usr/local/bin/hermes
ln -sfn "$official_dir/venv/bin/hermes-agent" /usr/local/bin/hermes-agent
ln -sfn "$official_dir/venv/bin/hermes-acp" /usr/local/bin/hermes-acp

# Install the complete workspace graph before either frontend build. Limiting
# npm ci to the web workspace prunes dependencies used by ui-tui and makes a
# second migration fail even though the first one succeeded.
(cd "$official_dir" && npm ci --include=dev \
  --silent --no-fund --no-audit --progress=false)

# A shared root-owned source checkout cannot rebuild its TUI from an
# unprivileged session. Build once and place the self-contained bundle where
# Hermes' official wheel lookup loads it without npm writes at runtime.
(cd "$official_dir/ui-tui" && npm run build)
install -d -m 0755 "$official_dir/hermes_cli/tui_dist"
install -m 0644 "$official_dir/ui-tui/dist/entry.js" \
  "$official_dir/hermes_cli/tui_dist/entry.js"

# Existing dashboard units intentionally use --skip-build. Produce the
# official Vite bundle once while the root-owned checkout is writable.
(cd "$official_dir" && npm run build -w web)
test -f "$official_dir/hermes_cli/web_dist/index.html"

# Install the browser engine once for all identities. agent-browser stores its
# managed Chrome below HOME; exposing that exact binary as google-chrome makes
# Hermes' passive capability probe and agent-browser agree without four copies.
(cd "$official_dir" && env HOME="$browser_home" \
  npx --ignore-scripts -y 'agent-browser@^0.26.0' install --with-deps)
browser_bin=$(find "$browser_home/.agent-browser/browsers" -mindepth 2 \
  -maxdepth 2 -type f -name chrome -perm -u+x -print -quit)
[ -n "$browser_bin" ] || { echo "agent-browser Chrome install is missing" >&2; exit 1; }
ln -sfn "$browser_bin" /usr/local/bin/google-chrome
sudo -u operator /usr/local/bin/google-chrome --version >/dev/null

for user_name in "${users[@]}"; do
  home_dir=$(getent passwd "$user_name" | cut -d: -f6)
  [ -n "$home_dir" ] || continue
  sudo -u "$user_name" env \
    HOME="$home_dir" \
    HERMES_HOME="$home_dir/.hermes" \
    AGK_TERMINAL_ROOT="$install_root" \
    PATH="$official_dir/venv/bin:/usr/local/bin:/usr/bin:$home_dir/.local/bin" \
    "$install_root/scripts/sync-hermes.sh"

  unit_dir=$home_dir/.config/systemd/user
  [ -d "$unit_dir" ] || continue
  while IFS= read -r -d '' unit; do
    cp -a "$unit" "$backup_dir/$user_name/$(basename "$unit").before"
    sed -i \
      -e "s#/opt/agentik/hermes/current/venv#$official_dir/venv#g" \
      -e "s#/opt/agentik/hermes/releases/[^/]*/venv#$official_dir/venv#g" \
      "$unit"
    chown "$user_name:$(id -gn "$user_name")" "$unit"
  done < <(find "$unit_dir" -maxdepth 1 -type f -name 'hermes-*.service' -print0)
done

for user_name in "${users[@]}"; do
  uid=$(id -u "$user_name")
  runtime=/run/user/$uid
  [ -S "$runtime/bus" ] || continue
  sudo -u "$user_name" env \
    XDG_RUNTIME_DIR="$runtime" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
    systemctl --user daemon-reload
  home_dir=$(getent passwd "$user_name" | cut -d: -f6)
  unit_dir=$home_dir/.config/systemd/user
  while IFS= read -r -d '' unit; do
    unit_name=$(basename "$unit")
    if sudo -u "$user_name" env \
      XDG_RUNTIME_DIR="$runtime" \
      DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
      systemctl --user is-active --quiet "$unit_name"
    then
      sudo -u "$user_name" env \
        XDG_RUNTIME_DIR="$runtime" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        systemctl --user restart "$unit_name"
      sudo -u "$user_name" env \
        XDG_RUNTIME_DIR="$runtime" \
        DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime/bus" \
        systemctl --user is-active --quiet "$unit_name"
    fi
  done < <(find "$unit_dir" -maxdepth 1 -type f -name 'hermes-*.service' -print0)

  : > "$backup_dir/$user_name/discord-state.after.sha256"
  for relative in "${discord_state[@]}"; do
    [ -f "$home_dir/.hermes/$relative" ] || continue
    sha256sum "$home_dir/.hermes/$relative" \
      >> "$backup_dir/$user_name/discord-state.after.sha256"
  done
done

echo "Shared official Hermes installation completed. Recovery snapshot: $backup_dir"
echo "Existing runtime data and live-session dependencies were preserved."
