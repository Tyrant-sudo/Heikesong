"""ROS-independent target tracking policy for person-centered orbit motion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


def infer_facing_orbit_direction(
    keypoints: Sequence[tuple[float, float, float]],
    bbox_width_px: float,
    minimum_confidence: float = 0.35,
) -> int | None:
    """Return left (1), right (-1), or None for an ambiguous face direction."""
    if len(keypoints) < 5 or bbox_width_px <= 0.0:
        return None
    nose_x, _, nose_confidence = keypoints[0]
    if nose_confidence < minimum_confidence:
        return None
    visible_ears = [
        keypoints[index][0]
        for index in (3, 4)
        if keypoints[index][2] >= minimum_confidence
    ]
    if not visible_ears:
        return None
    ear_center_x = sum(visible_ears) / len(visible_ears)
    offset_px = nose_x - ear_center_x
    minimum_offset_px = max(6.0, bbox_width_px * 0.04)
    if offset_px <= -minimum_offset_px:
        return 1
    if offset_px >= minimum_offset_px:
        return -1
    return None


class OrbitDecision(str, Enum):
    MOVE = "move"
    HOLD = "hold"
    COMPLETE = "complete"
    STOP = "stop"


@dataclass(frozen=True)
class PersonDetection:
    area_px2: float
    center_x_px: float
    confidence: float


@dataclass(frozen=True)
class PersonOrbitConfig:
    image_width_px: float = 480.0
    initial_center_min_px: float = 150.0
    initial_center_max_px: float = 350.0
    tracking_center_min_px: float = 5.0
    tracking_center_max_px: float = 475.0
    initial_minimum_area_px2: float = 1800.0
    tracking_minimum_area_px2: float = 500.0
    minimum_confidence: float = 0.55
    target_timeout_s: float = 0.55
    lateral_speed_mps: float = 0.30
    base_angular_speed_rps: float = 0.35
    angular_gain_rps_per_px: float = 0.003
    maximum_angular_speed_rps: float = 0.70
    minimum_angular_speed_rps: float = -0.70


@dataclass(frozen=True)
class OrbitOutput:
    decision: OrbitDecision
    linear_y_mps: float
    angular_z_rps: float
    target: PersonDetection | None
    reason: str | None = None


class PersonOrbitPolicy:
    def __init__(self, config: PersonOrbitConfig | None = None) -> None:
        self.config = config or PersonOrbitConfig()
        self._direction = 1
        self._duration_s = 0.0
        self._started_at_s: float | None = None
        self._last_target_at_s: float | None = None
        self._target: PersonDetection | None = None

    @property
    def target(self) -> PersonDetection | None:
        return self._target

    def start(
        self,
        detections: list[PersonDetection],
        *,
        now_s: float,
        direction: int,
        duration_s: float,
    ) -> PersonDetection:
        if direction not in (-1, 1):
            raise ValueError("direction must be LEFT (1) or RIGHT (-1)")
        if duration_s <= 0.0:
            raise ValueError("duration_s must be positive")
        candidates = [
            item
            for item in detections
            if item.confidence >= self.config.minimum_confidence
            and item.area_px2 >= self.config.initial_minimum_area_px2
            and self.config.initial_center_min_px
            <= item.center_x_px
            <= self.config.initial_center_max_px
        ]
        if not candidates:
            raise ValueError("no central person target")
        self._target = max(candidates, key=lambda item: (item.area_px2, item.confidence))
        self._direction = direction
        self._duration_s = duration_s
        self._started_at_s = now_s
        self._last_target_at_s = now_s
        return self._target

    def update(
        self,
        detections: list[PersonDetection],
        *,
        now_s: float,
    ) -> OrbitOutput:
        if self._started_at_s is None or self._target is None:
            return OrbitOutput(OrbitDecision.STOP, 0.0, 0.0, None, "not started")
        if now_s - self._started_at_s >= self._duration_s:
            return OrbitOutput(OrbitDecision.COMPLETE, 0.0, 0.0, self._target)

        candidates = [
            item
            for item in detections
            if item.confidence >= self.config.minimum_confidence
            and item.area_px2 >= self.config.tracking_minimum_area_px2
            and self.config.tracking_center_min_px
            <= item.center_x_px
            <= self.config.tracking_center_max_px
        ]
        if candidates:
            previous_center = self._target.center_x_px
            self._target = min(
                candidates,
                key=lambda item: (
                    abs(item.center_x_px - previous_center),
                    -item.area_px2,
                ),
            )
            self._last_target_at_s = now_s
        elif (
            self._last_target_at_s is None
            or now_s - self._last_target_at_s > self.config.target_timeout_s
        ):
            return OrbitOutput(
                OrbitDecision.STOP,
                0.0,
                0.0,
                self._target,
                "target person lost",
            )
        else:
            return OrbitOutput(OrbitDecision.HOLD, 0.0, 0.0, self._target)

        error_px = self._target.center_x_px - self.config.image_width_px / 2.0
        angular = (
            -self._direction * self.config.base_angular_speed_rps
            - self.config.angular_gain_rps_per_px * error_px
        )
        angular = max(
            self.config.minimum_angular_speed_rps,
            min(self.config.maximum_angular_speed_rps, angular),
        )
        return OrbitOutput(
            OrbitDecision.MOVE,
            self._direction * self.config.lateral_speed_mps,
            angular,
            self._target,
        )

    def reset(self) -> None:
        self._started_at_s = None
        self._last_target_at_s = None
        self._target = None
