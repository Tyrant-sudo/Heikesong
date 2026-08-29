#!/bin/bash
set -eo pipefail

BASE=/userdata/vbot/.local/share/heikesong/voice_kws

export COLCON_CURRENT_PREFIX=/app/opt/ros/humble
. /app/opt/ros/humble/local_setup.sh
export COLCON_CURRENT_PREFIX=/app/idl_msgs
. /app/idl_msgs/local_setup.sh

set -u

export RMW_IMPLEMENTATION=rmw_zenoh_cpp
export ZENOH_SESSION_CONFIG_URI=/app_param/zenoh/s100_session.json5
export ZENOH_ROUTER_CHECK_ATTEMPTS=-1
export PYTHONPATH="$BASE/runtime:$BASE/src${PYTHONPATH:+:$PYTHONPATH}"

args=(
  --session-seconds "${HEIKESONG_V2_SESSION_SECONDS:-1800}"
  --keyword-model-dir "$BASE/model"
  --enable-v2
  --v2-pose-hold-seconds "${HEIKESONG_V2_POSE_HOLD_SECONDS:-1.2}"
  --v2-stationary-hold-seconds "${HEIKESONG_V2_STATIONARY_HOLD_SECONDS:-5.0}"
)

if [[ ${HEIKESONG_V2_ENABLE_MOTION:-1} == 1 ]]; then
  args+=(--enable-v2-motion)
fi

exec python3 "$BASE/tools/vbot_voice_person_tracker.py" "${args[@]}"
