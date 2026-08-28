#!/usr/bin/env python3
"""Rotate once in place and verify that the yoga mat enters the camera view."""

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
from geometry_msgs.msg import Twist
from lowlevel_msg.srv import HeadAction
import rclpy
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from software_msgs.msg import LocomotionStatus
from std_msgs.msg import String
from tf2_ros import Buffer, TransformListener


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.perception.yoga_mat_color import ColorYogaMatDetector  # noqa: E402
from heikesong.safety.keepout import KeepoutZone  # noqa: E402
from heikesong.safety.route import point_to_polygon_distance  # noqa: E402


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--keepout-report", type=Path, required=True)
    parser.add_argument("--capture-interval-s", type=float, default=0.80)
    parser.add_argument("--timeout-s", type=float, default=25.0)
    parser.add_argument("--minimum-mask-fraction", type=float, default=0.005)
    parser.add_argument("--bottom-mat-fraction", type=float, default=0.30)
    parser.add_argument("--max-head-body-yaw-rad", type=float, default=0.65)
    parser.add_argument("--max-head-body-pitch-drift-rad", type=float, default=0.45)
    return parser.parse_known_args()


class MatScanNode:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        payload = json.loads(args.keepout_report.read_text(encoding="utf-8"))
        projection = payload.get("projection", payload)
        self.zone = KeepoutZone(
            tuple(
                tuple(float(value) for value in point)
                for point in projection["keepout_boundary_map"]
            )
        )
        self.node = rclpy.create_node("heikesong_yoga_mat_scan")
        self.publisher = self.node.create_publisher(
            Twist, "/heikesong/nav/cmd_vel_requested", 10
        )
        self.camera = self.node.create_client(GetJpegImages, "/get_jpeg_images")
        self.head_action = self.node.create_client(HeadAction, "/head_action")
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self.node)
        self.detector = ColorYogaMatDetector()
        self.locomotion: tuple[int, int, str] | None = None
        self.gate_state: str | None = None
        self.visual_future = None
        self.visual_requested_at = -math.inf
        self.frame_count = 0
        self.mat_seen_count = 0
        self.complete_detection_count = 0
        self.maximum_mask_fraction = 0.0
        self.maximum_bottom_fraction = 0.0
        self.maximum_head_yaw = 0.0
        self.initial_head_pitch: float | None = None
        self.maximum_head_pitch_drift = 0.0
        self.lookaround_active = False
        self.node.create_subscription(
            LocomotionStatus, "/locomotion/status", self._on_locomotion, 10
        )
        latched_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.node.create_subscription(
            String, "/heikesong/nav/keepout_gate_status", self._on_gate, latched_qos
        )

    def _on_locomotion(self, message: LocomotionStatus) -> None:
        self.locomotion = (message.posture, message.motion, message.current_action)

    def _on_gate(self, message: String) -> None:
        try:
            self.gate_state = str(json.loads(message.data)["state"])
        except (json.JSONDecodeError, KeyError, TypeError):
            self.gate_state = "invalid_status"

    @staticmethod
    def _yaw(quaternion: object) -> float:
        return math.atan2(
            2.0 * (quaternion.w * quaternion.z + quaternion.x * quaternion.y),
            1.0 - 2.0 * (quaternion.y**2 + quaternion.z**2),
        )

    @staticmethod
    def _rotate_vector(quaternion: object) -> tuple[float, float, float]:
        x, y, z, w = quaternion.x, quaternion.y, quaternion.z, quaternion.w
        tx, ty, tz = 2.0 * y, -2.0 * x, 0.0
        return (w * tx + y * tz - z * ty, w * ty + z * tx - x * tz, 1.0 + x * ty - y * tx)

    def _head_guard(self) -> None:
        transform = self.tf_buffer.lookup_transform("base_link", "stereo_left", Time())
        forward = self._rotate_vector(transform.transform.rotation)
        yaw = math.atan2(forward[1], forward[0])
        pitch = math.atan2(forward[2], math.hypot(forward[0], forward[1]))
        if self.initial_head_pitch is None:
            self.initial_head_pitch = pitch
        drift = abs(pitch - self.initial_head_pitch)
        self.maximum_head_yaw = max(self.maximum_head_yaw, abs(yaw))
        self.maximum_head_pitch_drift = max(self.maximum_head_pitch_drift, drift)
        if abs(yaw) > self.args.max_head_body_yaw_rad:
            raise RuntimeError(f"head/body yaw exceeded limit: {yaw:.3f}rad")
        if drift > self.args.max_head_body_pitch_drift_rad:
            raise RuntimeError(f"head/body pitch drift exceeded limit: {drift:.3f}rad")

    def _update_camera(self) -> None:
        now = time.monotonic()
        if self.visual_future is not None and self.visual_future.done():
            future = self.visual_future
            self.visual_future = None
            if future.exception() is not None:
                raise RuntimeError(f"camera capture failed: {future.exception()}")
            response = future.result()
            if not response.response or int(response.response[0].status) != 0:
                raise RuntimeError("camera returned no usable frame")
            image = cv2.imdecode(
                np.frombuffer(bytes(response.response[0].data), dtype=np.uint8),
                cv2.IMREAD_COLOR,
            )
            if image is None:
                raise RuntimeError("camera JPEG decode failed")
            analysis = self.detector.analyze(image)
            mask_fraction = float(np.count_nonzero(analysis.mask)) / float(analysis.mask.size)
            height, width = image.shape[:2]
            bottom = analysis.mask[
                int(height * 0.78) :, int(width * 0.30) : int(width * 0.70)
            ]
            bottom_fraction = float(np.count_nonzero(bottom)) / float(bottom.size)
            self.frame_count += 1
            self.maximum_mask_fraction = max(self.maximum_mask_fraction, mask_fraction)
            self.maximum_bottom_fraction = max(
                self.maximum_bottom_fraction, bottom_fraction
            )
            if mask_fraction >= self.args.minimum_mask_fraction:
                self.mat_seen_count += 1
            if analysis.observation.detected:
                self.complete_detection_count += 1
            try:
                transform = self.tf_buffer.lookup_transform("map", "base_link", Time())
                position = transform.transform.translation
                clearance = point_to_polygon_distance(
                    (float(position.x), float(position.y)), self.zone.boundary
                )
                if (
                    bottom_fraction >= self.args.bottom_mat_fraction
                    and clearance < 0.12
                ):
                    raise RuntimeError(
                        f"visual mat-underfoot guard triggered: {bottom_fraction:.3f}"
                    )
            except Exception as error:
                if isinstance(error, RuntimeError):
                    raise

        if self.visual_future is None and (
            now - self.visual_requested_at >= self.args.capture_interval_s
        ):
            request = GetJpegImages.Request()
            jpeg = JpegRequest()
            jpeg.channel_id = 0
            jpeg.width = 480
            jpeg.height = 270
            jpeg.quality = 70
            jpeg.undistort = True
            request.request.append(jpeg)
            self.visual_future = self.camera.call_async(request)
            self.visual_requested_at = now

    def _stop(self) -> None:
        for _ in range(15):
            self.publisher.publish(Twist())
            rclpy.spin_once(self.node, timeout_sec=0.03)
        if self.lookaround_active and self.head_action.service_is_ready():
            request = HeadAction.Request()
            request.target_state = 0
            request.mode = HeadAction.Request.STREAM
            request.req_id = "HEIKESONG-LOOKAROUND-CANCEL"
            request.pre_check = False
            request.action_path = ""
            request.duration_ms = 0
            request.loop_enabled = False
            request.playback_rate = 1.0
            request.target_angles = []
            self.head_action.call_async(request)
            self.lookaround_active = False

    def run(self) -> dict[str, object]:
        if not self.camera.wait_for_service(timeout_sec=4.0):
            raise RuntimeError("camera service unavailable")
        if not self.head_action.wait_for_service(timeout_sec=4.0):
            raise RuntimeError("head action service unavailable")
        deadline = time.monotonic() + 6.0
        yaw_previous = None
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.05)
            self._update_camera()
            try:
                self._head_guard()
                transform = self.tf_buffer.lookup_transform("map", "base_link", Time())
            except Exception:
                continue
            yaw_previous = self._yaw(transform.transform.rotation)
            if (
                self.locomotion
                and self.locomotion[0] == 1
                and self.locomotion[2] == "RL_TROT"
                and self.gate_state == "keepout_loaded"
                and self.frame_count > 0
            ):
                break
        else:
            raise RuntimeError("scan prerequisites did not become ready")

        request = HeadAction.Request()
        request.target_state = 1
        request.mode = HeadAction.Request.STREAM
        request.req_id = f"HEIKESONG-LOOKAROUND-{time.monotonic_ns()}"
        request.pre_check = False
        request.action_path = "/app/locomotion/trajectory/head_action/LOOKAROUND.csv"
        request.duration_ms = -1
        request.loop_enabled = False
        request.playback_rate = 1.0
        request.target_angles = []
        future = self.head_action.call_async(request)
        self.lookaround_active = True
        started = time.monotonic()
        deadline = started + 6.0
        while time.monotonic() < deadline:
            rclpy.spin_once(self.node, timeout_sec=0.03)
            self._update_camera()
            self._head_guard()
            if not self.locomotion or self.locomotion[0] != 1:
                raise RuntimeError(f"locomotion left standing state: {self.locomotion}")
            if future.done() and future.exception() is not None:
                raise RuntimeError(f"LOOKAROUND failed: {future.exception()}")
            if future.done() and not future.result().success:
                raise RuntimeError(f"LOOKAROUND rejected: {future.result()}")
            if future.done() and time.monotonic() - started >= 4.5:
                break
        else:
            raise RuntimeError("LOOKAROUND timeout")
        self.lookaround_active = False
        self._stop()

        self._stop()
        if self.mat_seen_count == 0:
            raise RuntimeError("full scan did not see yoga-mat color")
        return {
            "result": "completed",
            "action": "LOOKAROUND",
            "elapsed_s": time.monotonic() - started,
            "frame_count": self.frame_count,
            "mat_seen_count": self.mat_seen_count,
            "complete_detection_count": self.complete_detection_count,
            "maximum_mask_fraction": self.maximum_mask_fraction,
            "maximum_bottom_fraction": self.maximum_bottom_fraction,
            "maximum_head_body_yaw_rad": self.maximum_head_yaw,
            "maximum_head_body_pitch_drift_rad": self.maximum_head_pitch_drift,
        }


def main() -> int:
    args, ros_args = parse_args()
    rclpy.init(args=ros_args)
    scan = MatScanNode(args)
    exit_code = 0
    try:
        result = scan.run()
    except Exception as error:
        exit_code = 2
        result = {
            "result": "aborted",
            "error": str(error),
            "frame_count": scan.frame_count,
            "mat_seen_count": scan.mat_seen_count,
            "complete_detection_count": scan.complete_detection_count,
            "maximum_mask_fraction": scan.maximum_mask_fraction,
            "maximum_bottom_fraction": scan.maximum_bottom_fraction,
        }
    finally:
        scan._stop()
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps(result, separators=(",", ":")), flush=True)
        scan.node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
