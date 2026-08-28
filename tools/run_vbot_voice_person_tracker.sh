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

exec python3 "$BASE/tools/vbot_voice_person_tracker.py" \
  --session-seconds 1800 \
  --keyword-model-dir "$BASE/model"
