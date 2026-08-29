#!/bin/bash
set -uo pipefail

BASE=/userdata/vbot/.local/share/heikesong/voice_kws
LOG_DIR=/userdata/vbot/.local/share/heikesong/logs
LOCK_FILE=/userdata/vbot/.local/share/heikesong/voice-person-tracker.lock
RUNNER="${HEIKESONG_RUNNER:-$BASE/bin/run_voice_person_tracker.sh}"
LOG_FILE="$LOG_DIR/voice-person-tracker-supervisor.log"

mkdir -p "$LOG_DIR"
if [[ ! -f "$RUNNER" ]]; then
  printf 'runner not found: %s\n' "$RUNNER" >&2
  exit 1
fi
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

child_pid=""
stop_child() {
  if [[ -n "$child_pid" ]] && kill -0 "$child_pid" 2>/dev/null; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  exit 0
}
trap stop_child INT TERM

while true; do
  printf '%s starting voice tracker\n' "$(date --iso-8601=seconds)" >>"$LOG_FILE"
  /bin/bash "$RUNNER" >>"$LOG_FILE" 2>&1 &
  child_pid=$!
  wait "$child_pid"
  status=$?
  printf '%s voice tracker exited status=%s; restarting in 3s\n' \
    "$(date --iso-8601=seconds)" "$status" >>"$LOG_FILE"
  child_pid=""
  sleep 3
done
