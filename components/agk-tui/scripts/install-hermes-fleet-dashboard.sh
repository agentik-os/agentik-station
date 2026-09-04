#!/usr/bin/env bash
set -euo pipefail

source_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
official_root=/opt/agk-terminal/hermes-agent
install_root=/usr/local/lib/agk-terminal
fleet_link=$install_root/share/hermes-fleet
fleet_releases=$install_root/share/hermes-fleet-releases
template=
fleet_template=
temporary=

usage() {
  cat <<'EOF'
usage: install-hermes-fleet-dashboard.sh [--source-root PATH]

Build and install the AGK Hermes Fleet switcher, run one loopback-only Hermes
dashboard per AGK profile, and publish the central switcher through Tailscale
Serve on HTTPS 443. This command must run as root. Internet publication is
intentionally outside this installer's scope.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --source-root)
      source_root=${2:?missing source root}
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[ "$(id -u)" -eq 0 ] || {
  echo "Hermes Fleet dashboard installation must run as root" >&2
  exit 1
}

source_root=$(readlink -f "$source_root")
fleet_source=$source_root/apps/hermes-fleet
template=$source_root/systemd/hermes-dashboard.service.in
fleet_template=$source_root/systemd/hermes-fleet.service.in

for command_name in npm install readlink sha256sum sudo systemctl loginctl tailscale python3 ss getent stat curl; do
  command -v "$command_name" >/dev/null || {
    echo "required command is missing: $command_name" >&2
    exit 1
  }
done

test -f "$official_root/package-lock.json" || {
  echo "official Hermes checkout is missing: $official_root" >&2
  exit 1
}
test -f "$official_root/web/package.json" || {
  echo "official Hermes web workspace is missing" >&2
  exit 1
}
test -f "$fleet_source/package.json" && test -f "$fleet_source/package-lock.json" || {
  echo "Hermes Fleet application or lockfile is missing: $fleet_source" >&2
  exit 1
}
test -f "$template" || {
  echo "Hermes dashboard unit template is missing: $template" >&2
  exit 1
}
test -f "$fleet_template" || {
  echo "Hermes Fleet unit template is missing: $fleet_template" >&2
  exit 1
}
test -x /usr/local/bin/hermes || {
  echo "official Hermes launcher is missing: /usr/local/bin/hermes" >&2
  exit 1
}

profiles=(operator agentik mission private)
ports=(8460 8461 8462 8463)

validate_profile_target() {
  local profile_user=$1 expected_port=$2 profile_home unit env_file exec_line
  profile_home=$(getent passwd "$profile_user" | cut -d: -f6)
  [ "$profile_home" = "/home/$profile_user" ] || {
    echo "refusing unexpected home for $profile_user: ${profile_home:-<missing>}" >&2
    return 1
  }
  test -d "$profile_home/.hermes" || {
    echo "Hermes home is missing for $profile_user" >&2
    return 1
  }

  env_file=$profile_home/.hermes/secrets/serve.env
  if [ -e "$env_file" ] || [ -L "$env_file" ]; then
    test -f "$env_file" && test ! -L "$env_file" || {
      echo "refusing unsafe EnvironmentFile for $profile_user" >&2
      return 1
    }
    [ "$(stat -c %U "$env_file")" = "$profile_user" ] || {
      echo "EnvironmentFile owner is unsafe for $profile_user" >&2
      return 1
    }
    local env_mode
    env_mode=$(stat -c %a "$env_file")
    (( (8#$env_mode & 077) == 0 )) || {
      echo "EnvironmentFile permissions are too broad for $profile_user" >&2
      return 1
    }
  fi

  unit=$profile_home/.config/systemd/user/hermes-serve.service
  if [ -e "$unit" ] || [ -L "$unit" ]; then
    test -f "$unit" && test ! -L "$unit" || {
      echo "refusing unsafe service target for $profile_user" >&2
      return 1
    }
    exec_line=$(sed -n 's/^ExecStart=//p' "$unit")
    [ "$(printf '%s\n' "$exec_line" | wc -l)" -eq 1 ] || {
      echo "refusing service with an ambiguous ExecStart for $profile_user" >&2
      return 1
    }
    printf '%s\n' "$exec_line" \
      | grep -Eq '^(/usr/local/bin/hermes|/opt/(agk-terminal/hermes-agent|agentik/hermes/current)/venv/bin/hermes) (serve|dashboard)( |$)' || {
        echo "refusing to replace an unrelated service for $profile_user" >&2
        return 1
      }
    printf '%s\n' "$exec_line" | grep -Eq '(^| )--host 127\.0\.0\.1( |$)' || {
      echo "refusing non-loopback service for $profile_user" >&2
      return 1
    }
    printf '%s\n' "$exec_line" | grep -Eq "(^| )--port $expected_port( |$)" || {
      echo "refusing unexpected dashboard port for $profile_user" >&2
      return 1
    }
    if grep -q '^EnvironmentFile=' "$unit"; then
      grep -Eq "^EnvironmentFile=-?$profile_home/\.hermes/secrets/serve\.env$" "$unit" || {
        echo "refusing unexpected EnvironmentFile for $profile_user" >&2
        return 1
      }
    fi
  fi
}

validate_fleet_service_target() {
  local unit=/home/operator/.config/systemd/user/hermes-fleet.service exec_line
  if [ -e "$unit" ] || [ -L "$unit" ]; then
    test -f "$unit" && test ! -L "$unit" || {
      echo "refusing unsafe Hermes Fleet service target" >&2
      return 1
    }
    exec_line=$(sed -n 's/^ExecStart=//p' "$unit")
    [ "$exec_line" = "/usr/bin/node $fleet_link/server-dist/server.js" ] || {
      echo "refusing to replace an unrelated Hermes Fleet service" >&2
      return 1
    }
    grep -qx 'Environment=HERMES_FLEET_HOST=127.0.0.1' "$unit" || {
      echo "refusing non-loopback Hermes Fleet service" >&2
      return 1
    }
    grep -qx 'Environment=HERMES_FLEET_PORT=8459' "$unit" || {
      echo "refusing unexpected Hermes Fleet service port" >&2
      return 1
    }
  fi
}

validate_serve_config() {
  local config_file=$1 phase=${2:-before}
  python3 - "$config_file" "$fleet_link" "$phase" <<'PY'
import json
import sys

path, fleet_path, phase = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    config = json.load(handle)

if config.get("AllowFunnel"):
    raise SystemExit("refusing to modify Serve while Funnel is enabled")

central_target = "http://127.0.0.1:8459"
legacy_targets = {
    "8460": "http://127.0.0.1:8460",
    "8461": "http://127.0.0.1:8461",
    "8462": "http://127.0.0.1:8462",
    "8463": "http://127.0.0.1:8463",
}
tcp = config.get("TCP") or {}
web = config.get("Web") or {}

def matches(port):
    return [value for authority, value in web.items()
            if str(authority).rsplit(":", 1)[-1] == port]

central = matches("443")
if phase == "before":
    if tcp.get("443") is not None and not central:
        raise SystemExit("refusing conflicting non-web Serve target on port 443")
    for value in central:
        encoded = json.dumps(value, sort_keys=True)
        if central_target not in encoded and fleet_path not in encoded:
            raise SystemExit("refusing conflicting Serve target on HTTPS 443")
    for port, target in legacy_targets.items():
        routes = matches(port)
        if tcp.get(port) is not None and not routes:
            raise SystemExit(f"refusing conflicting non-web Serve target on port {port}")
        for value in routes:
            if target not in json.dumps(value, sort_keys=True):
                raise SystemExit(f"refusing conflicting Serve target on HTTPS {port}")
elif phase == "after":
    if not central or tcp.get("443") is None:
        raise SystemExit("Tailscale Serve route is missing on HTTPS 443")
    for value in central:
        if central_target not in json.dumps(value, sort_keys=True):
            raise SystemExit("unexpected final Serve target on HTTPS 443")
    for port in legacy_targets:
        if matches(port) or tcp.get(port) is not None:
            raise SystemExit(f"legacy Serve route remains on HTTPS {port}")
else:
    raise SystemExit(f"unknown Serve validation phase: {phase}")
PY
}

for index in "${!profiles[@]}"; do
  validate_profile_target "${profiles[$index]}" "${ports[$index]}"
done
validate_fleet_service_target

if [ -e "$fleet_link" ] || [ -L "$fleet_link" ]; then
  test -L "$fleet_link" || {
    echo "refusing to replace non-symlink Fleet install: $fleet_link" >&2
    exit 1
  }
  case "$(readlink "$fleet_link")" in
    hermes-fleet-releases/*) ;;
    *)
      echo "refusing unexpected Fleet release link" >&2
      exit 1
      ;;
  esac
fi

serve_before=$(mktemp -t agk-hermes-fleet-serve.XXXXXX)
temporary=$serve_before
trap 'test -n "${temporary:-}" && rm -rf -- "$temporary"' EXIT
tailscale serve status --json > "$serve_before"
validate_serve_config "$serve_before" before
legacy_ports=$(python3 - "$serve_before" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    web = (json.load(handle).get("Web") or {})
for port in ("8460", "8461", "8462", "8463"):
    if any(str(authority).rsplit(":", 1)[-1] == port for authority in web):
        print(port)
PY
)
rm -f -- "$serve_before"
temporary=

magic_dns=$(tailscale status --json | python3 -c '
import json
import re
import sys

name = str((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "").rstrip(".").lower()
if not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]*[a-z0-9])?)*\.ts\.net", name):
    raise SystemExit("Tailscale status did not return a safe MagicDNS name")
print(name)
')
allowed_hosts=$magic_dns,localhost,127.0.0.1

# Hermes uses one root workspace lockfile. Installing only the web workspace
# prunes sibling dependencies and makes subsequent official builds unreliable.
(cd "$official_root" && npm ci --include=dev --no-fund --no-audit)
(cd "$official_root/web" && npm run build)
test -f "$official_root/hermes_cli/web_dist/index.html" || {
  echo "official Hermes dashboard build did not produce web_dist" >&2
  exit 1
}

fleet_builder=$(stat -c %U "$fleet_source/package.json")
if [ "$fleet_builder" = root ]; then
  (cd "$fleet_source" && npm ci --include=dev --no-fund --no-audit)
  (cd "$fleet_source" && npm run build)
else
  fleet_builder_home=$(getent passwd "$fleet_builder" | cut -d: -f6)
  [ -n "$fleet_builder_home" ] || {
    echo "Fleet source owner is not a local user: $fleet_builder" >&2
    exit 1
  }
  sudo -u "$fleet_builder" env HOME="$fleet_builder_home" \
    npm --prefix "$fleet_source" ci --include=dev --no-fund --no-audit
  sudo -u "$fleet_builder" env HOME="$fleet_builder_home" \
    npm --prefix "$fleet_source" run build
fi
test -f "$fleet_source/dist/index.html" || {
  echo "Hermes Fleet build did not produce dist/index.html" >&2
  exit 1
}
test -f "$fleet_source/server-dist/server.js" || {
  echo "Hermes Fleet build did not produce server-dist/server.js" >&2
  exit 1
}

fleet_digest=$(find "$fleet_source/dist" "$fleet_source/server-dist" -type f -print0 \
  | sort -z \
  | xargs -0 sha256sum \
  | sha256sum \
  | cut -d' ' -f1)
test -n "$fleet_digest"
release_dir=$fleet_releases/$fleet_digest
install -d -m 0755 "$install_root/share" "$fleet_releases"
if [ ! -d "$release_dir" ]; then
  release_stage=$(mktemp -d "$fleet_releases/.staging.XXXXXX")
  temporary=$release_stage
  install -d -m 0755 "$release_stage/dist" "$release_stage/server-dist"
  cp -a "$fleet_source/dist/." "$release_stage/dist/"
  cp -a "$fleet_source/server-dist/." "$release_stage/server-dist/"
  chown -R root:root "$release_stage"
  find "$release_stage" -type d -exec chmod 0755 {} +
  find "$release_stage" -type f -exec chmod 0644 {} +
  mv "$release_stage" "$release_dir"
  temporary=
fi
ln -sfn "hermes-fleet-releases/$fleet_digest" "$fleet_link"

for index in "${!profiles[@]}"; do
  profile_user=${profiles[$index]}
  port=${ports[$index]}
  profile_home=/home/$profile_user
  profile_group=$(id -gn "$profile_user")
  profile_uid=$(id -u "$profile_user")
  unit_dir=$profile_home/.config/systemd/user
  rendered_unit=$(mktemp -t "agk-$profile_user-hermes-dashboard.XXXXXX")
  temporary=$rendered_unit
  sed \
    -e "s#@PROFILE_USER@#$profile_user#g" \
    -e "s#@PROFILE_HOME@#$profile_home#g" \
    -e "s#@PORT@#$port#g" \
    "$template" > "$rendered_unit"
  install -d -m 0700 -o "$profile_user" -g "$profile_group" "$unit_dir"
  if [ -f "$unit_dir/hermes-serve.service" ] \
    && [ ! -e "$unit_dir/hermes-serve.service.before-fleet" ]; then
    install -m 0600 -o "$profile_user" -g "$profile_group" \
      "$unit_dir/hermes-serve.service" \
      "$unit_dir/hermes-serve.service.before-fleet"
  fi
  install -m 0600 -o "$profile_user" -g "$profile_group" \
    "$rendered_unit" "$unit_dir/hermes-serve.service"
  rm -f -- "$rendered_unit"
  temporary=

  loginctl enable-linger "$profile_user"
  systemctl start "user@$profile_uid.service"
  runtime_dir=/run/user/$profile_uid
  test -S "$runtime_dir/bus" || {
    echo "systemd user bus is unavailable for $profile_user" >&2
    exit 1
  }
  sudo -u "$profile_user" env \
    HOME="$profile_home" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
    systemctl --user daemon-reload
  sudo -u "$profile_user" env \
    HOME="$profile_home" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
    systemctl --user enable hermes-serve.service
  # The previous headless unit may already be active. An explicit restart is
  # required so systemd replaces that running process with `hermes dashboard`.
  sudo -u "$profile_user" env \
    HOME="$profile_home" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
    systemctl --user restart hermes-serve.service
done

operator_home=/home/operator
operator_group=$(id -gn operator)
operator_uid=$(id -u operator)
operator_unit_dir=$operator_home/.config/systemd/user
fleet_unit=$operator_unit_dir/hermes-fleet.service
rendered_fleet_unit=$(mktemp -t agk-operator-hermes-fleet.XXXXXX)
temporary=$rendered_fleet_unit
sed \
  -e "s#@FLEET_ROOT@#$fleet_link#g" \
  -e "s#@ALLOWED_HOSTS@#$allowed_hosts#g" \
  "$fleet_template" > "$rendered_fleet_unit"
install -d -m 0700 -o operator -g "$operator_group" "$operator_unit_dir"
if [ -f "$fleet_unit" ] && [ ! -e "$fleet_unit.before-fleet" ]; then
  install -m 0600 -o operator -g "$operator_group" \
    "$fleet_unit" "$fleet_unit.before-fleet"
fi
install -m 0600 -o operator -g "$operator_group" \
  "$rendered_fleet_unit" "$fleet_unit"
rm -f -- "$rendered_fleet_unit"
temporary=

operator_runtime=/run/user/$operator_uid
test -S "$operator_runtime/bus" || {
  echo "systemd user bus is unavailable for operator" >&2
  exit 1
}
sudo -u operator env \
  HOME="$operator_home" \
  XDG_RUNTIME_DIR="$operator_runtime" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=$operator_runtime/bus" \
  systemctl --user daemon-reload
sudo -u operator env \
  HOME="$operator_home" \
  XDG_RUNTIME_DIR="$operator_runtime" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=$operator_runtime/bus" \
  systemctl --user enable hermes-fleet.service
sudo -u operator env \
  HOME="$operator_home" \
  XDG_RUNTIME_DIR="$operator_runtime" \
  DBUS_SESSION_BUS_ADDRESS="unix:path=$operator_runtime/bus" \
  systemctl --user restart hermes-fleet.service

expected_fleet_address=127.0.0.1:8459
fleet_listener=
for _ in $(seq 1 20); do
  fleet_listener=$(ss -H -ltn | awk -v address="$expected_fleet_address" \
    '$4 == address {print $4; exit}')
  [ -n "$fleet_listener" ] && break
  sleep 1
done
[ "$fleet_listener" = "$expected_fleet_address" ] || {
  echo "Hermes Fleet is not listening on loopback port 8459" >&2
  exit 1
}
if ss -H -ltn | awk \
  '$4 == "0.0.0.0:8459" || $4 == "*:8459" || $4 == "[::]:8459" { found = 1 } END { exit !found }'; then
  echo "Hermes Fleet has a wildcard listener on port 8459" >&2
  exit 1
fi

for route in / /operator/ /agentik/ /mission/ /private/; do
  status_code=
  for _ in $(seq 1 20); do
    status_code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' \
      "http://127.0.0.1:8459$route" || true)
    [ "$status_code" = 200 ] && break
    sleep 1
  done
  [ "$status_code" = 200 ] || {
    echo "Hermes Fleet route did not return HTTP 200: $route" >&2
    exit 1
  }
done

tailscale serve --bg --yes --https=443 "http://127.0.0.1:8459"
for port in $legacy_ports; do
  tailscale serve --yes --https="$port" off
done

serve_after=$(mktemp -t agk-hermes-fleet-serve.XXXXXX)
temporary=$serve_after
tailscale serve status --json > "$serve_after"
validate_serve_config "$serve_after" after

for index in "${!profiles[@]}"; do
  profile_user=${profiles[$index]}
  port=${ports[$index]}
  profile_uid=$(id -u "$profile_user")
  runtime_dir=/run/user/$profile_uid
  sudo -u "$profile_user" env \
    HOME="/home/$profile_user" \
    XDG_RUNTIME_DIR="$runtime_dir" \
    DBUS_SESSION_BUS_ADDRESS="unix:path=$runtime_dir/bus" \
    systemctl --user is-active --quiet hermes-serve.service

  expected_address="127.0.0.1:$port"
  listener=
  for _ in $(seq 1 20); do
    listener=$(ss -H -ltn | awk -v address="$expected_address" '$4 == address {print $4; exit}')
    [ -n "$listener" ] && break
    sleep 1
  done
  [ "$listener" = "$expected_address" ] || {
    echo "dashboard $profile_user is not listening on loopback port $port" >&2
    exit 1
  }
  if ss -H -ltn | awk -v port="$port" \
    '$4 == "0.0.0.0:" port || $4 == "*:" port || $4 == "[::]:" port { found = 1 } END { exit !found }'; then
    echo "dashboard $profile_user has a wildcard listener on port $port" >&2
    exit 1
  fi
done

rm -f -- "$serve_after"
temporary=
trap - EXIT

echo "Hermes Fleet dashboard installed with Tailscale Serve only"
echo "Fleet switcher: https://$magic_dns"
echo "Dashboard services remain isolated on loopback ports 8460-8463"
