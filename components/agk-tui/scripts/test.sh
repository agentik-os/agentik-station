#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
offline=()
case "${1:-}" in
  --offline) offline=(--offline); shift ;;
  -h|--help)
    echo 'usage: scripts/test.sh [--offline]'
    echo 'Test a private source copy; no build outputs are written into the release tree.'
    exit 0 ;;
esac
[ "$#" -eq 0 ] || { echo 'unknown test runner argument' >&2; exit 2; }
test -f "$repo_root/apps/agk-tui/Cargo.toml" || {
  echo 'Native Rust TUI source is absent; the complete component cannot be verified.' >&2
  exit 2
}
command -v python3 >/dev/null
command -v cargo >/dev/null
command -v npm >/dev/null

# The release tree includes authored dashboard/dist assets. Preserve those while
# excluding only caches and generated application build outputs from the copy.
test_root=$(mktemp -d -t station-agk-tests.XXXXXX)
trap 'rm -rf -- "$test_root"' EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM
python3 - "$repo_root" "$test_root/component" <<'PY'
from pathlib import Path
import shutil
import sys

source, target = map(Path, sys.argv[1:])
def ignore(directory, entries):
    excluded = {".git", "node_modules", "target", "__pycache__", ".pytest_cache"}
    if Path(directory) == source / "apps" / "hermes-fleet":
        excluded.update({"dist", "server-dist"})
    return [name for name in entries if name in excluded or name.endswith(".pyc")]
shutil.copytree(source, target, symlinks=True, ignore=ignore)
PY
repo_root=$(cd -P "$test_root/component" && pwd)
fleet_dashboard_root=$repo_root/apps/hermes-fleet
export PYTHONDONTWRITEBYTECODE=1
export CARGO_TARGET_DIR=$test_root/cargo-target

cargo fmt --manifest-path "$repo_root/apps/agk-tui/Cargo.toml" -- --check
cargo clippy --locked "${offline[@]}" --manifest-path "$repo_root/apps/agk-tui/Cargo.toml" --all-targets -- -D warnings
cargo test --locked "${offline[@]}" --manifest-path "$repo_root/apps/agk-tui/Cargo.toml"
if command -v uv >/dev/null 2>&1; then
  uv run "${offline[@]}" --no-project --python 3.13 --with pytest==8.4.2 --with PyYAML==6.0.3 --with Pillow==12.3.0 \
    python -m pytest -q -p no:cacheprovider --basetemp "$test_root/pytest" "$repo_root/tests"
elif python3 -c 'from importlib.metadata import version; assert all(version(name) == wanted for name, wanted in (("pytest", "8.4.2"), ("PyYAML", "6.0.3"), ("Pillow", "12.3.0")))' >/dev/null 2>&1; then
  python3 -m pytest -q -p no:cacheprovider --basetemp "$test_root/pytest" "$repo_root/tests"
else
  echo "Python tests require uv or pytest 8.4.2, PyYAML 6.0.3 and Pillow 12.3.0" >&2
  exit 1
fi
bash -n \
  "$repo_root/bootstrap-vps.sh" \
  "$repo_root/install.sh" \
  "$repo_root/bin/agk" \
  "$repo_root/bin/agk-terminal" \
  "$repo_root/bin/client-init" \
  "$repo_root/bin/client-doctor" \
  "$repo_root/bin/client-status" \
  "$repo_root/bin/client-env" \
  "$repo_root/bin/provision-client" \
  "$repo_root/scripts/doctor.sh" \
  "$repo_root/scripts/install-shared-hermes.sh" \
  "$repo_root/scripts/install-hermes-fleet-dashboard.sh" \
  "$repo_root/scripts/provider.sh" \
  "$repo_root/scripts/sync-hermes.sh"
python3 -m py_compile \
  "$repo_root/scripts/client_control.py" \
  "$repo_root/hermes/plugins/platforms/discord/agk_client_reviews.py"

(cd "$fleet_dashboard_root" && npm ci "${offline[@]}" --ignore-scripts --no-audit --no-fund)
(cd "$fleet_dashboard_root" && npm test)
(cd "$fleet_dashboard_root" && npm run typecheck)
(cd "$fleet_dashboard_root" && npm run build)
test -f "$fleet_dashboard_root/server-dist/server.js"
node --check "$fleet_dashboard_root/server-dist/server.js"
echo 'AGK shipped tests and builds passed; external accounts, live chat and service acceptance were not exercised.'
