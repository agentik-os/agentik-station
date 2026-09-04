#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
fleet_dashboard_root=$repo_root/apps/hermes-fleet

cargo fmt --manifest-path "$repo_root/apps/agk-tui/Cargo.toml" -- --check
cargo clippy --locked --manifest-path "$repo_root/apps/agk-tui/Cargo.toml" --all-targets -- -D warnings
cargo test --locked --manifest-path "$repo_root/apps/agk-tui/Cargo.toml"
if python3 -c 'import pytest' >/dev/null 2>&1; then
  python3 -m pytest -q "$repo_root/tests"
elif command -v uv >/dev/null 2>&1; then
  uv run --no-project --with pytest==9.0.2 --with PyYAML==6.0.3 --with Pillow==12.3.0 \
    python -m pytest -q "$repo_root/tests"
else
  echo "Python tests require pytest or uv" >&2
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

npm --prefix "$fleet_dashboard_root" ci
npm --prefix "$fleet_dashboard_root" test
npm --prefix "$fleet_dashboard_root" run typecheck
npm --prefix "$fleet_dashboard_root" run build
test -f "$fleet_dashboard_root/server-dist/server.js"
node --check "$fleet_dashboard_root/server-dist/server.js"
