#!/bin/bash
set -uo pipefail

BASE=/userdata/vbot/.local/share/heikesong/voice_kws
LOG_DIR=/userdata/vbot/.local/share/heikesong/logs
LOCK_FILE=/userdata/vbot/.local/share/heikesong/person-orbit-service.lock
RUNNER="$BASE/bin/run_vbot_person_orbit_service.sh"
LOG_FILE="$LOG_DIR/person-orbit-service-supervisor.log"

mkdir -p "$LOG_DIR"
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
  printf '%s starting person orbit service\n' "$(date --iso-8601=seconds)" \
    >>"$LOG_FILE"
  /bin/bash "$RUNNER" >>"$LOG_FILE" 2>&1 &
  child_pid=$!
  wait "$child_pid"
  status=$?
  printf '%s person orbit service exited status=%s; restarting in 3s\n' \
    "$(date --iso-8601=seconds)" "$status" >>"$LOG_FILE"
  child_pid=""
  sleep 3
done
