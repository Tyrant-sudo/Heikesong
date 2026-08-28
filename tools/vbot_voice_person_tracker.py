#!/usr/bin/env python3
"""Offline voice commands and person tracking for Vbot EDU."""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import time
import uuid
import wave
from array import array
from pathlib import Path
from typing import Any


try:
    from heikesong.actions.photo_store import (
        PhotoArtifactStore,
        normalize_jpeg_payload,
    )
    from heikesong.behavior.person_head_tracker import (
        HeadTrackingDecision,
        PersonHeadTracker,
    )
    from heikesong.behavior.voice_command_router import (
        VoiceCommandRouter,
        v1_command_specs,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from heikesong.actions.photo_store import (
        PhotoArtifactStore,
        normalize_jpeg_payload,
    )
    from heikesong.behavior.person_head_tracker import (
        HeadTrackingDecision,
        PersonHeadTracker,
    )
    from heikesong.behavior.voice_command_router import (
        VoiceCommandRouter,
        v1_command_specs,
    )

import rclpy
from camera_msgs.msg import JpegRequest
from camera_msgs.srv import GetJpegImages
from function_msgs.srv import FunctionInput, GetContext
from lowlevel_msg.srv import HeadAction
from peripheral_msgs.msg import ShowImg
from peripheral_msgs.srv import DisplayImgs, PlayEmotion
from speech_msgs.msg import SpeechDogToPhone, SpeechPhoneToDog, WakeupInfo
from speech_msgs.srv import SpeechControl
from software_msgs.srv import LowlevelAction
from std_srvs.srv import SetBool
from vision_msgs.msg import PoseDetection


class VoicePersonTrackerNode:
    START_KEYWORDS = {"看着我", "盯着我"}
    STOP_KEYWORDS = {"别看了", "停止跟踪"}

    def __init__(
        self,
        session_seconds: float,
        keyword_model_dir: Path | None = None,
        wake_trigger: bool = False,
        yoga_audio_path: Path = Path(
            "/userdata/vbot/.local/share/heikesong/audio/yoga_start_builtin_ai.wav"
        ),
        yoga_wake_audio_path: Path = Path(
            "/userdata/vbot/.local/share/heikesong/audio/jiajia_wake_ack_builtin.wav"
        ),
        yoga_action_path: Path = Path("/app/config/dags/idle/HAPPINESS.json"),
        downward_dog_action_path: Path = Path(
            "/userdata/vbot/.local/share/heikesong/actions/DOWNWARD_DOG_ONCE.json"
        ),
        push_up_action_path: Path = Path("/app/config/dags/actions/PUSHUP.json"),
        lay_down_action_path: Path = Path(
            "/app/config/dags/idle/SIT_WITHHEAD.json"
        ),
        photo_output_path: Path = Path(
            "/userdata/vbot/.local/share/heikesong/photos"
        ),
        command_arm_seconds: float = 10.0,
    ) -> None:
        self.node = rclpy.create_node("heikesong_voice_person_tracker")
        self.session_seconds = session_seconds
        self.policy = PersonHeadTracker()
        self.active_until_s: float | None = None
        self.pending_wakeup = False
        self.pending_stop = False
        self.pending_stop_reason = "stop trigger"
        self.next_update_s = 0.0
        self.last_adjustment_log_s = 0.0
        self.head_active = False
        self.initial_pose_pending = True
        self.completed_once = False
        self.adjustments = 0
        self.lost_stops = 0
        self.last_keyword_at_s: dict[str, float] = {}
        self.pending_yoga_wake_ack = False
        self.pending_command: tuple[str, str] | None = None
        self.yoga_audio_path = yoga_audio_path
        self.yoga_wake_audio_path = yoga_wake_audio_path
        self.yoga_action_path = yoga_action_path
        self.downward_dog_action_path = downward_dog_action_path
        self.push_up_action_path = push_up_action_path
        self.lay_down_action_path = lay_down_action_path
        self.photo_store = PhotoArtifactStore(photo_output_path)
        self.command_router = VoiceCommandRouter(
            v1_command_specs(), arm_seconds=command_arm_seconds
        )
        self.keyword_spotter: Any | None = None
        self.keyword_stream: Any | None = None
        self.head_client = self.node.create_client(HeadAction, "/head_action")
        self.context_client = self.node.create_client(
            GetContext, "/function/context/get_context"
        )
        self.speech_client = self.node.create_client(
            SpeechControl, "/speech_control"
        )
        self.emotion_client = self.node.create_client(
            PlayEmotion, "/display_node/play_emotion"
        )
        self.display_client = self.node.create_client(
            DisplayImgs, "/display_node/display_imgs"
        )
        self.function_client = self.node.create_client(
            FunctionInput, "/function_input"
        )
        self.lowlevel_action_client = self.node.create_client(
            LowlevelAction, "/sm/action/lowlevel"
        )
        self.camera_client = self.node.create_client(
            GetJpegImages, "/get_jpeg_images"
        )
        self.node.create_service(
            SetBool,
            "/heikesong/person_head_tracking/set_enabled",
            self._on_set_enabled,
        )
        self.audio_publisher = self.node.create_publisher(
            SpeechPhoneToDog, "/speech_phone_to_dog", 10
        )
        self.command_handlers = {
            "yoga_start": self._run_yoga_feedback,
            "downward_dog": self._run_downward_dog,
            "push_up": self._run_push_up,
            "lay_down_and_watch": self._run_lay_down_and_watch,
            "take_photo": self._run_take_photo,
        }
        if wake_trigger:
            self.node.create_subscription(
                WakeupInfo, "/speech/wakeup_info", self._on_wakeup, 10
            )
        self.node.create_subscription(
            PoseDetection, "/perception/poses", self._on_pose, 10
        )
        if keyword_model_dir is not None:
            self._configure_keyword_spotter(keyword_model_dir)
            self.node.create_subscription(
                SpeechDogToPhone,
                "/speech_dog_to_phone",
                self._on_audio,
                20,
            )

    def _on_set_enabled(
        self,
        request: SetBool.Request,
        response: SetBool.Response,
    ) -> SetBool.Response:
        if request.data:
            if self.active_until_s is not None or self.pending_wakeup:
                response.success = True
                response.message = "person head tracking already enabled or queued"
                return response
            self.pending_wakeup = True
            response.success = True
            response.message = "person head tracking enable queued"
            return response

        self.pending_wakeup = False
        if self.active_until_s is not None:
            self.pending_stop = True
            self.pending_stop_reason = "ROS service request"
            response.message = "person head tracking disable queued"
        else:
            response.message = "person head tracking already disabled"
        response.success = True
        return response

    def _configure_keyword_spotter(self, model_dir: Path) -> None:
        import sherpa_onnx

        model_dir = model_dir.resolve()
        self.keyword_spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(model_dir / "tokens.txt"),
            encoder=str(
                model_dir / "encoder-epoch-13-avg-2-chunk-16-left-64.int8.onnx"
            ),
            decoder=str(model_dir / "decoder-epoch-13-avg-2-chunk-16-left-64.onnx"),
            joiner=str(
                model_dir / "joiner-epoch-13-avg-2-chunk-16-left-64.int8.onnx"
            ),
            keywords_file=str(model_dir / "person_tracking_keywords.txt"),
            num_threads=2,
            keywords_score=1.2,
            keywords_threshold=0.18,
        )
        self.keyword_stream = self.keyword_spotter.create_stream()
        self.node.get_logger().info(f"offline keywords loaded from {model_dir}")

    def _on_audio(self, message: SpeechDogToPhone) -> None:
        if self.keyword_spotter is None or self.keyword_stream is None:
            return
        if message.num_channels != 1 or message.bit_depth != 16:
            return
        samples = [sample / 32768.0 for sample in message.audio_data]
        self.keyword_stream.accept_waveform(message.sample_rate, samples)
        keyword = ""
        while self.keyword_spotter.is_ready(self.keyword_stream):
            self.keyword_spotter.decode_stream(self.keyword_stream)
            current = self.keyword_spotter.get_result(self.keyword_stream)
            if current:
                keyword = current
        now_s = time.monotonic()
        if not keyword:
            return
        last_seen_s = self.last_keyword_at_s.get(keyword, 0.0)
        if now_s - last_seen_s < 2.0:
            return
        self.last_keyword_at_s[keyword] = now_s
        self.keyword_spotter.reset_stream(self.keyword_stream)
        self.node.get_logger().info(f"offline keyword detected: {keyword}")
        if keyword in self.START_KEYWORDS and self.active_until_s is None:
            self.pending_wakeup = True
        elif keyword in self.STOP_KEYWORDS and self.active_until_s is not None:
            self.pending_stop = True
            self.pending_stop_reason = f"offline keyword: {keyword}"
        else:
            decision = self.command_router.handle(keyword, now_s)
            if decision.action == "wake_ack":
                self.pending_yoga_wake_ack = True
                self.node.get_logger().info("voice command window armed")
            elif (
                decision.action == "execute_after_wake"
                and decision.command is not None
            ):
                self.pending_yoga_wake_ack = True
                correlation_id = (
                    f"VOICE-{decision.command.upper()}-{uuid.uuid4().hex[:10]}"
                )
                self.pending_command = (decision.command, correlation_id)
                self.node.get_logger().info(
                    f"pre-wake command paired: command={decision.command} "
                    f"correlation_id={correlation_id}"
                )
            elif decision.action == "execute" and decision.command is not None:
                correlation_id = (
                    f"VOICE-{decision.command.upper()}-{uuid.uuid4().hex[:10]}"
                )
                self.pending_command = (decision.command, correlation_id)
                self.node.get_logger().info(
                    f"voice command accepted: command={decision.command} "
                    f"correlation_id={correlation_id}"
                )
            else:
                self.node.get_logger().warning(
                    f"voice command ignored: keyword={keyword!r} "
                    f"reason={decision.reason}"
                )

    def _on_wakeup(self, message: WakeupInfo) -> None:
        if message.wakeup_source != message.WAKEUP_SOURCE_DOG:
            return
        if self.active_until_s is not None:
            self.pending_stop = True
            self.pending_stop_reason = "second wakeup"
            return
        self.pending_wakeup = True

    def _start_pending_session(self, now_s: float) -> None:
        self.pending_wakeup = False
        if not self._motion_context_is_safe():
            self.node.get_logger().error("voice trigger rejected by safety context")
            return
        self.policy.reset()
        self.adjustments = 0
        self.lost_stops = 0
        self.last_adjustment_log_s = 0.0
        self.initial_pose_pending = True
        self.active_until_s = now_s + self.session_seconds
        self.next_update_s = now_s + 0.6
        self.node.get_logger().info(
            f"tracking enabled for {self.session_seconds:.1f}s"
        )

    def _on_pose(self, message: PoseDetection) -> None:
        if self.active_until_s is None or message.class_id != 0:
            return
        face_points = [
            point for point in message.keypoints[:5] if point.confidence >= 0.45
        ]
        if face_points:
            confidence_sum = sum(point.confidence for point in face_points)
            center_x = sum(
                point.x * point.confidence for point in face_points
            ) / confidence_sum
            center_y = sum(
                point.y * point.confidence for point in face_points
            ) / confidence_sum
        else:
            center_x = (message.bbox_min.x + message.bbox_max.x) / 2.0
            center_y = message.bbox_min.y + (
                message.bbox_max.y - message.bbox_min.y
            ) * 0.15
        self.policy.observe(
            center_x,
            message.score,
            time.monotonic(),
            center_y_px=center_y,
        )

    def tick(self) -> None:
        now_s = time.monotonic()
        if self.command_router.expire(now_s):
            self.node.get_logger().info("voice command arm window expired")
        if self.pending_yoga_wake_ack:
            self.pending_yoga_wake_ack = False
            try:
                self._play_emotion(mode=0, duration_ms=500)
                self._play_audio(self.yoga_wake_audio_path)
                self.node.get_logger().info(
                    "voice wake acknowledged with blink and sound"
                )
            except Exception as error:
                self.node.get_logger().error(
                    f"voice wake acknowledgement failed: {error}"
                )
            return
        if self.pending_command is not None:
            command, correlation_id = self.pending_command
            self.pending_command = None
            self.pending_yoga_wake_ack = False
            handler = self.command_handlers.get(command)
            if handler is None:
                self.node.get_logger().error(
                    f"no handler registered for command={command}"
                )
                return
            try:
                handler(correlation_id)
            except Exception as error:
                self.node.get_logger().error(
                    f"voice command failed: command={command} "
                    f"correlation_id={correlation_id} error={error}"
                )
            return
        if self.pending_stop:
            self.pending_stop = False
            reason = self.pending_stop_reason
            self.pending_stop_reason = "stop trigger"
            self.stop(reason)
            return
        if self.pending_wakeup:
            self._start_pending_session(now_s)
        if self.active_until_s is None:
            return
        if now_s >= self.active_until_s:
            self.stop("session timeout")
            return
        if now_s < self.next_update_s:
            return
        self.next_update_s = now_s + 1.0
        output = self.policy.update(now_s)
        if output.decision == HeadTrackingDecision.STOP:
            if self.head_active:
                self.lost_stops += 1
                self.node.get_logger().warning("person lost; head motion stopped")
                self._cancel_head()
        elif output.decision == HeadTrackingDecision.ADJUST:
            duration_ms = 3000
            if self._set_head_pose(
                output.target_pitch_rad,
                output.target_yaw_rad,
                duration_ms=duration_ms,
            ):
                self.initial_pose_pending = False
                self.next_update_s = now_s + duration_ms / 1000.0 + 0.15
                self.adjustments += 1
                self.node.get_logger().info(
                    f"head tracking move pitch={output.target_pitch_rad:.3f} "
                    f"yaw={output.target_yaw_rad:.3f} "
                    f"error_x_px={output.error_px:.1f} "
                    f"error_y_px={output.vertical_error_px:.1f} "
                    f"duration_ms={duration_ms}"
                )

    def _run_yoga_feedback(self, correlation_id: str) -> None:
        if not self._motion_context_is_safe():
            self.node.get_logger().error(
                "yoga feedback rejected by safety context"
            )
            return
        try:
            self._notify_action(True)
            self._play_yoga_audio()
            self._play_emotion(mode=0, duration_ms=700)
            time.sleep(0.75)
            self._short_flash()
            self._perform_happy_body(correlation_id)
            self.node.get_logger().info(
                f"yoga start feedback completed: correlation_id={correlation_id}"
            )
        except Exception as error:
            self.node.get_logger().error(f"yoga start feedback failed: {error}")
        finally:
            try:
                self._notify_action(False)
            except Exception as error:
                self.node.get_logger().error(
                    f"failed to leave action voice mode: {error}"
                )

    def _run_downward_dog(self, correlation_id: str) -> None:
        self._run_motion_dag(
            "downward_dog",
            self.downward_dog_action_path,
            correlation_id,
            return_to_fixed_stand=True,
        )

    def _run_push_up(self, correlation_id: str) -> None:
        self._run_motion_dag("push_up", self.push_up_action_path, correlation_id)

    def _run_lay_down_and_watch(self, correlation_id: str) -> None:
        self._run_motion_dag(
            "lay_down_and_watch", self.lay_down_action_path, correlation_id
        )

    def _run_motion_dag(
        self,
        name: str,
        path: Path,
        correlation_id: str,
        return_to_fixed_stand: bool = False,
    ) -> None:
        if not self._motion_context_is_safe():
            raise RuntimeError(f"{name} rejected by safety context")
        if not path.is_file():
            raise FileNotFoundError(path)
        self._notify_action(True)
        try:
            request = FunctionInput.Request()
            request.source = "heikesong"
            request.dag = path.read_text(encoding="utf-8")
            request.request_id = correlation_id
            self._call_service(self.function_client, request, timeout=60.0)
            outcome = self._wait_for_motion_completion(
                correlation_id, timeout_seconds=65.0
            )
            if outcome != "SUCCESS":
                raise RuntimeError(f"{name} finished with outcome={outcome}")
            if return_to_fixed_stand:
                self._return_to_fixed_stand(correlation_id)
            self.node.get_logger().info(
                f"motion command completed: command={name} "
                f"correlation_id={correlation_id}"
            )
        finally:
            self._notify_action(False)

    def _return_to_fixed_stand(self, correlation_id: str) -> None:
        snapshot = self._get_context_snapshot()
        if (
            snapshot is not None
            and snapshot.system_status.robot_is_static
            and snapshot.function_status.body_action_status.mode_str
            == "FIXED_STAND"
        ):
            return

        request = LowlevelAction.Request()
        request.target_state = 1
        request.mode = request.FIXED_STAND
        request.req_id = f"{correlation_id}-FIXED-STAND"
        request.pre_check = False
        request.action_path = ""
        request.action_params_json = "{}"
        self._call_service(self.lowlevel_action_client, request, timeout=12.0)

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            snapshot = self._get_context_snapshot()
            if (
                snapshot is not None
                and not snapshot.dag_status.emergency_stop_active
                and snapshot.system_status.robot_is_static
                and snapshot.function_status.body_action_status.mode_str
                == "FIXED_STAND"
            ):
                self.node.get_logger().info(
                    f"fixed stand recovery completed: "
                    f"correlation_id={correlation_id}"
                )
                return
            time.sleep(0.25)
        raise RuntimeError("fixed stand recovery did not stabilize")

    def _run_take_photo(self, correlation_id: str) -> None:
        if not self._motion_context_is_safe():
            raise RuntimeError("photo rejected because the robot is moving")
        request = GetJpegImages.Request()
        jpeg_request = JpegRequest()
        jpeg_request.channel_id = 0
        jpeg_request.width = 960
        jpeg_request.height = 540
        jpeg_request.quality = 90
        jpeg_request.undistort = True
        request.request.append(jpeg_request)
        response = self._call_service(self.camera_client, request, timeout=12.0)
        if not response.response:
            raise RuntimeError("camera returned no frame")
        frame = response.response[0]
        if frame.status != 0:
            raise RuntimeError(f"camera returned status={frame.status}")
        raw_data = bytes(frame.data)
        data = normalize_jpeg_payload(raw_data)

        from PIL import Image

        image = Image.open(io.BytesIO(data))
        image.verify()
        captured_at = (
            frame.header.stamp.sec + frame.header.stamp.nanosec / 1_000_000_000
        )
        if captured_at <= 0:
            captured_at = time.time()
        digest = hashlib.sha256(data).hexdigest()
        artifact = self.photo_store.store(
            correlation_id,
            data,
            captured_at,
            digest,
            {
                "channel": int(jpeg_request.channel_id),
                "width": int(frame.width),
                "height": int(frame.height),
                "undistort": True,
                "status": int(frame.status),
                "raw_payload_bytes": len(raw_data),
                "padding_bytes": len(raw_data) - len(data),
            },
        )
        self._short_flash()
        self.node.get_logger().info(
            f"photo captured: correlation_id={correlation_id} "
            f"path={artifact.path} sha256={artifact.sha256}"
        )

    def _call_service(self, client: object, request: object, timeout: float = 8.0):
        if not client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError(f"service unavailable: {client.srv_name}")
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=timeout)
        if not future.done() or future.exception() is not None:
            raise RuntimeError(f"service timeout: {client.srv_name}")
        response = future.result()
        if hasattr(response, "success"):
            success = response.success
            accepted = success if isinstance(success, bool) else all(success)
            if not accepted:
                raise RuntimeError(
                    f"service rejected: {client.srv_name}: {response}"
                )
        return response

    def _notify_action(self, enabled: bool) -> None:
        request = SpeechControl.Request()
        request.request_type = (
            request.NOTIFY_ACTION_ON if enabled else request.NOTIFY_ACTION_OFF
        )
        request.enable = enabled
        self._call_service(self.speech_client, request)

    def _play_emotion(self, mode: int, duration_ms: int) -> None:
        request = PlayEmotion.Request()
        request.target_state = 1
        request.req_id = f"YOGA-FACE-{uuid.uuid4().hex[:8]}"
        request.pre_check = False
        request.mode = mode
        request.duration_ms = duration_ms
        self._call_service(self.emotion_client, request)

    def _short_flash(self) -> None:
        from PIL import Image

        image = Image.new("RGB", (854, 480), (48, 214, 170))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=90)
        frame = ShowImg()
        frame.width = 854
        frame.height = 480
        frame.data = list(buffer.getvalue())
        frame.encoding = "jpeg"
        request = DisplayImgs.Request()
        request.images = [frame]
        request.duration_ms = [150]
        self._call_service(self.display_client, request)

    def _perform_happy_body(self, correlation_id: str) -> None:
        if not self.yoga_action_path.is_file():
            raise FileNotFoundError(self.yoga_action_path)
        request = FunctionInput.Request()
        request.source = "heikesong"
        request.dag = self.yoga_action_path.read_text(encoding="utf-8")
        request.request_id = correlation_id
        self._call_service(self.function_client, request, timeout=55.0)

    def _play_yoga_audio(self) -> None:
        self._play_audio(self.yoga_audio_path)

    def _play_audio(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        with wave.open(str(path), "rb") as audio:
            if (
                audio.getnchannels() != 1
                or audio.getsampwidth() != 2
                or audio.getframerate() != 16000
            ):
                raise ValueError("yoga audio must be 16 kHz mono 16-bit PCM")
            samples = array("h", audio.readframes(audio.getnframes()))
            sample_rate = audio.getframerate()

        sequence = 0
        self._publish_audio_frame(sequence, sample_rate, [0x5555])
        sequence += 1
        chunk_size = 320
        for offset in range(0, len(samples), chunk_size):
            chunk = samples[offset : offset + chunk_size]
            self._publish_audio_frame(sequence, sample_rate, chunk)
            sequence += 1
            time.sleep(len(chunk) / sample_rate)
        self._publish_audio_frame(sequence, sample_rate, [-0x5556])
        time.sleep(0.08)

    def _publish_audio_frame(
        self, sequence: int, sample_rate: int, samples: list[int] | array
    ) -> None:
        message = SpeechPhoneToDog()
        message.frame_sequence = sequence
        message.sample_rate = sample_rate
        message.bit_depth = 16
        message.num_channels = 1
        message.num_samples = len(samples)
        message.audio_data = list(samples)
        self.audio_publisher.publish(message)

    def stop(self, reason: str) -> None:
        self._cancel_head()
        self._set_head_pose(0.0, 0.0, duration_ms=700)
        time.sleep(0.9)
        self._cancel_head()
        self.policy.reset()
        self.active_until_s = None
        self.completed_once = True
        self.node.get_logger().info(
            f"tracking disabled: {reason}; head centered; "
            f"adjustments={self.adjustments}; lost_stops={self.lost_stops}"
        )

    def _motion_context_is_safe(self) -> bool:
        snapshot = self._get_context_snapshot()
        if snapshot is None:
            return False
        nav = snapshot.function_status.nav_status
        return (
            not snapshot.dag_status.emergency_stop_active
            and snapshot.system_status.robot_is_static
            and nav.current_linear_velocity == 0.0
            and nav.current_angular_velocity == 0.0
        )

    def _wait_for_motion_completion(
        self, correlation_id: str, timeout_seconds: float
    ) -> str:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            snapshot = self._get_context_snapshot()
            if snapshot is None:
                time.sleep(0.25)
                continue
            status = snapshot.rcp_status
            if status.request_id != correlation_id or not status.last_outcome:
                time.sleep(0.25)
                continue
            if status.last_outcome == "SUCCESS":
                if self._motion_context_is_safe():
                    return status.last_outcome
                time.sleep(0.25)
                continue
            self.node.get_logger().error(
                f"motion task failed: correlation_id={correlation_id} "
                f"outcome={status.last_outcome} code={status.error_code} "
                f"failed_at={status.failed_at} error={status.error_message}"
            )
            return status.last_outcome
        self.node.get_logger().error(
            f"motion task timed out: correlation_id={correlation_id}"
        )
        return "TIMEOUT"

    def _get_context_snapshot(self):
        if not self.context_client.wait_for_service(timeout_sec=2.0):
            return None
        future = self.context_client.call_async(GetContext.Request())
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=3.0)
        if not future.done() or future.exception() is not None:
            return None
        return future.result().snapshot

    def _request(
        self,
        target_state: int,
        pitch_rad: float = 0.0,
        yaw_rad: float = 0.0,
        duration_ms: int = 650,
    ):
        request = HeadAction.Request()
        request.target_state = target_state
        request.mode = request.ANGLE_CONTROL
        request.req_id = f"heikesong-track-{uuid.uuid4().hex[:8]}"
        request.pre_check = False
        request.duration_ms = duration_ms
        request.loop_enabled = False
        request.playback_rate = 1.0
        request.target_angles = (
            [float(pitch_rad), float(yaw_rad)] if target_state else []
        )
        future = self.head_client.call_async(request)
        rclpy.spin_until_future_complete(self.node, future, timeout_sec=3.0)
        return future.result() if future.done() and future.exception() is None else None

    def _cancel_head(self) -> None:
        if not self.head_client.wait_for_service(timeout_sec=2.0):
            return
        self._request(0)
        self.head_active = False

    def _set_head_pose(
        self,
        pitch_rad: float,
        yaw_rad: float,
        duration_ms: int = 650,
    ) -> bool:
        if not self.head_client.wait_for_service(timeout_sec=2.0):
            return False
        response = self._request(1, pitch_rad, yaw_rad, duration_ms)
        message = str(getattr(response, "message", "")).lower()
        if response is not None and "already active" in message:
            self._cancel_head()
            response = self._request(1, pitch_rad, yaw_rad, duration_ms)
        self.head_active = bool(response and response.success)
        return self.head_active


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--session-seconds",
        type=float,
        default=300.0,
        help="Tracking duration after wakeup; must be between 5 and 1800 seconds.",
    )
    parser.add_argument(
        "--keyword-model-dir",
        type=Path,
        help="Enable offline keyword spotting with the model in this directory.",
    )
    parser.add_argument(
        "--wake-trigger",
        action="store_true",
        help="Also allow the vendor wakeup event to toggle tracking.",
    )
    parser.add_argument(
        "--yoga-audio-path",
        type=Path,
        default=Path(
            "/userdata/vbot/.local/share/heikesong/audio/yoga_start_builtin_ai.wav"
        ),
    )
    parser.add_argument(
        "--yoga-action-path",
        type=Path,
        default=Path("/app/config/dags/idle/HAPPINESS.json"),
    )
    parser.add_argument(
        "--downward-dog-action-path",
        type=Path,
        default=Path(
            "/userdata/vbot/.local/share/heikesong/actions/DOWNWARD_DOG_ONCE.json"
        ),
    )
    parser.add_argument(
        "--push-up-action-path",
        type=Path,
        default=Path("/app/config/dags/actions/PUSHUP.json"),
    )
    parser.add_argument(
        "--lay-down-action-path",
        type=Path,
        default=Path("/app/config/dags/idle/SIT_WITHHEAD.json"),
    )
    parser.add_argument(
        "--photo-output-path",
        type=Path,
        default=Path("/userdata/vbot/.local/share/heikesong/photos"),
    )
    parser.add_argument(
        "--yoga-wake-audio-path",
        type=Path,
        default=Path(
            "/userdata/vbot/.local/share/heikesong/audio/jiajia_wake_ack_builtin.wav"
        ),
    )
    parser.add_argument(
        "--command-arm-seconds",
        "--yoga-arm-seconds",
        dest="command_arm_seconds",
        type=float,
        default=10.0,
    )
    parser.add_argument(
        "--one-shot",
        action="store_true",
        help="Exit after the first triggered tracking session is stopped.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 5.0 <= args.session_seconds <= 1800.0:
        raise SystemExit("--session-seconds must be between 5 and 1800")
    if not 3.0 <= args.command_arm_seconds <= 30.0:
        raise SystemExit("--command-arm-seconds must be between 3 and 30")
    rclpy.init()
    tracker = VoicePersonTrackerNode(
        args.session_seconds,
        keyword_model_dir=args.keyword_model_dir,
        wake_trigger=args.wake_trigger,
        yoga_audio_path=args.yoga_audio_path,
        yoga_wake_audio_path=args.yoga_wake_audio_path,
        yoga_action_path=args.yoga_action_path,
        downward_dog_action_path=args.downward_dog_action_path,
        push_up_action_path=args.push_up_action_path,
        lay_down_action_path=args.lay_down_action_path,
        photo_output_path=args.photo_output_path,
        command_arm_seconds=args.command_arm_seconds,
    )
    try:
        while rclpy.ok():
            rclpy.spin_once(tracker.node, timeout_sec=0.1)
            tracker.tick()
            if args.one_shot and tracker.completed_once:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if tracker.active_until_s is not None:
            tracker.stop("process exit")
        tracker.node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            # SIGINT may already have shut down the default ROS context.
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
