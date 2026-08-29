"""V2 yoga-mode arbitration shared by voice and visual adapters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class V2ModeState(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    TASK_RUNNING = "task_running"
    HIGH_FIVE_READY = "high_five_ready"


class V2Task(str, Enum):
    DOWNWARD_DOG = "downward_dog"
    PUSH_UP = "push_up"
    SUPPORT_WATCH = "support_watch"
    SEATED_COUNTDOWN = "seated_countdown"
    TAKE_PHOTO = "take_photo"
    HIGH_FIVE_LEFT = "high_five_left"
    HIGH_FIVE_RIGHT = "high_five_right"
    PERSON_ORBIT = "person_orbit"


class TriggerSource(str, Enum):
    VOICE = "voice"
    VISUAL = "visual"


@dataclass(frozen=True)
class V2Decision:
    action: str
    task: V2Task | None = None
    reason: str = ""


class V2SessionCoordinator:
    """Gate all V2 side effects behind an explicit yoga-mode session."""

    def __init__(self, cooldown_seconds: float = 3.0) -> None:
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must not be negative")
        self.cooldown_seconds = cooldown_seconds
        self.state = V2ModeState.IDLE
        self.active_task: V2Task | None = None
        self.end_requested = False
        self._cooldown_until_s: dict[V2Task, float] = {}
        self._visual_tokens: set[str] = set()

    def enter_mode(self) -> V2Decision:
        if self.state is not V2ModeState.IDLE:
            return V2Decision("ignored", reason="yoga mode is already active")
        self.state = V2ModeState.ACTIVE
        self.active_task = None
        self.end_requested = False
        self._cooldown_until_s.clear()
        self._visual_tokens.clear()
        return V2Decision("mode_started")

    def request_task(
        self,
        task: V2Task,
        source: TriggerSource,
        now_s: float,
        visual_token: str | None = None,
    ) -> V2Decision:
        if self.state is V2ModeState.IDLE:
            return V2Decision("ignored", task, "yoga mode is not active")
        if self.state is V2ModeState.HIGH_FIVE_READY:
            return V2Decision("ignored", task, "waiting for high-five confirmation")
        if self.state is V2ModeState.TASK_RUNNING:
            return V2Decision("ignored", task, "another task is running")
        if source is TriggerSource.VISUAL:
            if not visual_token:
                raise ValueError("visual requests require a stable episode token")
            if visual_token in self._visual_tokens:
                return V2Decision("ignored", task, "visual episode already handled")
        if now_s < self._cooldown_until_s.get(task, 0.0):
            return V2Decision("ignored", task, "task cooldown is active")

        if visual_token:
            self._visual_tokens.add(visual_token)
        self.state = V2ModeState.TASK_RUNNING
        self.active_task = task
        return V2Decision("run_task", task)

    def request_end(self) -> V2Decision:
        if self.state is V2ModeState.IDLE:
            return V2Decision("ignored", reason="yoga mode is not active")
        if self.state is V2ModeState.TASK_RUNNING:
            self.end_requested = True
            return V2Decision("end_deferred", self.active_task)
        self.state = V2ModeState.TASK_RUNNING
        self.active_task = V2Task.HIGH_FIVE_RIGHT
        return V2Decision("run_task", V2Task.HIGH_FIVE_RIGHT)

    def confirm_high_five(
        self, side: str, now_s: float
    ) -> V2Decision:
        if self.state is not V2ModeState.HIGH_FIVE_READY:
            return V2Decision("ignored", reason="high five is not armed")
        task = (
            V2Task.HIGH_FIVE_LEFT
            if side == "left"
            else V2Task.HIGH_FIVE_RIGHT
            if side == "right"
            else None
        )
        if task is None:
            return V2Decision("ignored", reason="unknown raised-hand side")
        self.state = V2ModeState.TASK_RUNNING
        self.active_task = task
        return V2Decision("run_task", task)

    def finish_task(self, now_s: float, succeeded: bool = True) -> V2Decision:
        if self.state is not V2ModeState.TASK_RUNNING or self.active_task is None:
            return V2Decision("ignored", reason="no task is running")
        completed = self.active_task
        self.active_task = None
        if completed in {
            V2Task.HIGH_FIVE_LEFT,
            V2Task.HIGH_FIVE_RIGHT,
        }:
            self.exit_mode()
            return V2Decision("mode_ended", completed)
        if succeeded:
            self._cooldown_until_s[completed] = now_s + self.cooldown_seconds
        if self.end_requested:
            self.end_requested = False
            self.state = V2ModeState.TASK_RUNNING
            self.active_task = V2Task.HIGH_FIVE_RIGHT
            return V2Decision("run_task", V2Task.HIGH_FIVE_RIGHT)
        self.state = V2ModeState.ACTIVE
        return V2Decision("task_finished", completed)

    def exit_mode(self) -> None:
        self.state = V2ModeState.IDLE
        self.active_task = None
        self.end_requested = False
        self._cooldown_until_s.clear()
        self._visual_tokens.clear()
