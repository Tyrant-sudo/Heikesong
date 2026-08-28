"""Reusable, ROS-independent horizontal person-tracking policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class HeadTrackingDecision(str, Enum):
    HOLD = "hold"
    ADJUST = "adjust"
    STOP = "stop"


@dataclass(frozen=True)
class HeadTrackingConfig:
    image_width_px: float = 480.0
    image_height_px: float = 270.0
    deadband_px: float = 45.0
    vertical_deadband_px: float = 18.0
    gain_rad_per_px: float = 0.0012
    pitch_gain_rad_per_px: float = 0.0015
    smoothing_alpha: float = 0.25
    maximum_slew_rad_per_s: float = 0.18
    nominal_update_period_s: float = 1.0
    maximum_step_rad: float = 0.18
    maximum_yaw_rad: float = 0.18
    target_pitch_rad: float | None = None
    minimum_pitch_rad: float = -0.21
    maximum_pitch_rad: float = 0.10
    maximum_pitch_step_rad: float = 0.12
    minimum_confidence: float = 0.55
    target_timeout_s: float = 1.0


@dataclass(frozen=True)
class HeadTrackingOutput:
    decision: HeadTrackingDecision
    target_yaw_rad: float
    target_pitch_rad: float
    error_px: float | None
    vertical_error_px: float | None


class PersonHeadTracker:
    def __init__(self, config: HeadTrackingConfig | None = None) -> None:
        self.config = config or HeadTrackingConfig()
        self._yaw_rad = 0.0
        self._pitch_rad = 0.0
        self._last_target_at_s: float | None = None
        self._last_center_x_px: float | None = None
        self._last_center_y_px: float | None = None
        self._last_update_at_s: float | None = None
        self._last_confidence = 0.0

    @property
    def yaw_rad(self) -> float:
        return self._yaw_rad

    @property
    def pitch_rad(self) -> float:
        return self._pitch_rad

    def observe(
        self,
        center_x_px: float,
        confidence: float,
        now_s: float,
        center_y_px: float | None = None,
    ) -> None:
        if confidence < self.config.minimum_confidence:
            return
        if self._last_center_x_px is None:
            self._last_center_x_px = center_x_px
        else:
            alpha = self.config.smoothing_alpha
            self._last_center_x_px = (
                alpha * center_x_px + (1.0 - alpha) * self._last_center_x_px
            )
        if center_y_px is not None:
            if self._last_center_y_px is None:
                self._last_center_y_px = center_y_px
            else:
                self._last_center_y_px = (
                    alpha * center_y_px + (1.0 - alpha) * self._last_center_y_px
                )
        self._last_confidence = confidence
        self._last_target_at_s = now_s

    def update(self, now_s: float) -> HeadTrackingOutput:
        elapsed_s = (
            self.config.nominal_update_period_s
            if self._last_update_at_s is None
            else max(0.0, now_s - self._last_update_at_s)
        )
        self._last_update_at_s = now_s
        if (
            self._last_target_at_s is None
            or now_s - self._last_target_at_s > self.config.target_timeout_s
        ):
            return HeadTrackingOutput(
                HeadTrackingDecision.STOP,
                self._yaw_rad,
                self._pitch_rad,
                None,
                None,
            )

        assert self._last_center_x_px is not None
        error_px = self.config.image_width_px / 2.0 - self._last_center_x_px
        slew_limit = self.config.maximum_slew_rad_per_s * elapsed_s
        step_limit = min(self.config.maximum_step_rad, slew_limit)
        raw_step = (
            0.0
            if abs(error_px) <= self.config.deadband_px
            else error_px * self.config.gain_rad_per_px
        )
        step = max(-step_limit, min(step_limit, raw_step))
        old_yaw_rad = self._yaw_rad
        self._yaw_rad = max(
            -self.config.maximum_yaw_rad,
            min(self.config.maximum_yaw_rad, self._yaw_rad + step),
        )

        vertical_error_px: float | None = None
        old_pitch_rad = self._pitch_rad
        if self.config.target_pitch_rad is not None:
            self._pitch_rad = self.config.target_pitch_rad
        elif self._last_center_y_px is not None:
            vertical_error_px = (
                self.config.image_height_px / 2.0 - self._last_center_y_px
            )
            raw_pitch_step = (
                0.0
                if abs(vertical_error_px) <= self.config.vertical_deadband_px
                else -vertical_error_px * self.config.pitch_gain_rad_per_px
            )
            pitch_step = max(
                -self.config.maximum_pitch_step_rad,
                min(self.config.maximum_pitch_step_rad, raw_pitch_step),
            )
            self._pitch_rad = max(
                self.config.minimum_pitch_rad,
                min(self.config.maximum_pitch_rad, self._pitch_rad + pitch_step),
            )

        decision = (
            HeadTrackingDecision.ADJUST
            if self._yaw_rad != old_yaw_rad or self._pitch_rad != old_pitch_rad
            else HeadTrackingDecision.HOLD
        )
        return HeadTrackingOutput(
            decision,
            self._yaw_rad,
            self._pitch_rad,
            error_px,
            vertical_error_px,
        )

    def reset(self) -> None:
        self._yaw_rad = 0.0
        self._pitch_rad = 0.0
        self._last_target_at_s = None
        self._last_center_x_px = None
        self._last_center_y_px = None
        self._last_update_at_s = None
        self._last_confidence = 0.0
