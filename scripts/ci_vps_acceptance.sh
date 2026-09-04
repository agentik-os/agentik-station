#!/usr/bin/env bash
# Read back an actual disposable Ubuntu bootstrap. No external account is accepted here.
set -Eeuo pipefail

PROFILE="${AGK_VPS_PROFILE:-core}"
STATION_HOME="/home/agk-station"
REPO="$STATION_HOME/repos/agentik-station"
EVIDENCE="${AGK_VPS_EVIDENCE:-/tmp/station-vps-acceptance.json}"

[[ "$PROFILE" == core || "$PROFILE" == full ]] || { echo "invalid acceptance profile" >&2; exit 2; }
[[ "$(id -u)" -eq 0 ]] || { echo "acceptance readback requires root" >&2; exit 2; }
[[ -x "$REPO/station" && -x "$STATION_HOME/.local/bin/agk" ]] || {
  echo "installed Station/AGK entry points are missing" >&2
  exit 1
}
[[ ! -e /root/repos/agentik-station ]] || { echo "repository leaked into /root" >&2; exit 1; }

"$REPO/station" doctor --full
"$REPO/station" os doctor --id devops-os --json >/tmp/devops-os-doctor.json
sudo -u agk-station -H "$STATION_HOME/.local/bin/agk" help >/tmp/agk-help.txt
STATION_USER=agk-station STATION_HOME="$STATION_HOME" \
  "$REPO/scripts/station_toolchain_install.sh" --check
systemctl is-enabled --quiet station-hermes-update.timer
systemctl is-active --quiet station-hermes-update.timer
STATION_USER=agk-station STATION_HOME="$STATION_HOME" "$REPO/station" deps web-check

if [[ "$PROFILE" == full ]]; then
  systemctl is-enabled --quiet station-parakeet.service
  curl --fail --silent --show-error --max-time 5 http://127.0.0.1:5092/health >/dev/null
fi

python3 - "$EVIDENCE" "$PROFILE" <<'PY'
import hashlib
import json
import pathlib
import sys
import time

output = pathlib.Path(sys.argv[1])
profile = sys.argv[2]
doctor = pathlib.Path('/tmp/devops-os-doctor.json').read_bytes()
payload = {
    'schema_version': 1,
    'environment': 'disposable-ubuntu-24.04',
    'profile': profile,
    'claim': 'VERIFIED_INSTALL_READY_FOR_EXTERNAL_SETUP',
    'external_accounts_accepted': False,
    'checks': [
        'station-doctor-full',
        'devops-os-doctor',
        'agk-entrypoint',
        'pinned-toolchain-including-discord-js',
        'hermes-update-timer',
        'scrapegraphai-crawl4ai-imports-and-chromium-launch',
        *(['parakeet-loopback-health'] if profile == 'full' else []),
    ],
    'devops_doctor_sha256': hashlib.sha256(doctor).hexdigest(),
    'observed_unix_time': int(time.time()),
}
output.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
print(json.dumps(payload, indent=2, sort_keys=True))
PY
