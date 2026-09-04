#!/usr/bin/env bash
# Enable the loopback broker and, when enrolled, publish it inside the Tailnet.
set -Eeuo pipefail

optional=0
hermes_setup_url=""
while (($#)); do
  case "$1" in
    --if-enrolled) optional=1; shift;;
    --hermes-setup-url) hermes_setup_url=${2:-}; shift 2;;
    -h|--help)
      echo "usage: sudo station_guided_setup_enable.sh [--if-enrolled] [--hermes-setup-url https://host.ts.net/path]"
      exit 0;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "run with sudo/root" >&2; exit 2; }
zone_id=discord-bootstrap
zone_user=z-system-discord
zone_root=/var/lib/station/zones/discord-bootstrap
zone_record=/etc/station/zones.d/discord-bootstrap.json
state_root=$zone_root/connector-state/setup-links
hermes_dir=$zone_root/hermes

[[ -f "$zone_record" && ! -L "$zone_record" ]] || {
  echo "ERROR: the canonical discord-bootstrap Zone is not installed" >&2
  exit 2
}
jq -e --arg id "$zone_id" --arg user "$zone_user" --arg root "$zone_root" \
  '.id == $id and .unix_user == $user and .state_root == $root' "$zone_record" >/dev/null || {
  echo "ERROR: discord-bootstrap Zone identity/path readback failed" >&2
  exit 2
}
id "$zone_user" >/dev/null 2>&1 || { echo "ERROR: missing $zone_user" >&2; exit 2; }
install -d -m 0700 -o "$zone_user" -g "$zone_user" "$state_root"
systemctl enable --now station-guided-setup.service
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8787/health >/dev/null

if ! command -v tailscale >/dev/null 2>&1 || ! tailscale status --json >/dev/null 2>&1; then
  echo "STATE: LOCAL_BROKER_READY_TAILSCALE_NOT_ENROLLED"
  echo "NEXT: enroll this Host in Tailscale, then rerun sudo $0"
  [[ "$optional" -eq 1 ]] && exit 0
  exit 2
fi

dns_name=$(tailscale status --json | jq -r '.Self.DNSName // empty')
dns_name=${dns_name%.}
[[ "$dns_name" =~ ^[A-Za-z0-9.-]+\.ts\.net$ ]] || {
  echo "ERROR: Tailscale MagicDNS .ts.net identity is unavailable" >&2
  exit 2
}
base_url="https://${dns_name}/station-setup"
if [[ -n "$hermes_setup_url" ]]; then
  [[ "$hermes_setup_url" =~ ^https://[A-Za-z0-9.-]+\.ts\.net(/[^[:space:]?#]*)?$ ]] || {
    echo "ERROR: --hermes-setup-url must be a query-free Tailnet HTTPS URL" >&2
    exit 2
  }
fi

tailscale serve --bg --yes --https=443 --set-path=/station-setup http://127.0.0.1:8787
tailscale serve status >/dev/null
curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8787/station-setup/health >/dev/null
curl --fail --silent --show-error --max-time 10 "$base_url/health" >/dev/null

env_file=$hermes_dir/.env
[[ ! -L "$hermes_dir" && -d "$hermes_dir" ]] || { echo "ERROR: unsafe Zone Hermes directory" >&2; exit 2; }
if [[ -e "$env_file" ]]; then
  [[ -f "$env_file" && ! -L "$env_file" ]] || { echo "ERROR: unsafe Zone Hermes environment" >&2; exit 2; }
  [[ "$(stat -c '%U' "$env_file")" == "$zone_user" ]] || { echo "ERROR: Zone Hermes environment has the wrong owner" >&2; exit 2; }
fi
temporary=$(mktemp --tmpdir="$hermes_dir" .env.station.XXXXXX)
trap 'rm -f -- "$temporary"' EXIT
if [[ -f "$env_file" ]]; then
  awk '!/^STATION_ZONE_ID=/ && !/^STATION_ZONE_STATE_ROOT=/ && !/^STATION_SETUP_BASE_URL=/ && !/^STATION_HERMES_SETUP_URL=/' \
    "$env_file" > "$temporary"
fi
{
  printf 'STATION_ZONE_ID=%s\n' "$zone_id"
  printf 'STATION_ZONE_STATE_ROOT=%s\n' "$zone_root"
  printf 'STATION_SETUP_BASE_URL=%s\n' "$base_url"
  [[ -n "$hermes_setup_url" ]] && printf 'STATION_HERMES_SETUP_URL=%s\n' "$hermes_setup_url"
} >> "$temporary"
chown "$zone_user:$zone_user" "$temporary"
chmod 0600 "$temporary"
mv -- "$temporary" "$env_file"
trap - EXIT

echo "STATE: TAILNET_GUIDED_SETUP_CONFIGURED"
echo "URL: $base_url"
echo "NEXT: restart the discord-bootstrap Hermes gateway, then use its ephemeral provider setup buttons."
