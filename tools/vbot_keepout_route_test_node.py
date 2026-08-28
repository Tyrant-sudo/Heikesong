#!/usr/bin/env python3
"""Execute one low-speed corner bypass through the yoga-mat command gate."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import sys
import time

import cv2
import numpy as np
from camera_msgs.msg import JpegRequest
from camera_msgs.srv import GetJpegImages
from function_msgs.srv import BaseAction
from geometry_msgs.msg import Twist
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from software_msgs.msg import LocomotionStatus
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.safety.keepout import KeepoutZone, Pose2D  # noqa: E402
from heikesong.perception.ground_projection import (  # noqa: E402
    CameraIntrinsics,
    project_mat_boundary_to_world,
    quaternion_xyzw_to_matrix,
)
from heikesong.perception.yoga_mat_color import ColorYogaMatDetector  # noqa: E402
from heikesong.safety.route import (  # noqa: E402
    plan_corner_bypass,
    plan_full_orbit,
    point_to_polygon_distance,
    polyline_minimum_clearance,
)


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keepout-report", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--route-mode", choices=("corner-bypass", "full-orbit"), default="corner-bypass"
    )
    parser.add_argument("--side", choices=("left", "right"), default="right")
    parser.add_argument("--max-linear-speed-mps", type=float, default=0.05)
    parser.add_argument("--min-linear-speed-mps", type=float, default=0.05)
    parser.add_argument("--max-angular-speed-rps", type=float, default=0.10)
    parser.add_argument("--min-angular-speed-rps", type=float, default=0.10)
    parser.add_argument("--extra-route-margin-m", type=float, default=0.20)
    parser.add_argument("--distance-along-side-m", type=float, default=0.65)
    parser.add_argument("--position-tolerance-m", type=float, default=0.08)
    parser.add_argument("--approach-tolerance-m", type=float, default=0.08)
    parser.add_argument("--timeout-s", type=float, default=120.0)
    parser.add_argument("--max-head-body-yaw-rad", type=float, default=0.10)
    parser.add_argument("--max-head-body-pitch-drift-rad", type=float, default=0.08)
    parser.add_argument("--obstacle-stop-distance-m", type=float, default=0.65)
    parser.add_argument("--obstacle-half-width-m", type=float, default=0.38)
    parser.add_argument("--obstacle-min-z-m", type=float, default=-0.15)
    parser.add_argument("--obstacle-max-z-m", type=float, default=0.65)
    parser.add_argument("--lidar-timeout-s", type=float, default=0.8)
    parser.add_argument("--visual-interval-s", type=float, default=0.8)
    parser.add_argument("--visual-timeout-s", type=float, default=3.0)
    parser.add_argument("--visual-bottom-mat-fraction", type=float, default=0.30)
    parser.add_argument("--visual-map-drift-limit-m", type=float, default=0.35)
    return parser.parse_known_args()


def load_zone(path: Path) -> KeepoutZone:
    payload = json.loads(path.read_text(encoding="utf-8"))
    projection = payload.get("projection", payload)
    boundary = projection["keepout_boundary_map"]
    return KeepoutZone(tuple((float(point[0]), float(point[1])) for point in boundary))


class RouteTestNode(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("heikesong_keepout_route_test")
        self.args = args
        self.zone = load_zone(args.keepout_report)
        payload = json.loads(args.keepout_report.read_text(encoding="utf-8"))
        projection = payload.get("projection", payload)
        raw_boundary = projection.get("raw_boundary_map", [])
        self.reference_mat_center = (
            (
                sum(float(point[0]) for point in raw_boundary) / len(raw_boundary),
                sum(float(point[1]) for point in raw_boundary) / len(raw_boundary),
            )
            if raw_boundary
            else None
        )
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self)
        self.command_publisher = self.create_publisher(
            Twist, "/heikesong/nav/cmd_vel_requested", 10
        )
        latched_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.create_subscription(
            String,
            "/heikesong/nav/keepout_gate_status",
            self._on_gate_status,
            latched_qos,
        )
        self.create_subscription(LocomotionStatus, "/locomotion/status", self._on_loco, 10)
        self.create_subscription(Twist, "/adapter/vel_cmd", self._on_adapter_velocity, 10)
        self.create_subscription(PointCloud2, "/lidar_points", self._on_lidar, 10)
        self.visual_client = self.create_client(GetJpegImages, "/get_jpeg_images")
        self.base_action_client = self.create_client(BaseAction, "/base_action")
        self.visual_detector = ColorYogaMatDetector()
        self.gate_state: str | None = None
        self.gate_status_at: float | None = None
        self.locomotion: tuple[int, int, str] | None = None
        self.max_adapter_linear_mps = 0.0
        self.max_adapter_angular_rps = 0.0
        self.trajectory: list[dict[str, float]] = []
        self.gate_states: list[str] = []
        self.tf_pause_count = 0
        self.lidar_at: float | None = None
        self.front_obstacle_m: float | None = None
        self.maximum_head_body_yaw_rad = 0.0
        self.initial_head_body_pitch_rad: float | None = None
        self.maximum_head_body_pitch_drift_rad = 0.0
        self.visual_future = None
        self.visual_requested_at: float | None = None
        self.last_visual_at: float | None = None
        self.visual_sample_count = 0
        self.visual_projection_count = 0
        self.maximum_visual_bottom_mat_fraction = 0.0
        self.maximum_visual_map_drift_m = 0.0
        self.builtin_rotation_count = 0

    def _on_gate_status(self, message: String) -> None:
        try:
            state = str(json.loads(message.data)["state"])
        except (json.JSONDecodeError, KeyError, TypeError):
            state = "invalid_status"
        self.gate_state = state
        self.gate_status_at = time.monotonic()
        if not self.gate_states or self.gate_states[-1] != state:
            self.gate_states.append(state)

    def _on_loco(self, message: LocomotionStatus) -> None:
        self.locomotion = (int(message.posture), int(message.motion), message.current_action)

    def _on_adapter_velocity(self, message: Twist) -> None:
        self.max_adapter_linear_mps = max(
            self.max_adapter_linear_mps,
            math.hypot(float(message.linear.x), float(message.linear.y)),
        )
        self.max_adapter_angular_rps = max(
            self.max_adapter_angular_rps, abs(float(message.angular.z))
        )

    def _on_lidar(self, message: PointCloud2) -> None:
        try:
            transform = self.tf_buffer.lookup_transform(
                "base_link", message.header.frame_id, Time()
            )
        except TransformException:
            return
        rotation = transform.transform.rotation
        translation = transform.transform.translation
        quaternion = (rotation.x, rotation.y, rotation.z, rotation.w)
        nearest: float | None = None
        for row in point_cloud2.read_points(
            message, field_names=("x", "y", "z"), skip_nans=True
        ):
            rotated = self._rotate_vector(
                quaternion, (float(row[0]), float(row[1]), float(row[2]))
            )
            x = rotated[0] + float(translation.x)
            y = rotated[1] + float(translation.y)
            z = rotated[2] + float(translation.z)
            if not (
                0.08 < x < self.args.obstacle_stop_distance_m
                and abs(y) < self.args.obstacle_half_width_m
                and self.args.obstacle_min_z_m < z < self.args.obstacle_max_z_m
            ):
                continue
            distance = math.hypot(x, y)
            nearest = distance if nearest is None else min(nearest, distance)
        self.front_obstacle_m = nearest
        self.lidar_at = time.monotonic()

    def pose(self) -> Pose2D:
        transform = self.tf_buffer.lookup_transform("map", "base_link", Time())
        stamp = Time.from_msg(transform.header.stamp)
        age_s = (self.get_clock().now() - stamp).nanoseconds / 1e9
        if age_s > 1.0:
            raise RuntimeError(f"stale map-base_link TF: {age_s:.3f}s")
        position = transform.transform.translation
        orientation = transform.transform.rotation
        yaw = math.atan2(
            2.0 * (orientation.w * orientation.z + orientation.x * orientation.y),
            1.0 - 2.0 * (orientation.y * orientation.y + orientation.z * orientation.z),
        )
        return Pose2D(float(position.x), float(position.y), yaw)

    @staticmethod
    def _rotate_vector(
        quaternion: tuple[float, float, float, float],
        vector: tuple[float, float, float],
    ) -> tuple[float, float, float]:
        x, y, z, w = quaternion
        vx, vy, vz = vector
        tx = 2.0 * (y * vz - z * vy)
        ty = 2.0 * (z * vx - x * vz)
        tz = 2.0 * (x * vy - y * vx)
        return (
            vx + w * tx + y * tz - z * ty,
            vy + w * ty + z * tx - x * tz,
            vz + w * tz + x * ty - y * tx,
        )

    def head_body_angles(self) -> tuple[float, float]:
        transform = self.tf_buffer.lookup_transform("base_link", "stereo_left", Time())
        rotation = transform.transform.rotation
        camera_forward = self._rotate_vector(
            (rotation.x, rotation.y, rotation.z, rotation.w), (0.0, 0.0, 1.0)
        )
        return (
            math.atan2(camera_forward[1], camera_forward[0]),
            math.atan2(
                camera_forward[2], math.hypot(camera_forward[0], camera_forward[1])
            ),
        )

    def assert_dynamic_safety(self, pose: Pose2D) -> float:
        self.update_visual_guard()
        if self.lidar_at is None:
            raise RuntimeError("lidar has not produced a usable cloud")
        lidar_age = time.monotonic() - self.lidar_at
        if lidar_age > self.args.lidar_timeout_s:
            raise RuntimeError(f"lidar data stale: {lidar_age:.3f}s")
        if self.front_obstacle_m is not None:
            raise RuntimeError(
                f"front obstacle inside stop corridor: {self.front_obstacle_m:.3f}m"
            )
        relative_yaw, relative_pitch = self.head_body_angles()
        if self.initial_head_body_pitch_rad is None:
            self.initial_head_body_pitch_rad = relative_pitch
        pitch_drift = abs(relative_pitch - self.initial_head_body_pitch_rad)
        self.maximum_head_body_yaw_rad = max(
            self.maximum_head_body_yaw_rad, abs(relative_yaw)
        )
        self.maximum_head_body_pitch_drift_rad = max(
            self.maximum_head_body_pitch_drift_rad, pitch_drift
        )
        if abs(relative_yaw) > self.args.max_head_body_yaw_rad:
            raise RuntimeError(
                f"head/body yaw exceeded limit: {relative_yaw:.3f}rad"
            )
        if pitch_drift > self.args.max_head_body_pitch_drift_rad:
            raise RuntimeError(
                f"head/body pitch drift exceeded limit: {pitch_drift:.3f}rad"
            )
        return relative_yaw

    def update_visual_guard(self) -> None:
        now = time.monotonic()
        if self.visual_future is not None and self.visual_future.done():
            future = self.visual_future
            self.visual_future = None
            if future.exception() is not None:
                raise RuntimeError(f"visual capture failed: {future.exception()}")
            response = future.result()
            if not response.response or int(response.response[0].status) != 0:
                raise RuntimeError("visual capture returned no usable frame")
            encoded = np.frombuffer(bytes(response.response[0].data), dtype=np.uint8)
            image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError("visual JPEG decode failed")
            self._analyze_visual_frame(image)
            self.last_visual_at = now
            self.visual_sample_count += 1

        if self.visual_future is not None:
            if (
                self.visual_requested_at is not None
                and now - self.visual_requested_at > self.args.visual_timeout_s
            ):
                raise RuntimeError("visual capture timeout")
            return

        if (
            self.last_visual_at is None
            or now - self.last_visual_at >= self.args.visual_interval_s
        ):
            if not self.visual_client.service_is_ready():
                if not self.visual_client.wait_for_service(timeout_sec=0.05):
                    if self.last_visual_at is None:
                        return
                    if now - self.last_visual_at > self.args.visual_timeout_s:
                        raise RuntimeError("visual service unavailable")
                    return
            request = GetJpegImages.Request()
            jpeg = JpegRequest()
            jpeg.channel_id = 0
            jpeg.width = 480
            jpeg.height = 270
            jpeg.quality = 70
            jpeg.undistort = True
            request.request.append(jpeg)
            self.visual_future = self.visual_client.call_async(request)
            self.visual_requested_at = now

    def _analyze_visual_frame(self, image: np.ndarray) -> None:
        analysis = self.visual_detector.analyze(image)
        height, width = image.shape[:2]
        region = analysis.mask[int(height * 0.78) :, int(width * 0.30) : int(width * 0.70)]
        bottom_fraction = float(np.count_nonzero(region)) / float(region.size)
        self.maximum_visual_bottom_mat_fraction = max(
            self.maximum_visual_bottom_mat_fraction, bottom_fraction
        )
        current_pose = self.pose()
        current_clearance = point_to_polygon_distance(
            (current_pose.x, current_pose.y), self.zone.boundary
        )
        if (
            bottom_fraction >= self.args.visual_bottom_mat_fraction
            and current_clearance < 0.12
        ):
            raise RuntimeError(
                f"visual mat-underfoot guard triggered: {bottom_fraction:.3f}"
            )
        if not analysis.observation.detected or self.reference_mat_center is None:
            return

        transform = self.tf_buffer.lookup_transform("map", "stereo_left", Time())
        rotation = transform.transform.rotation
        translation = transform.transform.translation
        boundary = np.asarray(
            [[point.x, point.y] for point in analysis.observation.boundary],
            dtype=np.float64,
        )
        try:
            projected = project_mat_boundary_to_world(
                boundary,
                CameraIntrinsics(
                    162.14315136170416, 162.14315136170416, 239.5, 134.5
                ),
                quaternion_xyzw_to_matrix(
                    (rotation.x, rotation.y, rotation.z, rotation.w)
                ),
                np.asarray(
                    [translation.x, translation.y, translation.z], dtype=np.float64
                ),
            )
        except ValueError:
            return
        drift = math.dist(projected.center_world[:2], self.reference_mat_center)
        self.maximum_visual_map_drift_m = max(self.maximum_visual_map_drift_m, drift)
        self.visual_projection_count += 1
        if drift > self.args.visual_map_drift_limit_m:
            raise RuntimeError(f"visual mat map drift exceeded limit: {drift:.3f}m")

    def wait_ready(self, seconds: float = 20.0) -> Pose2D:
        deadline = time.monotonic() + seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            try:
                pose = self.pose()
            except (TransformException, RuntimeError) as error:
                last_error = error
                continue
            if (
                self.locomotion
                and self.locomotion[0] == 1
                and self.gate_state
                in {"keepout_loaded", "allowed", "stopped_command_timeout"}
                and self.lidar_at is not None
                and self.last_visual_at is not None
            ):
                self.assert_dynamic_safety(pose)
                return pose
        raise RuntimeError(
            f"route not ready: locomotion={self.locomotion}, gate={self.gate_state}, "
            f"tf_error={last_error}"
        )

    def stop(self) -> None:
        zero = Twist()
        for _ in range(10):
            self.command_publisher.publish(zero)
            rclpy.spin_once(self, timeout_sec=0.03)

    def cancel_builtin_rotation(self) -> None:
        if not self.base_action_client.service_is_ready():
            return
        request = BaseAction.Request()
        request.target_state = 0
        request.mode = BaseAction.Request.ROTATE_IN_PLACE
        request.req_id = "HEIKESONG-ORBIT-ROTATE-CANCEL"
        request.pre_check = False
        self.base_action_client.call_async(request)

    def rotate_in_place(self, angle_rad: float) -> None:
        self.stop()
        before = self.pose()
        request = BaseAction.Request()
        request.target_state = 1
        request.mode = BaseAction.Request.ROTATE_IN_PLACE
        request.req_id = (
            f"HEIKESONG-ORBIT-ROTATE-{self.builtin_rotation_count + 1}-"
            f"{time.monotonic_ns()}"
        )
        request.pre_check = False
        request.angle_rad = float(angle_rad)
        future = self.base_action_client.call_async(request)
        deadline = time.monotonic() + 12.0
        try:
            while not future.done() and time.monotonic() < deadline:
                rclpy.spin_once(self, timeout_sec=0.04)
                current = self.pose()
                self.assert_dynamic_safety(current)
                if self.locomotion is None or self.locomotion[0] != 1:
                    raise RuntimeError(
                        f"locomotion left standing during rotation: {self.locomotion}"
                    )
            if not future.done():
                raise RuntimeError("built-in rotation timeout")
            if future.exception() is not None:
                raise RuntimeError(f"built-in rotation failed: {future.exception()}")
            if not future.result().success:
                raise RuntimeError(f"built-in rotation rejected: {future.result()}")
            after = self.pose()
            actual = abs(
                math.atan2(
                    math.sin(after.yaw - before.yaw),
                    math.cos(after.yaw - before.yaw),
                )
            )
            if abs(angle_rad) >= 0.20 and actual < min(0.20, abs(angle_rad) * 0.5):
                raise RuntimeError(
                    f"built-in rotation completed without enough yaw: {actual:.3f}rad"
                )
            self.builtin_rotation_count += 1
        except Exception:
            self.cancel_builtin_rotation()
            raise
        finally:
            self.stop()

    def recover_fresh_pose(self, seconds: float = 3.0) -> Pose2D:
        self.stop()
        self.tf_pause_count += 1
        deadline = time.monotonic() + seconds
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=0.05)
            try:
                return self.pose()
            except (TransformException, RuntimeError) as error:
                last_error = error
        raise RuntimeError(f"robot transform did not recover after stop: {last_error}")

    def run(self) -> dict[str, object]:
        if self.args.min_linear_speed_mps > self.args.max_linear_speed_mps:
            raise ValueError("minimum linear speed exceeds maximum linear speed")
        if self.args.min_angular_speed_rps > self.args.max_angular_speed_rps:
            raise ValueError("minimum angular speed exceeds maximum angular speed")
        if not self.base_action_client.wait_for_service(timeout_sec=4.0):
            raise RuntimeError("base action service unavailable")
        started = time.monotonic()
        initial = self.wait_ready()
        if self.args.route_mode == "full-orbit":
            plan = plan_full_orbit(
                self.zone,
                (initial.x, initial.y),
                initial.yaw,
                side=self.args.side,
                extra_margin_m=self.args.extra_route_margin_m,
            )
        else:
            plan = plan_corner_bypass(
                self.zone,
                (initial.x, initial.y),
                initial.yaw,
                side=self.args.side,
                extra_margin_m=self.args.extra_route_margin_m,
                distance_along_side_m=self.args.distance_along_side_m,
            )
        planned_points = ((initial.x, initial.y),) + plan.waypoints
        planned_clearance = polyline_minimum_clearance(planned_points, self.zone.boundary)
        initial_clearance = point_to_polygon_distance(
            (initial.x, initial.y), self.zone.boundary
        )
        required_planned_clearance = min(
            initial_clearance, self.args.extra_route_margin_m
        )
        if planned_clearance < required_planned_clearance - 0.02:
            raise RuntimeError(f"planned clearance too small: {planned_clearance:.3f}m")

        waypoint_index = 0
        outcome = "running"
        next_tick = time.monotonic()
        last_trajectory_at = -math.inf
        last_progress_at = -math.inf
        progress_pose = initial
        progress_at = time.monotonic()
        while waypoint_index < len(plan.waypoints):
            if time.monotonic() - started > self.args.timeout_s:
                raise RuntimeError("route timeout")
            rclpy.spin_once(self, timeout_sec=0.02)
            if self.locomotion is None or self.locomotion[0] != 1:
                raise RuntimeError(f"locomotion left standing state: {self.locomotion}")
            if self.gate_state and self.gate_state.startswith("blocked"):
                raise RuntimeError(f"command gate blocked route: {self.gate_state}")
            try:
                pose = self.pose()
            except (TransformException, RuntimeError):
                pose = self.recover_fresh_pose()
            relative_head_yaw = self.assert_dynamic_safety(pose)
            yaw_progress = abs(
                math.atan2(
                    math.sin(pose.yaw - progress_pose.yaw),
                    math.cos(pose.yaw - progress_pose.yaw),
                )
            )
            if (
                math.hypot(pose.x - progress_pose.x, pose.y - progress_pose.y) >= 0.025
                or yaw_progress >= 0.025
            ):
                progress_pose = pose
                progress_at = time.monotonic()
            elif time.monotonic() - progress_at > 8.0:
                raise RuntimeError("no TF pose progress for 8 seconds")
            clearance = point_to_polygon_distance((pose.x, pose.y), self.zone.boundary)
            if self.zone.contains((pose.x, pose.y)) or clearance < 0.10:
                raise RuntimeError(f"keepout clearance violated: {clearance:.3f}m")
            target = plan.waypoints[waypoint_index]
            dx, dy = target[0] - pose.x, target[1] - pose.y
            distance = math.hypot(dx, dy)
            elapsed = time.monotonic() - started
            if elapsed - last_trajectory_at >= 0.18:
                self.trajectory.append(
                    {
                        "elapsed_s": elapsed,
                        "x": pose.x,
                        "y": pose.y,
                        "yaw": pose.yaw,
                        "clearance_m": clearance,
                        "head_body_yaw_rad": relative_head_yaw,
                        "head_body_pitch_drift_rad": self.maximum_head_body_pitch_drift_rad,
                        "front_obstacle_m": self.front_obstacle_m,
                        "waypoint": float(waypoint_index),
                    }
                )
                last_trajectory_at = elapsed
            if elapsed - last_progress_at >= 5.0:
                print(
                    "ROUTE_PROGRESS "
                    + json.dumps(
                        {
                            "elapsed_s": round(elapsed, 2),
                            "waypoint": waypoint_index,
                            "waypoint_count": len(plan.waypoints),
                            "distance_m": round(distance, 3),
                            "clearance_m": round(clearance, 3),
                            "head_body_yaw_rad": round(relative_head_yaw, 4),
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
                last_progress_at = elapsed
            tolerance = (
                self.args.approach_tolerance_m
                if self.args.route_mode == "full-orbit" and waypoint_index == 0
                else self.args.position_tolerance_m
            )
            if distance <= tolerance:
                self.stop()
                waypoint_index += 1
                progress_pose = pose
                progress_at = time.monotonic()
                continue
            desired_yaw = math.atan2(dy, dx)
            heading_error = math.atan2(
                math.sin(desired_yaw - pose.yaw), math.cos(desired_yaw - pose.yaw)
            )
            command = Twist()
            if abs(heading_error) > 0.08:
                self.rotate_in_place(heading_error)
                progress_pose = self.pose()
                progress_at = time.monotonic()
                continue
            else:
                command.linear.x = min(
                    self.args.max_linear_speed_mps,
                    max(self.args.min_linear_speed_mps, 0.5 * distance),
                )
            self.command_publisher.publish(command)
            next_tick = max(next_tick + 0.10, time.monotonic())
            while time.monotonic() < next_tick:
                rclpy.spin_once(
                    self,
                    timeout_sec=min(0.02, next_tick - time.monotonic()),
                )

        outcome = "completed"
        final_pose = self.pose()
        return {
            "result": outcome,
            "motion_commands_sent": True,
            "route_mode": self.args.route_mode,
            "keepout_report": str(self.args.keepout_report),
            "side": plan.side,
            "initial_pose": {"x": initial.x, "y": initial.y, "yaw": initial.yaw},
            "waypoints": [list(point) for point in plan.waypoints],
            "final_pose": {"x": final_pose.x, "y": final_pose.y, "yaw": final_pose.yaw},
            "planned_minimum_clearance_m": planned_clearance,
            "observed_minimum_clearance_m": min(
                point["clearance_m"] for point in self.trajectory
            ),
            "max_adapter_linear_mps": self.max_adapter_linear_mps,
            "max_adapter_angular_rps": self.max_adapter_angular_rps,
            "maximum_head_body_yaw_rad": self.maximum_head_body_yaw_rad,
            "maximum_head_body_pitch_drift_rad": self.maximum_head_body_pitch_drift_rad,
            "lidar_stop_distance_m": self.args.obstacle_stop_distance_m,
            "visual_sample_count": self.visual_sample_count,
            "visual_projection_count": self.visual_projection_count,
            "maximum_visual_bottom_mat_fraction": self.maximum_visual_bottom_mat_fraction,
            "maximum_visual_map_drift_m": self.maximum_visual_map_drift_m,
            "builtin_rotation_count": self.builtin_rotation_count,
            "gate_states": self.gate_states,
            "tf_pause_count": self.tf_pause_count,
            "locomotion_final": self.locomotion,
            "elapsed_s": time.monotonic() - started,
            "trajectory": self.trajectory,
        }


def main() -> int:
    args, ros_args = parse_args()
    rclpy.init(args=ros_args)
    node = RouteTestNode(args)
    result: dict[str, object]
    exit_code = 0
    try:
        result = node.run()
    except Exception as error:
        exit_code = 2
        result = {
            "result": "aborted",
            "error": str(error),
            "motion_commands_sent": bool(node.trajectory),
            "gate_states": node.gate_states,
            "tf_pause_count": node.tf_pause_count,
            "locomotion_final": node.locomotion,
            "max_adapter_linear_mps": node.max_adapter_linear_mps,
            "max_adapter_angular_rps": node.max_adapter_angular_rps,
            "maximum_head_body_yaw_rad": node.maximum_head_body_yaw_rad,
            "maximum_head_body_pitch_drift_rad": node.maximum_head_body_pitch_drift_rad,
            "visual_sample_count": node.visual_sample_count,
            "visual_projection_count": node.visual_projection_count,
            "maximum_visual_bottom_mat_fraction": node.maximum_visual_bottom_mat_fraction,
            "maximum_visual_map_drift_m": node.maximum_visual_map_drift_m,
            "builtin_rotation_count": node.builtin_rotation_count,
            "observed_minimum_clearance_m": (
                min(point["clearance_m"] for point in node.trajectory)
                if node.trajectory
                else None
            ),
            "trajectory": node.trajectory,
        }
    finally:
        node.stop()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        console_result = {key: value for key, value in result.items() if key != "trajectory"}
        console_result["trajectory_point_count"] = len(result.get("trajectory", []))
        print(json.dumps(console_result, indent=2), flush=True)
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
