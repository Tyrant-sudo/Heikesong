#!/bin/bash
set -euo pipefail

BASE=/userdata/vbot/.local/share/heikesong/voice_kws
export HEIKESONG_RUNNER="$BASE/bin/run_vbot_v2_demo.sh"
export HEIKESONG_V2_ENABLE_MOTION="${HEIKESONG_V2_ENABLE_MOTION:-0}"

exec "$BASE/bin/run_vbot_voice_person_tracker_supervisor.sh"
