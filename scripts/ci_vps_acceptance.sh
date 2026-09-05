#!/usr/bin/env bash
# Read back an actual disposable Ubuntu bootstrap. No external account is accepted here.
set -Eeuo pipefail

PROFILE="${AGK_VPS_PROFILE:-core}"
STATION_HOME="/home/agk-station"
REPO="$STATION_HOME/repos/agentik-station"
EVIDENCE="${AGK_VPS_EVIDENCE:-/tmp/station-vps-acceptance.json}"
EVIDENCE_HELPER="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/ci_vps_evidence.py"

[[ "$PROFILE" == core || "$PROFILE" == full ]] || { echo "invalid acceptance profile" >&2; exit 2; }
[[ "$(id -u)" -eq 0 ]] || { echo "acceptance readback requires root" >&2; exit 2; }
python3 -I -B "$EVIDENCE_HELPER" --output "$EVIDENCE" --check-output
[[ -x "$REPO/station" && -x "$STATION_HOME/.local/bin/agk" ]] || {
  echo "installed Station/AGK entry points are missing" >&2
  exit 1
}
[[ ! -e /root/repos/agentik-station ]] || { echo "repository leaked into /root" >&2; exit 1; }

umask 077
READBACK_DIR="$(mktemp -d /tmp/station-vps-readback.XXXXXXXXXX)"
cleanup() {
  local acceptance_status=$?
  rm -f -- "$READBACK_DIR/devops-os-doctor.json" || true
  rmdir -- "$READBACK_DIR" || true
  return "$acceptance_status"
}
trap cleanup EXIT

"$REPO/station" doctor --full
"$REPO/station" os doctor --id devops-os --json >"$READBACK_DIR/devops-os-doctor.json"
sudo -u agk-station -H "$STATION_HOME/.local/bin/agk" help >/dev/null
STATION_USER=agk-station STATION_HOME="$STATION_HOME" \
  "$REPO/scripts/station_toolchain_install.sh" --check
systemctl is-enabled --quiet station-hermes-update.timer
systemctl is-active --quiet station-hermes-update.timer
STATION_USER=agk-station STATION_HOME="$STATION_HOME" "$REPO/station" deps web-check

# Test real POSIX identities, not merely root's ability to stat private paths.
python3 - <<'PY'
import json
import pathlib
import subprocess
records = [json.loads(path.read_text()) for path in pathlib.Path('/etc/station/zones.d').glob('*.json')]
records = [record for record in records if record.get('placement') == 'local']
assert records, 'No local Zone to verify'
probe = '''import json, os, pathlib, sys
zone = json.loads(sys.argv[1])
for path in (zone['human_root'], zone['state_root'] + '/home',
             zone['state_root'] + '/home/.config', zone['state_root'] + '/home/.config/containers',
             zone['state_root'] + '/home/.local', zone['state_root'] + '/home/.local/share',
             zone['state_root'] + '/home/.local/share/containers',
             zone['hermes_home'], zone['log_root'], zone['runtime_root']):
    assert os.access(path, os.R_OK | os.W_OK | os.X_OK), path
binding = pathlib.Path('/var/lib/station/zone-bindings') / (zone['id'] + '.json')
assert json.loads(binding.read_text()) == zone
assert not os.access('/etc/station/station.json', os.R_OK)
assert not os.access(binding, os.W_OK)
for other in json.loads(sys.argv[2]):
    assert not os.access(other + '/home', os.R_OK | os.X_OK), other
'''
for record in records:
    others = [other['state_root'] for other in records if other['id'] != record['id']]
    subprocess.run(['/usr/sbin/runuser', '--user', record['unix_user'], '--', '/usr/bin/env', '-i',
                    'PATH=/usr/bin:/bin', '/usr/bin/python3', '-c', probe, json.dumps(record), json.dumps(others)], check=True)
print('PASS: real Zone traversal, private bindings and cross-Zone denial')
PY

if [[ "$PROFILE" == full ]]; then
  systemctl is-enabled --quiet station-parakeet.service
  curl --fail --silent --show-error --max-time 5 http://127.0.0.1:5092/health >/dev/null
fi

python3 -I -B "$EVIDENCE_HELPER" --output "$EVIDENCE" --profile "$PROFILE" \
  --doctor "$READBACK_DIR/devops-os-doctor.json"
