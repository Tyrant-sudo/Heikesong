"""V1 yoga interaction sequencing independent of the device SDK."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from heikesong.actions.interfaces import DisplayAdapter, RobotAdapter, VoiceAdapter


@dataclass(frozen=True)
class YogaInteractionPhrases:
    start_keywords: tuple[str, ...] = ("瑜伽", "伽伽")
    start_feedback: str = "瑜伽开始了"


class YogaInteractionController:
    """Coordinates V1 output effects while preserving trace correlation."""

    def __init__(
        self,
        robot: RobotAdapter,
        display: DisplayAdapter,
        voice: VoiceAdapter,
        phrases: YogaInteractionPhrases | None = None,
    ) -> None:
        self._robot = robot
        self._display = display
        self._voice = voice
        self._phrases = phrases or YogaInteractionPhrases()
        self._claimed: set[tuple[str, str]] = set()

    def perform_downward_dog(self, correlation_id: str) -> bool:
        return self._run_motion_once(
            "downward_dog", correlation_id, self._robot.perform_downward_dog_combo
        )

    def perform_push_up(self, correlation_id: str) -> bool:
        return self._run_motion_once(
            "push_up", correlation_id, self._robot.perform_push_up
        )

    def sit_and_watch_user(self, correlation_id: str) -> bool:
        return self._run_motion_once(
            "sit_and_watch", correlation_id, self._robot.sit_and_watch_user
        )

    def lay_down_and_watch_user(self, correlation_id: str) -> bool:
        return self._run_motion_once(
            "lay_down_and_watch",
            correlation_id,
            self._robot.lay_down_and_watch_user,
        )

    def handle_voice_command(self, text: str, correlation_id: str) -> bool:
        normalized = self._normalize(text)
        if not any(
            self._normalize(keyword) in normalized
            for keyword in self._phrases.start_keywords
        ):
            return False
        if not self._claim("start_feedback", correlation_id):
            return True

        self._display.blink_then_flash(correlation_id)
        self._robot.celebrate_happy(correlation_id)
        self._voice.speak(self._phrases.start_feedback, correlation_id)
        return True

    def _run_motion_once(
        self, name: str, correlation_id: str, action: Callable[[str], None]
    ) -> bool:
        if not self._claim(name, correlation_id):
            return False
        action(correlation_id)
        return True

    def _claim(self, name: str, correlation_id: str) -> bool:
        if not correlation_id:
            raise ValueError("correlation_id must not be empty")
        key = (name, correlation_id)
        if key in self._claimed:
            return False
        self._claimed.add(key)
        return True

    @staticmethod
    def _normalize(text: str) -> str:
        return "".join(text.split()).rstrip("，。！？,！？?")
