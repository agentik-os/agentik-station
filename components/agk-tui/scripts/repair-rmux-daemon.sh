#!/usr/bin/env bash
set -Eeuo pipefail

rmux_bin=${1:?usage: repair-rmux-daemon.sh /absolute/path/to/rmux}
[ -x "$rmux_bin" ] || { echo "RMUX executable is missing: $rmux_bin" >&2; exit 2; }

if output=$("$rmux_bin" list-sessions 2>&1); then
  status=0
else
  status=$?
fi
if [ "$status" -eq 0 ]; then
  [ -z "$output" ] || printf '%s\n' "$output"
  exit 0
fi
case "$output" in
  *": protocol error: unsupported RMUX wire version "*) ;;
  *) printf '%s\n' "$output" >&2; exit "$status" ;;
esac

endpoint=$(printf '%s\n' "$output" | sed -n \
  's/^\(.*\): protocol error: unsupported RMUX wire version .*$/\1/p' | head -n 1)
case "$endpoint" in
  /*) ;;
  *) echo "Could not resolve the incompatible RMUX socket safely." >&2; exit 1 ;;
esac
[ -S "$endpoint" ] || {
  echo "The incompatible RMUX endpoint is not a Unix socket: $endpoint" >&2
  exit 1
}
command -v lsof >/dev/null 2>&1 || {
  echo "lsof is required to replace an incompatible RMUX daemon safely." >&2
  exit 1
}

current_uid=$(id -u)
pids=()
while IFS= read -r pid; do
  case "$pid" in ''|*[!0-9]*) continue ;; esac
  pids+=("$pid")
done < <(lsof -n -t "$endpoint" 2>/dev/null | awk '!seen[$0]++')
[ "${#pids[@]}" -gt 0 ] || {
  echo "No process owns the incompatible RMUX socket: $endpoint" >&2
  exit 1
}

# Validate every owner before signaling any process. This keeps the recovery
# scoped to the exact current-user RMUX daemon named by the protocol error.
for pid in "${pids[@]}"; do
  owner_uid=$(ps -o uid= -p "$pid" 2>/dev/null | tr -d '[:space:]')
  command_line=$(ps -o command= -p "$pid" 2>/dev/null || true)
  [ "$owner_uid" = "$current_uid" ] || {
    echo "Refusing to stop RMUX socket owner $pid from another user." >&2
    exit 1
  }
  case "$command_line" in
    *rmux*|*RMUX*) ;;
    *)
      echo "Refusing to stop non-RMUX socket owner $pid: $command_line" >&2
      exit 1
      ;;
  esac
done

echo "  ! replacing incompatible current-user RMUX daemon (${pids[*]})"
for pid in "${pids[@]}"; do
  kill -TERM "$pid"
done
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
  alive=false
  for pid in "${pids[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then alive=true; break; fi
  done
  [ "$alive" = false ] && break
  sleep 0.1
done
for pid in "${pids[@]}"; do
  if kill -0 "$pid" 2>/dev/null; then
    echo "  ! RMUX daemon $pid did not stop after SIGTERM; forcing shutdown"
    kill -KILL "$pid"
  fi
done

if [ -S "$endpoint" ]; then
  backup="$endpoint.agk-incompatible.$(date -u +%Y%m%dT%H%M%SZ).$$"
  mv "$endpoint" "$backup"
  echo "  = preserved obsolete socket as $backup"
fi

if ! output=$("$rmux_bin" list-sessions 2>&1); then
  printf '%s\n' "$output" >&2
  echo "The RMUX 0.10.0 daemon did not start after protocol recovery." >&2
  exit 1
fi
[ -z "$output" ] || printf '%s\n' "$output"
echo "  = RMUX daemon protocol is compatible"
