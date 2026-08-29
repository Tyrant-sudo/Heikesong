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

exec python3 "$BASE/tools/vbot_person_orbit_service_node.py" --ros-args \
  -p direction:="${HEIKESONG_ORBIT_DIRECTION:--1}" \
  -p orbit_duration_s:="${HEIKESONG_ORBIT_DURATION_SECONDS:-6.8}"
