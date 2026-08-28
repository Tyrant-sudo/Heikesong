#!/usr/bin/env python3
"""Gate project-owned velocity requests against the yoga-mat keepout zone."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

from geometry_msgs.msg import PolygonStamped, Twist
import rclpy
from rclpy.node import Node
from rclpy.executors import ExternalShutdownException
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.safety.keepout import (  # noqa: E402
    KeepoutMotionGate,
    KeepoutZone,
    Motion2D,
    Pose2D,
)


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enable-motion-output", action="store_true")
    parser.add_argument("--prediction-horizon-s", type=float, default=1.0)
    parser.add_argument("--keepout-report", type=Path)
    parser.add_argument("--max-linear-speed-mps", type=float, default=0.05)
    parser.add_argument("--max-angular-speed-rps", type=float, default=0.10)
    parser.add_argument("--command-timeout-s", type=float, default=0.35)
    return parser.parse_known_args()


class KeepoutCommandGateNode(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("heikesong_keepout_cmd_gate")
        self.args = args
        self.zone: KeepoutZone | None = None
        self.last_command_at: float | None = None
        self.timeout_stopped = False
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        latched_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(
            PolygonStamped,
            "/heikesong/yoga_mat/keepout_map",
            self._on_keepout,
            latched_qos,
        )
        self.create_subscription(
            Twist,
            "/heikesong/nav/cmd_vel_requested",
            self._on_command,
            10,
        )
        output_topic = "/vel_cmd" if args.enable_motion_output else "/heikesong/nav/cmd_vel_safe"
        self.command_publisher = self.create_publisher(Twist, output_topic, 10)
        self.status_publisher = self.create_publisher(
            String, "/heikesong/nav/keepout_gate_status", latched_qos
        )
        self.create_timer(0.05, self._watch_command_timeout)
        if args.keepout_report:
            self.zone = self._load_keepout_report(args.keepout_report)
        self._publish_status("waiting", output_topic=output_topic)
        if self.zone is not None:
            self._publish_status(
                "keepout_loaded",
                point_count=len(self.zone.boundary),
                source=str(args.keepout_report),
            )

    @staticmethod
    def _load_keepout_report(path: Path) -> KeepoutZone:
        payload = json.loads(path.read_text(encoding="utf-8"))
        projection = payload.get("projection", payload)
        boundary = projection.get("keepout_boundary_map")
        if not isinstance(boundary, list) or len(boundary) < 3:
            raise ValueError(f"invalid keepout report: {path}")
        return KeepoutZone(tuple((float(point[0]), float(point[1])) for point in boundary))

    def _on_keepout(self, message: PolygonStamped) -> None:
        if message.header.frame_id != "map" or len(message.polygon.points) < 3:
            self.zone = None
            self._publish_status("invalid_keepout")
            return
        self.zone = KeepoutZone(
            tuple((float(point.x), float(point.y)) for point in message.polygon.points)
        )
        self._publish_status("keepout_loaded", point_count=len(self.zone.boundary))

    def _current_pose(self) -> Pose2D | None:
        try:
            transform = self.tf_buffer.lookup_transform("map", "base_link", Time())
        except TransformException as error:
            self._publish_status("blocked_no_robot_transform", error=str(error))
            return None
        position = transform.transform.translation
        orientation = transform.transform.rotation
        yaw = math.atan2(
            2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
            1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
        )
        return Pose2D(float(position.x), float(position.y), yaw)

    def _on_command(self, message: Twist) -> None:
        self.last_command_at = time.monotonic()
        self.timeout_stopped = False
        pose = self._current_pose()
        if self.zone is None or pose is None:
            self.command_publisher.publish(Twist())
            self._publish_status("blocked_not_ready")
            return
        linear_speed = math.hypot(float(message.linear.x), float(message.linear.y))
        angular_speed = abs(float(message.angular.z))
        if (
            linear_speed > self.args.max_linear_speed_mps + 1e-9
            or angular_speed > self.args.max_angular_speed_rps + 1e-9
        ):
            self.command_publisher.publish(Twist())
            self._publish_status(
                "blocked_speed_limit",
                requested_linear_mps=linear_speed,
                requested_angular_rps=angular_speed,
            )
            return
        gate = KeepoutMotionGate(
            self.zone,
            prediction_horizon_s=self.args.prediction_horizon_s,
        )
        motion = Motion2D(
            float(message.linear.x),
            float(message.linear.y),
            float(message.angular.z),
        )
        if gate.command_allowed(pose, motion):
            self.command_publisher.publish(message)
            self._publish_status("allowed")
        else:
            self.command_publisher.publish(Twist())
            self._publish_status("blocked_keepout")

    def _watch_command_timeout(self) -> None:
        if self.last_command_at is None or self.timeout_stopped:
            return
        elapsed = time.monotonic() - self.last_command_at
        if elapsed <= self.args.command_timeout_s:
            return
        self.command_publisher.publish(Twist())
        self.timeout_stopped = True
        self._publish_status("stopped_command_timeout", elapsed_s=elapsed)

    def _publish_status(self, state: str, **details: object) -> None:
        message = String()
        message.data = json.dumps(
            {
                "state": state,
                "motion_output_enabled": self.args.enable_motion_output,
                **details,
            },
            separators=(",", ":"),
        )
        self.status_publisher.publish(message)


def main() -> int:
    args, ros_args = parse_args()
    rclpy.init(args=ros_args)
    node = KeepoutCommandGateNode(args)
    try:
        try:
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0.2)
        except ExternalShutdownException:
            pass
    finally:
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
