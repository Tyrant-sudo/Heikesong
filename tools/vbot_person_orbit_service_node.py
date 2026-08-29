#!/usr/bin/env python3
"""Standard ROS 2 service interface for person-on-mat orbit behavior."""

from __future__ import annotations

import json
import math
from pathlib import Path
import sys
import threading
import time
from typing import Any

import cv2
import numpy as np
import rclpy
from camera_msgs.msg import JpegRequest
from camera_msgs.srv import GetJpegImages
from function_msgs.srv import SetRunMode
from geometry_msgs.msg import Twist
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import PointCloud2
from sensor_msgs_py import point_cloud2
from software_msgs.msg import LocomotionStatus
from software_msgs.srv import LowlevelAction
from std_msgs.msg import String
from std_srvs.srv import Trigger
from tf2_ros import Buffer, TransformListener
from vision_msgs.msg import PoseDetection


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.behavior.person_orbit import (  # noqa: E402
    OrbitDecision,
    PersonDetection,
    PersonOrbitPolicy,
    infer_facing_orbit_direction,
)
from vbot_person_on_mat_probe import evaluate_person, mat_polygon  # noqa: E402


CAMERA_FX_PX = 162.14315136170416
CAMERA_CX_PX = 239.5


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


class PersonOrbitServiceNode(Node):
    def __init__(self) -> None:
        super().__init__("heikesong_person_orbit_service")
        self.declare_parameter("direction", 1)
        self.declare_parameter("orbit_duration_s", 6.8)
        self.declare_parameter("target_distance_m", 0.60)
        self.declare_parameter("hard_stop_distance_m", 0.30)
        self.declare_parameter("maximum_approach_s", 20.0)

        self.callback_group = ReentrantCallbackGroup()
        self.command_publisher = self.create_publisher(Twist, "/vel_cmd", 10)
        status_qos = QoSProfile(
            depth=1,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self.status_publisher = self.create_publisher(
            String, "/heikesong/person_orbit/status", status_qos
        )
        self.camera = self.create_client(
            GetJpegImages, "/get_jpeg_images", callback_group=self.callback_group
        )
        self.lowlevel = self.create_client(
            LowlevelAction, "/sm/action/lowlevel", callback_group=self.callback_group
        )
        self.run_mode = self.create_client(
            SetRunMode, "/locomotion/set_run_mode", callback_group=self.callback_group
        )
        self.tf_buffer = Buffer()
        self.tf_listener = TransformListener(self.tf_buffer, self, spin_thread=False)
        self.create_subscription(
            LocomotionStatus,
            "/locomotion/status",
            self._on_locomotion,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            PointCloud2,
            "/lidar_points",
            self._on_cloud,
            10,
            callback_group=self.callback_group,
        )
        self.create_subscription(
            PoseDetection,
            "/perception/poses",
            self._on_pose,
            20,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/heikesong/person_orbit/start",
            self._on_start,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/heikesong/person_orbit/start_auto",
            self._on_start_auto,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/heikesong/person_orbit/stop",
            self._on_stop,
            callback_group=self.callback_group,
        )
        self.create_service(
            Trigger,
            "/heikesong/person_orbit/get_status",
            self._on_get_status,
            callback_group=self.callback_group,
        )

        self.data_lock = threading.Lock()
        self.run_lock = threading.Lock()
        self.stop_requested = threading.Event()
        self.worker: threading.Thread | None = None
        self.active = False
        self.locomotion: tuple[int, int, str] | None = None
        self.cloud: PointCloud2 | None = None
        self.cloud_at_s = 0.0
        self.pose_stamp: tuple[int, int] | None = None
        self.people: list[PoseDetection] = []
        self.pose_at_s = 0.0
        self.status_json = ""
        self._publish_status("idle", callable=True)

    def _on_locomotion(self, message: LocomotionStatus) -> None:
        with self.data_lock:
            self.locomotion = (
                int(message.posture),
                int(message.motion),
                str(message.current_action),
            )

    def _on_cloud(self, message: PointCloud2) -> None:
        with self.data_lock:
            self.cloud = message
            self.cloud_at_s = time.monotonic()

    def _on_pose(self, message: PoseDetection) -> None:
        if message.class_id != 0:
            return
        stamp = (int(message.header.stamp.sec), int(message.header.stamp.nanosec))
        with self.data_lock:
            if stamp != self.pose_stamp:
                self.people = []
                self.pose_stamp = stamp
            self.people.append(message)
            self.pose_at_s = time.monotonic()

    def _read_orbit_parameters(self) -> tuple[int, float, float, float, float]:
        direction = int(self.get_parameter("direction").value)
        duration = float(self.get_parameter("orbit_duration_s").value)
        target_distance = float(self.get_parameter("target_distance_m").value)
        hard_stop = float(self.get_parameter("hard_stop_distance_m").value)
        maximum_approach = float(self.get_parameter("maximum_approach_s").value)
        if direction not in (-1, 1):
            raise ValueError("direction must be 1 or -1")
        if not 1.0 <= duration <= 60.0:
            raise ValueError("orbit_duration_s must be between 1 and 60")
        if not 0.45 <= target_distance <= 0.90:
            raise ValueError("target_distance_m must be between 0.45 and 0.90")
        if not 0.25 <= hard_stop < target_distance:
            raise ValueError("hard_stop_distance_m is invalid")
        if not 1.0 <= maximum_approach <= 60.0:
            raise ValueError("maximum_approach_s must be between 1 and 60")
        return direction, duration, target_distance, hard_stop, maximum_approach

    def _on_start(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        try:
            parameters = self._read_orbit_parameters()
        except ValueError as error:
            response.success = False
            response.message = str(error)
            return response
        return self._start_behavior(parameters, response)

    def _on_start_auto(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        try:
            _, duration, target_distance, hard_stop, maximum_approach = (
                self._read_orbit_parameters()
            )
        except ValueError as error:
            response.success = False
            response.message = str(error)
            return response
        return self._start_behavior(
            (0, duration, target_distance, hard_stop, maximum_approach),
            response,
        )

    def _start_behavior(
        self,
        parameters: tuple[int, float, float, float, float],
        response: Trigger.Response,
    ) -> Trigger.Response:
        with self.run_lock:
            if self.active:
                response.success = False
                response.message = "person orbit is already active"
                return response
            self.active = True
            self.stop_requested.clear()
            self.worker = threading.Thread(
                target=self._run_behavior,
                args=(parameters,),
                name="heikesong-person-orbit",
                daemon=True,
            )
            self.worker.start()
        response.success = True
        response.message = "person orbit accepted"
        return response

    def _on_stop(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        with self.run_lock:
            active = self.active
        self.stop_requested.set()
        self._publish_zero()
        response.success = True
        response.message = "stop requested" if active else "already idle"
        return response

    def _on_get_status(
        self, _request: Trigger.Request, response: Trigger.Response
    ) -> Trigger.Response:
        response.success = True
        response.message = self.status_json
        return response

    def _snapshot_people(self) -> list[PoseDetection]:
        with self.data_lock:
            return list(self.people)

    @staticmethod
    def _to_policy_detections(
        messages: list[PoseDetection],
    ) -> list[PersonDetection]:
        return [
            PersonDetection(
                area_px2=max(
                    0.0,
                    float(message.bbox_max.x - message.bbox_min.x)
                    * float(message.bbox_max.y - message.bbox_min.y),
                ),
                center_x_px=float(message.bbox_min.x + message.bbox_max.x) * 0.5,
                confidence=float(message.score),
            )
            for message in messages
        ]

    def _fresh_people(self) -> list[PersonDetection]:
        with self.data_lock:
            pose_age = time.monotonic() - self.pose_at_s
            messages = list(self.people)
        return [] if pose_age > 0.8 else self._to_policy_detections(messages)

    def _wait_future(self, future: Any, timeout_s: float) -> Any:
        deadline = time.monotonic() + timeout_s
        while not future.done() and time.monotonic() < deadline:
            if self.stop_requested.is_set():
                raise RuntimeError("stop requested")
            time.sleep(0.02)
        if not future.done():
            raise RuntimeError("service timeout")
        if future.exception() is not None:
            raise RuntimeError(str(future.exception()))
        return future.result()

    def _capture_image(self) -> np.ndarray:
        if not self.camera.wait_for_service(timeout_sec=4.0):
            raise RuntimeError("camera service unavailable")
        request = GetJpegImages.Request()
        frame = JpegRequest()
        frame.channel_id = 0
        frame.width = 480
        frame.height = 270
        frame.quality = 95
        frame.undistort = True
        request.request.append(frame)
        response = self._wait_future(self.camera.call_async(request), 5.0)
        if not response.response:
            raise RuntimeError("camera returned no frame")
        image = cv2.imdecode(
            np.frombuffer(bytes(response.response[0].data), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if image is None:
            raise RuntimeError("camera JPEG decode failed")
        return image

    def _select_person_on_mat(self) -> tuple[PersonDetection, PoseDetection]:
        image = self._capture_image()
        time.sleep(0.25)
        polygon, _, _, _ = mat_polygon(image)
        messages = self._snapshot_people()
        associations = [
            evaluate_person(message, polygon, image.shape[:2])
            for message in messages
        ]
        valid = [
            (item, message)
            for item, message in zip(associations, messages)
            if item["association_score"] >= 2.0 and item["score"] >= 0.55
        ]
        if not valid:
            raise RuntimeError("no person associated with yoga mat")
        target, message = max(
            valid,
            key=lambda pair: (
                pair[0]["association_score"],
                pair[0]["score"],
            ),
        )
        bbox = target["bbox"]
        return (
            PersonDetection(
                area_px2=max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])),
                center_x_px=float(target["center_x"]),
                confidence=float(target["score"]),
            ),
            message,
        )

    @staticmethod
    def _continuous_target(
        previous: PersonDetection,
        detections: list[PersonDetection],
    ) -> PersonDetection | None:
        candidates = [
            item
            for item in detections
            if item.confidence >= 0.55
            and item.area_px2 >= 500.0
            and 5.0 <= item.center_x_px <= 475.0
        ]
        return (
            None
            if not candidates
            else min(candidates, key=lambda item: abs(item.center_x_px - previous.center_x_px))
        )

    def _switch_to_trot(self) -> None:
        if not self.lowlevel.wait_for_service(timeout_sec=3.0):
            raise RuntimeError("lowlevel service unavailable")
        request = LowlevelAction.Request()
        request.target_state = 1
        request.mode = LowlevelAction.Request.RL_TROT
        request.req_id = f"HEIKESONG-PERSON-ORBIT-{time.monotonic_ns()}"
        request.pre_check = False
        request.action_path = ""
        request.action_params_json = "{}"
        response = self._wait_future(self.lowlevel.call_async(request), 8.0)
        if not response.success:
            raise RuntimeError(f"RL_TROT rejected: {response.message}")
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with self.data_lock:
                state = self.locomotion
            if state and state[0] == 1 and state[1] == 0 and state[2] == "RL_TROT":
                return
            self._publish_zero(1)
            time.sleep(0.04)
        raise RuntimeError(f"RL_TROT did not stabilize: {state}")

    def _restore_idle(self) -> None:
        self._publish_zero()
        if not self.run_mode.wait_for_service(timeout_sec=2.0):
            return
        request = SetRunMode.Request()
        request.target_state = 1
        request.mode = SetRunMode.Request.MODE_IDLE
        request.req_id = f"HEIKESONG-PERSON-ORBIT-IDLE-{time.monotonic_ns()}"
        request.pre_check = False
        request.has_is_traction_user_param = False
        request.is_traction_user_param = False
        future = self.run_mode.call_async(request)
        deadline = time.monotonic() + 4.0
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.02)
        self._publish_zero()

    def _publish_zero(self, count: int = 12) -> None:
        for _ in range(count):
            self.command_publisher.publish(Twist())
            time.sleep(0.02)

    def _lidar_metrics(
        self, target_center_x_px: float, direction: int
    ) -> tuple[float | None, float | None]:
        with self.data_lock:
            cloud = self.cloud
            cloud_at_s = self.cloud_at_s
        if cloud is None or time.monotonic() - cloud_at_s > 0.8:
            raise RuntimeError("lidar stale")
        transform = self.tf_buffer.lookup_transform(
            "base_link", cloud.header.frame_id, Time()
        )
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        quaternion = (rotation.x, rotation.y, rotation.z, rotation.w)
        target_bearing = math.atan2(
            CAMERA_CX_PX - target_center_x_px, CAMERA_FX_PX
        )
        target_distance = None
        side_distance = None
        for row in point_cloud2.read_points(
            cloud, field_names=("x", "y", "z"), skip_nans=True
        ):
            rotated = _rotate_vector(
                quaternion, (float(row[0]), float(row[1]), float(row[2]))
            )
            x = rotated[0] + translation.x
            y = rotated[1] + translation.y
            z = rotated[2] + translation.z
            distance = math.hypot(x, y)
            if distance < 0.25 or distance > 3.0 or not (-0.10 < z < 1.80):
                continue
            bearing = math.atan2(y, x)
            angular_error = math.atan2(
                math.sin(bearing - target_bearing),
                math.cos(bearing - target_bearing),
            )
            if x > 0.0 and abs(angular_error) <= math.radians(12.0):
                target_distance = distance if target_distance is None else min(target_distance, distance)
            on_motion_side = (
                0.12 < y < 0.55 if direction == 1 else -0.55 < y < -0.12
            )
            if on_motion_side and -0.25 < x < 0.65 and -0.10 < z < 0.80:
                side_distance = distance if side_distance is None else min(side_distance, distance)
        return target_distance, side_distance

    def _run_behavior(
        self, parameters: tuple[int, float, float, float, float]
    ) -> None:
        direction, duration, target_distance, hard_stop, maximum_approach = parameters
        started_at_s = time.monotonic()
        phase = "validating_target"
        target: PersonDetection | None = None
        measured_distance: float | None = None
        outcome = "aborted"
        reason = "unknown"
        try:
            self._publish_status(phase)
            target, target_pose = self._select_person_on_mat()
            if direction == 0:
                keypoints = tuple(
                    (float(point.x), float(point.y), float(point.confidence))
                    for point in target_pose.keypoints
                )
                direction = infer_facing_orbit_direction(
                    keypoints,
                    float(target_pose.bbox_max.x - target_pose.bbox_min.x),
                )
                if direction is None:
                    raise RuntimeError("person facing direction is ambiguous")
                self._publish_status(
                    "direction_selected",
                    direction=direction,
                    direction_name="left" if direction == 1 else "right",
                )
            self._switch_to_trot()
            phase = "approaching"
            approach_deadline = time.monotonic() + maximum_approach
            target_seen_at = time.monotonic()
            while time.monotonic() < approach_deadline:
                if self.stop_requested.is_set():
                    raise RuntimeError("stop requested")
                updated = self._continuous_target(target, self._fresh_people())
                if updated is not None:
                    target = updated
                    target_seen_at = time.monotonic()
                elif time.monotonic() - target_seen_at > 0.55:
                    raise RuntimeError("target person lost")
                else:
                    self.command_publisher.publish(Twist())
                    time.sleep(0.04)
                    continue
                measured_distance, side_distance = self._lidar_metrics(
                    target.center_x_px, direction
                )
                if measured_distance is None:
                    raise RuntimeError("no lidar return for mat person")
                if measured_distance < hard_stop:
                    raise RuntimeError("person inside hard stop distance")
                if side_distance is not None and side_distance < hard_stop:
                    raise RuntimeError("motion-side obstacle inside hard stop distance")
                self._publish_status(
                    phase,
                    elapsed_s=time.monotonic() - started_at_s,
                    target_confidence=target.confidence,
                    target_distance_m=measured_distance,
                    target_center_x_px=target.center_x_px,
                )
                if measured_distance <= target_distance + 0.10:
                    break
                command = Twist()
                command.linear.x = 0.30
                command.angular.z = max(
                    -0.70, min(0.70, -0.003 * (target.center_x_px - 240.0))
                )
                self.command_publisher.publish(command)
                time.sleep(0.04)
            else:
                raise RuntimeError("approach timeout")

            self._publish_zero()
            policy = PersonOrbitPolicy()
            policy.start(
                self._fresh_people(),
                now_s=time.monotonic(),
                direction=direction,
                duration_s=duration,
            )
            phase = "orbiting"
            orbit_started_at_s = time.monotonic()
            while rclpy.ok():
                if self.stop_requested.is_set():
                    raise RuntimeError("stop requested")
                output = policy.update(self._fresh_people(), now_s=time.monotonic())
                if output.decision == OrbitDecision.COMPLETE:
                    outcome = "completed"
                    reason = "completed"
                    break
                if output.decision == OrbitDecision.STOP or output.target is None:
                    raise RuntimeError(output.reason or "target person lost")
                target = output.target
                measured_distance, side_distance = self._lidar_metrics(
                    target.center_x_px, direction
                )
                if measured_distance is None:
                    raise RuntimeError("no lidar return for mat person")
                if measured_distance < hard_stop:
                    raise RuntimeError("person inside hard stop distance")
                if side_distance is not None and side_distance < hard_stop:
                    raise RuntimeError("motion-side obstacle inside hard stop distance")
                self._publish_status(
                    phase,
                    elapsed_s=time.monotonic() - orbit_started_at_s,
                    target_confidence=target.confidence,
                    target_distance_m=measured_distance,
                    target_center_x_px=target.center_x_px,
                )
                command = Twist()
                if output.decision == OrbitDecision.MOVE:
                    command.linear.y = output.linear_y_mps
                    command.angular.z = output.angular_z_rps
                    distance_error = measured_distance - target_distance
                    if distance_error > 0.12:
                        command.linear.x = 0.30
                    elif distance_error < -0.12:
                        command.linear.x = -0.30
                self.command_publisher.publish(command)
                time.sleep(0.04)
        except Exception as error:
            reason = str(error)
            outcome = "stopped" if reason == "stop requested" else "aborted"
        finally:
            self._publish_zero()
            self._restore_idle()
            with self.run_lock:
                self.active = False
            self.stop_requested.clear()
            self._publish_status(
                outcome,
                reason=reason,
                direction=direction,
                elapsed_s=time.monotonic() - started_at_s,
                target_confidence=target.confidence if target else 0.0,
                target_distance_m=measured_distance if measured_distance is not None else -1.0,
            )

    def _publish_status(self, state: str, **details: object) -> None:
        payload = {"state": state, **details}
        self.status_json = json.dumps(payload, separators=(",", ":"))
        message = String()
        message.data = self.status_json
        self.status_publisher.publish(message)

    def close(self) -> None:
        self.stop_requested.set()
        self._publish_zero()
        worker = self.worker
        if worker and worker.is_alive():
            worker.join(timeout=5.0)


def main() -> int:
    rclpy.init()
    node = PersonOrbitServiceNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
