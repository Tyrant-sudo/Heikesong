"""A monotonic, pause-aware session timer for V1."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class TimerState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FINISHED = "finished"


@dataclass(frozen=True)
class TimerSnapshot:
    state: TimerState
    elapsed_s: float
    remaining_s: float | None


class SessionTimer:
    """Track elapsed time using an injectable monotonic clock."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._state = TimerState.IDLE
        self._duration_s: float | None = None
        self._started_at_s: float | None = None
        self._elapsed_before_start_s = 0.0

    def start(self, duration_s: float | None = None) -> None:
        if duration_s is not None and duration_s <= 0:
            raise ValueError("duration_s must be positive")
        self._duration_s = duration_s
        self._elapsed_before_start_s = 0.0
        self._started_at_s = self._clock()
        self._state = TimerState.RUNNING

    def pause(self) -> None:
        if self._state is not TimerState.RUNNING:
            raise RuntimeError("only a running timer can be paused")
        self._elapsed_before_start_s = self._elapsed_now()
        self._started_at_s = None
        self._state = TimerState.PAUSED

    def resume(self) -> None:
        if self._state is not TimerState.PAUSED:
            raise RuntimeError("only a paused timer can be resumed")
        self._started_at_s = self._clock()
        self._state = TimerState.RUNNING

    def stop(self) -> None:
        if self._state is TimerState.RUNNING:
            self._elapsed_before_start_s = self._elapsed_now()
        self._started_at_s = None
        self._state = TimerState.STOPPED

    def snapshot(self) -> TimerSnapshot:
        elapsed_s = self._elapsed_now()
        remaining_s = None
        if self._duration_s is not None:
            remaining_s = max(0.0, self._duration_s - elapsed_s)
            if remaining_s == 0.0 and self._state is TimerState.RUNNING:
                elapsed_s = self._duration_s
                self._elapsed_before_start_s = elapsed_s
                self._started_at_s = None
                self._state = TimerState.FINISHED
        return TimerSnapshot(
            state=self._state,
            elapsed_s=elapsed_s,
            remaining_s=remaining_s,
        )

    def _elapsed_now(self) -> float:
        if self._state is TimerState.RUNNING and self._started_at_s is not None:
            return self._elapsed_before_start_s + self._clock() - self._started_at_s
        return self._elapsed_before_start_s
