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
# Type=simple becomes active before the broker necessarily starts listening.
broker_ready=0
for attempt in {1..10}; do
  if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8787/health >/dev/null 2>&1; then
    broker_ready=1
    break
  fi
  if [[ "$attempt" -lt 10 ]]; then sleep 1; fi
done
[[ "$broker_ready" -eq 1 ]] || {
  echo "ERROR: loopback setup broker did not become healthy after 10 attempts" >&2
  exit 2
}

tailnet_not_ready() {
  echo "STATE: LOCAL_BROKER_READY_TAILNET_NOT_READY"
  echo "NEXT: $1, then rerun sudo $0"
  [[ "$optional" -eq 1 ]] && exit 0
  exit 2
}

# Match providers/tailscale.py: zero exit alone is not an enrolled, online node.
# Use one observed snapshot for both readiness and the private DNS identity.
if ! command -v tailscale >/dev/null 2>&1 \
  || ! tailscale_status=$(tailscale status --json 2>/dev/null) \
  || ! jq -e '
    type == "object" and .BackendState == "Running"
    and (.Self | type == "object") and .Self.Online == true
    and (.Self.TailscaleIPs | type == "array" and length > 0)
  ' <<< "$tailscale_status" >/dev/null 2>&1; then
  tailnet_not_ready "enroll/start Tailscale and verify this Host is online with assigned Tailnet addresses"
fi

dns_name=$(jq -r '.Self.DNSName // empty' <<< "$tailscale_status")
dns_name=${dns_name%.}
[[ "$dns_name" =~ ^[A-Za-z0-9.-]+\.ts\.net$ ]] || {
  tailnet_not_ready "enable and verify this Host's Tailscale MagicDNS .ts.net identity"
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
# The first Serve request can wait for Tailscale's ACME certificate issuance.
# Retry bounded transport failures without weakening TLS or accepting HTTP errors.
tailnet_ready=0
for attempt in {1..5}; do
  if curl --fail --silent --show-error --connect-timeout 5 --max-time 10 "$base_url/health" >/dev/null; then
    tailnet_ready=1
    break
  else
    readback_status=$?
  fi
  case "$readback_status" in
    6|7|28|35|52|56) ;; # DNS, connection, timeout or interrupted TLS/transport.
    *) exit "$readback_status";; # Includes certificate verification and HTTP failure.
  esac
  if [[ "$attempt" -lt 5 ]]; then sleep 2; fi
done
[[ "$tailnet_ready" -eq 1 ]] || {
  echo "ERROR: private HTTPS setup readback failed after 5 attempts; inspect Tailscale certificate/connectivity status" >&2
  exit "$readback_status"
}

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
