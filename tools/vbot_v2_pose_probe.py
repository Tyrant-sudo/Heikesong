#!/usr/bin/env python3
"""Print coarse V2 pose telemetry without issuing robot commands."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

try:
    from heikesong.perception.coarse_human_pose import (
        CocoKeypoint,
        CoarsePoseFrame,
        CoarsePoseTracker,
        PoseKeypoint,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from heikesong.perception.coarse_human_pose import (
        CocoKeypoint,
        CoarsePoseFrame,
        CoarsePoseTracker,
        PoseKeypoint,
    )

import rclpy
from vision_msgs.msg import PoseDetection


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=30.0)
    parser.add_argument("--interval-seconds", type=float, default=0.4)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = rclpy.create_node("heikesong_v2_pose_probe")
    tracker = CoarsePoseTracker()
    started_at = time.monotonic()
    last_printed_at = 0.0

    def on_pose(message: PoseDetection) -> None:
        nonlocal last_printed_at
        now_s = time.monotonic()
        if message.class_id != 0 or now_s - last_printed_at < args.interval_seconds:
            return
        last_printed_at = now_s
        frame = CoarsePoseFrame(
            tuple(
                PoseKeypoint(point.x, point.y, point.confidence)
                for point in message.keypoints
            ),
            message.bbox_min.x,
            message.bbox_min.y,
            message.bbox_max.x,
            message.bbox_max.y,
            message.score,
            now_s,
        )
        observation = tracker.update(frame)
        selected = {}
        for keypoint in (
            CocoKeypoint.LEFT_SHOULDER,
            CocoKeypoint.RIGHT_SHOULDER,
            CocoKeypoint.LEFT_HIP,
            CocoKeypoint.RIGHT_HIP,
            CocoKeypoint.LEFT_ANKLE,
            CocoKeypoint.RIGHT_ANKLE,
        ):
            point = frame.keypoints[keypoint]
            selected[keypoint.name.lower()] = [
                round(point.x, 1),
                round(point.y, 1),
                round(point.confidence, 2),
            ]
        print(
            json.dumps(
                {
                    "label": observation.label.value,
                    "held_s": round(observation.label_held_for_s, 2),
                    "stationary_s": round(observation.stationary_for_s, 2),
                    "score": round(message.score, 3),
                    "bbox": [
                        round(message.bbox_min.x, 1),
                        round(message.bbox_min.y, 1),
                        round(message.bbox_max.x, 1),
                        round(message.bbox_max.y, 1),
                    ],
                    "points": selected,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    node.create_subscription(PoseDetection, "/perception/poses", on_pose, 10)
    try:
        while rclpy.ok() and time.monotonic() - started_at < args.duration_seconds:
            rclpy.spin_once(node, timeout_sec=0.1)
    finally:
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
