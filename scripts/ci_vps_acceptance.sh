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

# Verify the public shared tools as a real Zone, never through the operator's
# private PATH or accounts. A separate network namespace forbids provider or
# telemetry traffic even if a CLI changes its --version implementation.
python3 -I -B - "$REPO/config/versions.lock" <<'PY_ZONE_TOOLS'
import json
import pathlib
import pwd
import re
import subprocess
import sys

TOOLS = {
    'node': 'NODE_VERSION', 'npm': 'NPM_VERSION', 'npx': 'NPM_VERSION',
    'gh': 'GITHUB_CLI_VERSION', 'vercel': 'VERCEL_CLI_VERSION', 'codex': 'CODEX_CLI_VERSION',
    'shadcn': 'SHADCN_CLI_VERSION', 'uv': 'UV_VERSION', 'uvx': 'UV_VERSION',
    'python-latest': 'PYTHON_VERSION', 'python-ai': 'AI_PYTHON_VERSION',
}

ZONE_TOOL_PROBE = '''import json, os, re, shutil, subprocess, sys
expected = json.loads(sys.argv[1])
pins = json.loads(sys.argv[2])
assert os.getuid() == expected['uid'] != 0, 'Probe must run as the selected non-root Zone'
assert os.getgid() == expected['gid'], 'Probe must use the Zone primary group'
assert os.environ.get('HOME') == expected['home'], 'Zone HOME changed'
assert os.environ.get('HERMES_HOME') == expected['hermes_home'], 'Zone HERMES_HOME changed'
assert os.environ.get('PATH') == '/usr/local/bin:/usr/bin:/bin', 'Private operator PATH inherited'
environment = dict(os.environ)
for name, version in pins.items():
    executable = '/usr/local/bin/' + name
    assert shutil.which(name) == executable, 'Public Zone command unavailable: ' + name
    try:
        result = subprocess.run([executable, '--version'], env=environment, cwd='/',
                                stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError('Zone version probe failed: ' + name) from None
    if result.returncode or not re.search(r'(?<![0-9.])' + re.escape(version) + r'(?![0-9.])',
                                         result.stdout + result.stderr):
        raise RuntimeError('Zone version readback failed: ' + name)
    print('PASS: Zone public ' + name + ' ' + version)
'''


def select_zone(records):
    candidates = sorted((record for record in records
                         if record.get('placement') == 'local' and record.get('category') != 'SYSTEM'),
                        key=lambda record: (record.get('category') != 'AGENTIK', record['id']))
    if not candidates:
        raise ValueError('No non-system local Zone available for toolchain acceptance')
    return candidates[0]


def verify_zone_tools(record, pins):
    account = pwd.getpwnam(record['unix_user'])
    home = str(pathlib.Path(record['state_root']) / 'home')
    if account.pw_uid == 0 or account.pw_dir != home:
        raise ValueError('Zone identity does not match its canonical private HOME')
    versions = {name: pins.get(key, '') for name, key in TOOLS.items()}
    if any(not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}', value) for value in versions.values()):
        raise ValueError('Missing or malformed toolchain acceptance pins')
    expected = {'uid': account.pw_uid, 'gid': account.pw_gid, 'home': home,
                'hermes_home': record['hermes_home']}
    command = ['/usr/bin/unshare', '--net', '--', '/usr/sbin/runuser', '--user', account.pw_name,
               '--', '/usr/bin/env', '-i', 'HOME=' + home, 'HERMES_HOME=' + record['hermes_home'],
               'PATH=/usr/local/bin:/usr/bin:/bin', 'CI=1', 'DO_NOT_TRACK=1',
               'NPM_CONFIG_UPDATE_NOTIFIER=false', 'PYTHONDONTWRITEBYTECODE=1',
               '/usr/bin/python3', '-I', '-B', '-c', ZONE_TOOL_PROBE,
               json.dumps(expected), json.dumps(versions)]
    try:
        result = subprocess.run(command, cwd='/', stdin=subprocess.DEVNULL,
                                capture_output=True, text=True, timeout=360)
    except (OSError, subprocess.SubprocessError):
        raise RuntimeError('Network-isolated Zone toolchain probe could not complete') from None
    if result.returncode:
        # Never echo native CLI output: a future version could include config.
        raise RuntimeError('Network-isolated Zone toolchain probe failed; inspect native versions and namespace support')
    print('PASS: real Zone public toolchain pins, private HOME and network-isolated version readback')


def main(lock):
    pins = dict(line.split('=', 1) for line in pathlib.Path(lock).read_text().splitlines()
                if re.fullmatch(r'[A-Z][A-Z0-9_]*=\S+', line))
    records = [json.loads(path.read_text()) for path in pathlib.Path('/etc/station/zones.d').glob('*.json')]
    verify_zone_tools(select_zone(records), pins)


if __name__ == '__main__':
    main(sys.argv[1])
PY_ZONE_TOOLS

if [[ "$PROFILE" == full ]]; then
  systemctl is-enabled --quiet station-parakeet.service
  curl --fail --silent --show-error --max-time 5 http://127.0.0.1:5092/health >/dev/null
fi

python3 -I -B "$EVIDENCE_HELPER" --output "$EVIDENCE" --profile "$PROFILE" \
  --doctor "$READBACK_DIR/devops-os-doctor.json"
