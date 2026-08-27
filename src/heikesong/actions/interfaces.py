"""External device ports used by V1 behavior modules."""

from __future__ import annotations

from typing import Protocol


class RobotAdapter(Protocol):
    def imitate_downward_dog(self, correlation_id: str) -> None: ...

    def stop_motion(self, reason: str) -> None: ...


class PhotoCapture(Protocol):
    def capture(self, correlation_id: str) -> str: ...
