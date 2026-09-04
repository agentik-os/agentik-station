#!/usr/bin/env bash
# Optional dependency installer for Agentik Station power stack.
# Does NOT claim OPERATIONAL. Leaves modules at SCAFFOLDED/INSTALLABLE until Doctor/readback.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATION_USER="${STATION_USER:-agk-station}"
STATION_HOME="${STATION_HOME:-/home/${STATION_USER}}"
STACK="$ROOT/config/deps/stack.yaml"

usage() {
  cat <<'USAGE'
usage: station_deps_install.sh [--all] [--list]
       station_deps_install.sh --component ID [--component ID ...]
       station_deps_install.sh --enable-hermes-auto-update
       station_deps_install.sh --platforms-guide

Components: ponytail langfuse honcho hindsight tigervnc crawl4ai
USAGE
}

COMPONENTS=()
ENABLE_AUTO=0
LIST_ONLY=0
PLATFORMS=0
ALL=0

while (($#)); do
  case "$1" in
    --all) ALL=1; shift;;
    --list) LIST_ONLY=1; shift;;
    --component) COMPONENTS+=("$2"); shift 2;;
    --enable-hermes-auto-update) ENABLE_AUTO=1; shift;;
    --platforms-guide) PLATFORMS=1; shift;;
    -h|--help) usage; exit 0;;
    *) echo "unknown: $1" >&2; usage; exit 2;;
  esac
done

if [[ "$LIST_ONLY" -eq 1 ]]; then
  echo "Declared stack: $STACK"
  if command -v python3 >/dev/null; then
    python3 - <<PY
import pathlib
try:
    import yaml
except ImportError:
    print(pathlib.Path("$STACK").read_text())
    raise SystemExit
data = yaml.safe_load(pathlib.Path("$STACK").read_text())
for c in data.get("components", []):
    print(f"{c['id']:12} {c['maturity']:12} {c['role']}")
print("platforms:", ", ".join(data.get("platforms", {}).get("surfaces", [])[:8]), "...")
PY
  else
    cat "$STACK"
  fi
  exit 0
fi

if [[ "$PLATFORMS" -eq 1 ]]; then
  cat "$ROOT/docs/dependencies/HERMES_PLATFORMS.md"
  exit 0
fi

as_station() {
  if [[ "$(id -un)" == "$STATION_USER" ]]; then
    env HOME="$STATION_HOME" PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  else
    sudo -u "$STATION_USER" -H env HOME="$STATION_HOME" PATH="$STATION_HOME/.local/bin:$PATH" "$@"
  fi
}

install_tigervnc() {
  [[ "$(id -u)" -eq 0 ]] || { echo "tigervnc apt install needs root" >&2; return 2; }
  apt-get update
  env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    tigervnc-standalone-server tigervnc-common tigervnc-tools || \
  env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
    tigervnc-standalone-server tigervnc-viewer
  echo "TigerVNC packages installed (SCAFFOLDED — configure display + auth before use)."
}

install_crawl4ai() {
  as_station bash -lc 'python3 -m pip install --user -U crawl4ai && crawl4ai-setup || pipx install crawl4ai || true'
  echo "crawl4ai install attempted under ${STATION_USER} (verify: python3 -c 'import crawl4ai')."
}

install_honcho() {
  as_station bash -lc 'python3 -m pip install --user -U honcho-ai || python3 -m pip install --user -U honcho || true'
  echo "honcho install attempted (package name may vary — see plastic-labs/honcho README)."
}

install_hindsight() {
  as_station bash -lc 'python3 -m pip install --user -U hindsight-ai || python3 -m pip install --user -U hindsight || true'
  echo "hindsight install attempted (verify against vectorize-io/hindsight README)."
}

install_ponytail() {
  dest="$STATION_HOME/.agentik/skills/ponytail"
  as_station bash -lc "mkdir -p '$STATION_HOME/.agentik/skills' && \
    if [ ! -d '$dest/.git' ]; then git clone --depth 1 https://github.com/DietrichGebert/ponytail.git '$dest'; else git -C '$dest' pull --ff-only; fi"
  echo "ponytail cloned to $dest (wire as Hermes/Claude skill — SCAFFOLDED)."
}

install_langfuse() {
  dest="$STATION_HOME/repos/langfuse"
  as_station bash -lc "mkdir -p '$STATION_HOME/repos' && \
    if [ ! -d '$dest/.git' ]; then git clone --depth 1 https://github.com/langfuse/langfuse.git '$dest'; else git -C '$dest' pull --ff-only; fi"
  echo "langfuse repo at $dest — start with its docker compose (not auto-started; secrets operator-owned)."
}

enable_hermes_auto_update() {
  [[ "$(id -u)" -eq 0 ]] || { echo "enabling timer needs root" >&2; return 2; }
  unit_dir=/etc/systemd/system
  install -m 0644 "$ROOT/scripts/systemd/station-hermes-update.service" "$unit_dir/"
  install -m 0644 "$ROOT/scripts/systemd/station-hermes-update.timer" "$unit_dir/"
  # Fix ExecStart to this checkout if relocated
  sed -i "s|/home/agk-station/repos/agentik-station|$ROOT|g" "$unit_dir/station-hermes-update.service"
  systemctl daemon-reload
  systemctl enable --now station-hermes-update.timer
  systemctl list-timers station-hermes-update.timer --no-pager || true
  echo "Hermes weekly auto-update timer enabled."
}

if [[ "$ENABLE_AUTO" -eq 1 ]]; then
  enable_hermes_auto_update
fi

if [[ "$ALL" -eq 1 ]]; then
  COMPONENTS=(ponytail langfuse honcho hindsight tigervnc crawl4ai)
fi

for id in "${COMPONENTS[@]}"; do
  case "$id" in
    ponytail) install_ponytail;;
    langfuse) install_langfuse;;
    honcho) install_honcho;;
    hindsight) install_hindsight;;
    tigervnc) install_tigervnc;;
    crawl4ai) install_crawl4ai;;
    *) echo "unknown component: $id" >&2; exit 2;;
  esac
done

echo
echo "Done. Maturity remains SCAFFOLDED until station doctor + component readback."
echo "Platforms: hermes gateway setup && hermes gateway start"
echo "Guide: $ROOT/docs/dependencies/HERMES_PLATFORMS.md"
