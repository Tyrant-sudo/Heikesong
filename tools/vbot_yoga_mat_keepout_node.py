#!/usr/bin/env python3
"""Detect, project, and publish a stable yoga-mat keepout zone without motion."""

from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import rclpy
from camera_msgs.msg import JpegRequest
from camera_msgs.srv import GetJpegImages
from geometry_msgs.msg import Point32, PolygonStamped
from nav_msgs.msg import OccupancyGrid
from rclpy.duration import Duration
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from std_msgs.msg import String
from tf2_ros import Buffer, TransformException, TransformListener


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.perception.ground_projection import (  # noqa: E402
    CameraIntrinsics,
    MatProjectionError,
    project_mat_boundary_to_world,
    quaternion_xyzw_to_matrix,
    select_stable_boundary_cluster,
)
from heikesong.perception.yoga_mat_color import ColorYogaMatDetector  # noqa: E402
from heikesong.safety.keepout import KeepoutZone  # noqa: E402


CALIBRATED_INTRINSICS = CameraIntrinsics(
    fx=162.14315136170416,
    fy=162.14315136170416,
    cx=239.5,
    cy=134.5,
)


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report")
    parser.add_argument("--exit-after-stable", action="store_true")
    parser.add_argument("--max-seconds", type=float, default=30.0)
    parser.add_argument("--stable-frames", type=int, default=10)
    parser.add_argument("--stability-px", type=float, default=4.0)
    parser.add_argument("--capture-interval-s", type=float, default=0.5)
    parser.add_argument("--keepout-expansion-m", type=float, default=0.40)
    parser.add_argument("--grid-resolution-m", type=float, default=0.05)
    return parser.parse_known_args()


class YogaMatKeepoutNode(Node):
    def __init__(self, args: argparse.Namespace) -> None:
        super().__init__("heikesong_yoga_mat_keepout")
        self.args = args
        self.detector = ColorYogaMatDetector()
        self.camera = self.create_client(GetJpegImages, "/get_jpeg_images")
        self.tf_buffer = Buffer(cache_time=Duration(seconds=10.0))
        self.tf_listener = TransformListener(self.tf_buffer, self)
        latched_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.mat_publisher = self.create_publisher(
            PolygonStamped, "/heikesong/yoga_mat/polygon_map", latched_qos
        )
        self.keepout_publisher = self.create_publisher(
            PolygonStamped, "/heikesong/yoga_mat/keepout_map", latched_qos
        )
        self.grid_publisher = self.create_publisher(
            OccupancyGrid, "/heikesong/yoga_mat/keepout_grid", latched_qos
        )
        self.status_publisher = self.create_publisher(
            String, "/heikesong/yoga_mat/status", latched_qos
        )
        self.samples: deque[np.ndarray] = deque(maxlen=max(30, args.stable_frames * 3))
        self.pending = False
        self.completed = False
        self.success = False
        self.started = time.monotonic()
        self.last_projection = None
        self.timer = self.create_timer(args.capture_interval_s, self._capture)

    def _capture(self) -> None:
        if self.pending or self.completed:
            return
        if not self.camera.service_is_ready():
            self._publish_status("waiting_for_camera")
            return
        request = GetJpegImages.Request()
        frame_request = JpegRequest()
        frame_request.channel_id = 0
        frame_request.width = 480
        frame_request.height = 270
        frame_request.quality = 95
        frame_request.undistort = True
        request.request.append(frame_request)
        self.pending = True
        try:
            future = self.camera.call_async(request)
            future.add_done_callback(self._handle_frame)
        except Exception as error:
            self.pending = False
            if rclpy.ok():
                self._publish_status("camera_request_failed", error=str(error))

    def _handle_frame(self, future: object) -> None:
        self.pending = False
        try:
            response = future.result()
            if not response.response:
                raise RuntimeError("camera returned no frame")
            frame = response.response[0]
            image = cv2.imdecode(np.frombuffer(bytes(frame.data), dtype=np.uint8), cv2.IMREAD_COLOR)
            if image is None:
                raise RuntimeError("JPEG decode failed")
            analysis = self.detector.analyze(image)
            if not analysis.observation.detected:
                self.samples.clear()
                self._publish_status("mat_not_complete", rejection=analysis.rejection_counts)
                return

            height, width = image.shape[:2]
            scale_x, scale_y = width / 480.0, height / 270.0
            intrinsics = CameraIntrinsics(
                CALIBRATED_INTRINSICS.fx * scale_x,
                CALIBRATED_INTRINSICS.fy * scale_y,
                CALIBRATED_INTRINSICS.cx * scale_x,
                CALIBRATED_INTRINSICS.cy * scale_y,
            )
            boundary_px = np.asarray(
                [[point.x, point.y] for point in analysis.observation.boundary],
                dtype=np.float64,
            )
            self._record_candidate(boundary_px, intrinsics)
        except (MatProjectionError, TransformException, RuntimeError, AttributeError) as error:
            self.samples.clear()
            self._publish_status("projection_rejected", error=str(error))

    def _record_candidate(
        self,
        candidate: np.ndarray,
        intrinsics: CameraIntrinsics,
    ) -> None:
        self.samples.append(candidate)
        cluster = select_stable_boundary_cluster(
            list(self.samples),
            required_inliers=self.args.stable_frames,
            maximum_deviation=self.args.stability_px,
        )
        if cluster is None:
            self._publish_status("stabilizing", sampled_frames=len(self.samples))
            return
        transform = self.tf_buffer.lookup_transform("map", "stereo_left", Time())
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        rotation_wc = quaternion_xyzw_to_matrix(
            (rotation.x, rotation.y, rotation.z, rotation.w)
        )
        translation_wc = np.asarray(
            [translation.x, translation.y, translation.z], dtype=np.float64
        )
        projection = project_mat_boundary_to_world(
            cluster.averaged_boundary,
            intrinsics,
            rotation_wc,
            translation_wc,
        )
        self.last_projection = projection
        averaged = np.asarray(projection.boundary_world, dtype=np.float64)
        raw_zone = KeepoutZone(tuple((float(x), float(y)) for x, y in averaged[:, :2]))
        keepout_zone = raw_zone.expanded(self.args.keepout_expansion_m)
        self._publish_zones(averaged, keepout_zone)
        self.success = True
        self._publish_status(
            "keepout_ready",
            stable_frames=self.args.stable_frames,
            sampled_frames=len(self.samples),
            inlier_count=cluster.inlier_count,
            maximum_pixel_deviation=cluster.maximum_deviation,
            raw_boundary_map=[list(point) for point in raw_zone.boundary],
            keepout_boundary_map=[list(point) for point in keepout_zone.boundary],
            keepout_expansion_m=self.args.keepout_expansion_m,
            reprojection_rms_px=self.last_projection.reprojection_rms_px,
            gravity_alignment=self.last_projection.gravity_alignment,
            camera_distance_m=self.last_projection.camera_distance_m,
        )
        if self.args.exit_after_stable:
            self.completed = True

    def _publish_zones(self, averaged: np.ndarray, keepout: KeepoutZone) -> None:
        stamp = self.get_clock().now().to_msg()
        raw_message = PolygonStamped()
        raw_message.header.frame_id = "map"
        raw_message.header.stamp = stamp
        raw_message.polygon.points = [
            Point32(x=float(x), y=float(y), z=float(z)) for x, y, z in averaged
        ]
        self.mat_publisher.publish(raw_message)

        keepout_message = PolygonStamped()
        keepout_message.header.frame_id = "map"
        keepout_message.header.stamp = stamp
        mean_z = float(np.mean(averaged[:, 2]))
        keepout_message.polygon.points = [
            Point32(x=float(x), y=float(y), z=mean_z) for x, y in keepout.boundary
        ]
        self.keepout_publisher.publish(keepout_message)

        grid_data = keepout.occupancy_grid(resolution=self.args.grid_resolution_m)
        grid = OccupancyGrid()
        grid.header.frame_id = "map"
        grid.header.stamp = stamp
        grid.info.map_load_time = stamp
        grid.info.resolution = float(grid_data.resolution)
        grid.info.width = grid_data.width
        grid.info.height = grid_data.height
        grid.info.origin.position.x = grid_data.origin_x
        grid.info.origin.position.y = grid_data.origin_y
        grid.info.origin.orientation.w = 1.0
        grid.data = list(grid_data.data)
        self.grid_publisher.publish(grid)

    def _publish_status(self, state: str, **details: object) -> None:
        payload = {"state": state, "motion_enabled": False, **details}
        message = String()
        message.data = json.dumps(payload, separators=(",", ":"))
        self.status_publisher.publish(message)
        if state in {"keepout_ready", "timeout"} and self.args.report:
            report_path = Path(self.args.report)
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    args, ros_args = parse_args()
    rclpy.init(args=ros_args)
    node = YogaMatKeepoutNode(args)
    try:
        try:
            while rclpy.ok() and not node.completed:
                if time.monotonic() - node.started > args.max_seconds:
                    node._publish_status(
                        "timeout",
                        sampled_frames=len(node.samples),
                        sampled_boundaries=[sample.tolist() for sample in node.samples],
                    )
                    break
                rclpy.spin_once(node, timeout_sec=0.2)
        except ExternalShutdownException:
            pass
    finally:
        success = node.success
        node.destroy_node()
        try:
            if rclpy.ok():
                rclpy.shutdown()
        except Exception:
            pass
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
