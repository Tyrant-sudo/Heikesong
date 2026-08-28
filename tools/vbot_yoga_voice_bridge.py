#!/usr/bin/env python3
"""Bridge Vbot Aorta ASR events to the V1 yoga start feedback."""

from __future__ import annotations

import argparse
import io
import queue
import sys
import time
import uuid
from pathlib import Path


VENDOR_PYTHON_PATHS = (
    Path("/app_param/robo_orchard/python"),
    Path("/app/robo_orchard/workspace/python"),
)
for vendor_path in VENDOR_PYTHON_PATHS:
    if vendor_path.is_dir():
        sys.path.insert(0, str(vendor_path))

import rclpy
from function_msgs.srv import FunctionInput, SetSpeak
from peripheral_msgs.msg import ShowImg
from peripheral_msgs.srv import DisplayImgs, PlayEmotion
from speech_msgs.srv import SpeechControl

import aorta
from aorta.voice.AsrEvent import AsrEvent
from aorta.voice.VoiceEvent import VoiceEvent
from aorta.voice.VoiceEventPayload import VoiceEventPayload


class YogaVoiceBridge:
    def __init__(
        self,
        keywords: tuple[str, ...],
        feedback: str,
        enable_body_action: bool,
        body_action_path: Path,
    ) -> None:
        self.keywords = tuple(self._normalize(keyword) for keyword in keywords)
        self.feedback = feedback
        self.enable_body_action = enable_body_action
        self.body_action_path = body_action_path
        self.events: queue.Queue[tuple[int, str]] = queue.Queue()
        self.handled_sessions: set[int] = set()
        self.ros = rclpy.create_node("heikesong_yoga_voice_bridge")
        self.speech = self.ros.create_client(SpeechControl, "/speech_control")
        self.emotion = self.ros.create_client(
            PlayEmotion, "/display_node/play_emotion"
        )
        self.display = self.ros.create_client(
            DisplayImgs, "/display_node/display_imgs"
        )
        self.speak = self.ros.create_client(SetSpeak, "/set_speak")
        self.function_input = self.ros.create_client(
            FunctionInput, "/function_input"
        )
        self.aorta = aorta.Node("heikesong_yoga_voice_bridge")
        self.subscription = self.aorta.create_subscriber(
            "topic/voice/event", self._on_voice_event
        )

    def _on_voice_event(self, payload: bytes, _context: object) -> None:
        event = VoiceEvent.GetRootAs(payload, 0)
        if event.PayloadType() != VoiceEventPayload.AsrEvent:
            return
        table = event.Payload()
        if table is None:
            return
        asr = AsrEvent()
        asr.Init(table.Bytes, table.Pos)
        if not asr.IsFinal() or asr.IsReject():
            return
        raw_text = asr.Text()
        text = raw_text.decode("utf-8", "replace") if raw_text else ""
        self.events.put((event.SessionId(), text))

    def run(self, timeout_seconds: float, one_shot: bool) -> bool:
        self._set_recognition_mode(SpeechControl.Request.CMD_RECOGNITION_MODE_DOUBAO_ASR)
        self.ros.get_logger().info(
            f"online ASR bridge ready; keywords={self.keywords!r}; "
            f"body_action={self.enable_body_action}"
        )
        matched = False
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(self.ros, timeout_sec=0.05)
            try:
                session_id, text = self.events.get_nowait()
            except queue.Empty:
                continue
            self.ros.get_logger().info(
                f"ASR final: session={session_id} text={text!r}"
            )
            normalized = self._normalize(text)
            if not any(keyword in normalized for keyword in self.keywords):
                continue
            if session_id in self.handled_sessions:
                continue
            self.handled_sessions.add(session_id)
            self._feedback()
            matched = True
            if one_shot:
                break
        return matched

    def close(self) -> None:
        try:
            self._notify_action(False)
            self._set_recognition_mode(
                SpeechControl.Request.CMD_RECOGNITION_MODE_SPEECH_SERVICE
            )
            self._set_chat(False)
        finally:
            self.subscription.close()
            self.aorta.close()
            self.ros.destroy_node()

    def _feedback(self) -> None:
        self._notify_action(True)
        self._stop_speaking()
        try:
            self._play_emotion(mode=0, duration_ms=700)
            time.sleep(0.75)
            self._short_flash()
            if self.enable_body_action:
                self._perform_happy_body()
            else:
                self._play_emotion(mode=19, duration_ms=1800)
            self._speak(self.feedback)
            self.ros.get_logger().info("yoga start feedback completed")
        finally:
            self._notify_action(False)

    def _call(self, client: object, request: object, timeout: float = 8.0):
        if not client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError(f"service unavailable: {client.srv_name}")
        future = client.call_async(request)
        deadline = time.monotonic() + timeout
        while not future.done() and time.monotonic() < deadline:
            rclpy.spin_once(self.ros, timeout_sec=0.05)
        if not future.done():
            raise TimeoutError(f"service timeout: {client.srv_name}")
        response = future.result()
        if hasattr(response, "success"):
            success = response.success
            accepted = all(success) if isinstance(success, (list, tuple)) else success
            if not accepted:
                raise RuntimeError(
                    f"service rejected: {client.srv_name}: {response}"
                )
        return response

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(text.split()).rstrip("，。！？!?、")

    def _set_recognition_mode(self, mode: int) -> None:
        request = SpeechControl.Request()
        request.request_type = request.REQUEST_SET_CMD_RECOGNITION
        request.enable = mode != request.CMD_RECOGNITION_MODE_OFF
        request.mode = mode
        self._call(self.speech, request)

    def _set_chat(self, enabled: bool) -> None:
        request = SpeechControl.Request()
        request.request_type = request.REQUEST_SET_CHAT_FUNCTION
        request.enable = enabled
        self._call(self.speech, request)

    def _notify_action(self, enabled: bool) -> None:
        request = SpeechControl.Request()
        request.request_type = (
            request.NOTIFY_ACTION_ON if enabled else request.NOTIFY_ACTION_OFF
        )
        request.enable = enabled
        self._call(self.speech, request)

    def _stop_speaking(self) -> None:
        request = SetSpeak.Request()
        request.target_state = 0
        request.mode = request.HUMAN_VOICE
        request.req_id = f"YOGA-STOP-{uuid.uuid4().hex[:8]}"
        request.pre_check = False
        request.machine_language_name = ""
        request.human_language_text = ""
        self._call(self.speak, request)

    def _play_emotion(self, mode: int, duration_ms: int) -> None:
        request = PlayEmotion.Request()
        request.target_state = 1
        request.req_id = f"YOGA-FACE-{uuid.uuid4().hex[:8]}"
        request.pre_check = False
        request.mode = mode
        request.duration_ms = duration_ms
        self._call(self.emotion, request)

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
        self._call(self.display, request)

    def _perform_happy_body(self) -> None:
        if not self.body_action_path.is_file():
            raise FileNotFoundError(
                f"body action DAG not found: {self.body_action_path}"
            )
        request = FunctionInput.Request()
        request.source = "heikesong"
        request.dag = self.body_action_path.read_text(encoding="utf-8")
        request.request_id = f"YOGA-HAPPY-{uuid.uuid4().hex[:8]}"
        self.ros.get_logger().info(
            f"starting body action: {self.body_action_path}"
        )
        self._call(self.function_input, request, timeout=55.0)
        self.ros.get_logger().info("happy body action completed")

    def _speak(self, text: str) -> None:
        request = SetSpeak.Request()
        request.target_state = 1
        request.mode = request.HUMAN_VOICE
        request.req_id = f"YOGA-TTS-{uuid.uuid4().hex[:8]}"
        request.pre_check = False
        request.machine_language_name = ""
        request.human_language_text = text
        self._call(self.speak, request, timeout=10.0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--keyword",
        action="append",
        help="trigger keyword; repeat for aliases (default: 瑜伽, 伽伽)",
    )
    parser.add_argument("--feedback", default="瑜伽开始了")
    parser.add_argument("--enable-body-action", action="store_true")
    parser.add_argument(
        "--body-action-path",
        type=Path,
        default=Path("/app/config/dags/idle/HAPPINESS.json"),
    )
    parser.add_argument("--timeout-seconds", type=float, default=150.0)
    parser.add_argument("--one-shot", action="store_true")
    args = parser.parse_args()
    if not 5.0 <= args.timeout_seconds <= 1800.0:
        raise SystemExit("--timeout-seconds must be between 5 and 1800")
    keywords = tuple(args.keyword or ("瑜伽", "伽伽"))
    if any(not keyword.strip() for keyword in keywords):
        raise SystemExit("--keyword must not be empty")

    rclpy.init()
    bridge = YogaVoiceBridge(
        keywords,
        args.feedback,
        args.enable_body_action,
        args.body_action_path,
    )
    try:
        return 0 if bridge.run(args.timeout_seconds, args.one_shot) else 2
    except KeyboardInterrupt:
        return 130
    finally:
        bridge.close()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
