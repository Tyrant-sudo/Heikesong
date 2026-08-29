"""Coarse human-pose classification and temporal gating for the V2 demo."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, IntEnum


class CocoKeypoint(IntEnum):
    NOSE = 0
    LEFT_SHOULDER = 5
    RIGHT_SHOULDER = 6
    LEFT_ELBOW = 7
    RIGHT_ELBOW = 8
    LEFT_WRIST = 9
    RIGHT_WRIST = 10
    LEFT_HIP = 11
    RIGHT_HIP = 12
    LEFT_KNEE = 13
    RIGHT_KNEE = 14
    LEFT_ANKLE = 15
    RIGHT_ANKLE = 16


class CoarsePoseLabel(str, Enum):
    UNKNOWN = "unknown"
    DOWNWARD_DOG = "downward_dog"
    PUSH_UP = "push_up"


class RaisedHandSide(str, Enum):
    LEFT = "left"
    RIGHT = "right"


@dataclass(frozen=True)
class PoseKeypoint:
    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class CoarsePoseFrame:
    keypoints: tuple[PoseKeypoint, ...]
    bbox_min_x: float
    bbox_min_y: float
    bbox_max_x: float
    bbox_max_y: float
    score: float
    observed_at_s: float
    image_width_px: float = 480.0
    image_height_px: float = 270.0

    def __post_init__(self) -> None:
        if len(self.keypoints) < 17:
            raise ValueError("COCO pose frame must contain at least 17 keypoints")
        if self.bbox_max_x <= self.bbox_min_x or self.bbox_max_y <= self.bbox_min_y:
            raise ValueError("pose bounding box must have positive area")
        if self.image_width_px <= 0 or self.image_height_px <= 0:
            raise ValueError("image dimensions must be positive")

    @property
    def bbox_width(self) -> float:
        return self.bbox_max_x - self.bbox_min_x

    @property
    def bbox_height(self) -> float:
        return self.bbox_max_y - self.bbox_min_y


@dataclass(frozen=True)
class CoarsePoseConfig:
    minimum_person_score: float = 0.55
    minimum_keypoint_confidence: float = 0.0
    pose_hold_seconds: float = 1.2
    pose_dropout_grace_seconds: float = 0.35
    stationary_hold_seconds: float = 5.0
    movement_threshold: float = 0.025
    target_lost_seconds: float = 1.0


@dataclass(frozen=True)
class CoarsePoseObservation:
    label: CoarsePoseLabel
    label_held_for_s: float
    stationary_for_s: float
    pose_trigger: CoarsePoseLabel | None
    support_trigger: bool
    raised_hand: RaisedHandSide | None
    framing_complete: bool
    observed_at_s: float


class CoarsePoseTracker:
    """Classify broad poses and emit one event per continuous visual episode."""

    _MOTION_POINTS = (
        CocoKeypoint.LEFT_SHOULDER,
        CocoKeypoint.RIGHT_SHOULDER,
        CocoKeypoint.LEFT_HIP,
        CocoKeypoint.RIGHT_HIP,
        CocoKeypoint.LEFT_KNEE,
        CocoKeypoint.RIGHT_KNEE,
        CocoKeypoint.LEFT_ANKLE,
        CocoKeypoint.RIGHT_ANKLE,
    )

    def __init__(self, config: CoarsePoseConfig | None = None) -> None:
        self.config = config or CoarsePoseConfig()
        self._label = CoarsePoseLabel.UNKNOWN
        self._label_since_s: float | None = None
        self._pose_emitted = False
        self._last_positive_pose_s: float | None = None
        self._stationary_since_s: float | None = None
        self._support_emitted = False
        self._previous_points: dict[int, tuple[float, float]] = {}
        self._last_seen_s: float | None = None

    def update(self, frame: CoarsePoseFrame) -> CoarsePoseObservation:
        if frame.score < self.config.minimum_person_score:
            return self.lost(frame.observed_at_s)

        now_s = frame.observed_at_s
        self._last_seen_s = now_s
        label = self._classify(frame)
        if label is not CoarsePoseLabel.UNKNOWN:
            self._last_positive_pose_s = now_s
        elif (
            self._label is not CoarsePoseLabel.UNKNOWN
            and self._last_positive_pose_s is not None
            and now_s - self._last_positive_pose_s
            <= self.config.pose_dropout_grace_seconds
        ):
            label = self._label
        if label != self._label:
            self._label = label
            self._label_since_s = now_s
            self._pose_emitted = False
        elif self._label_since_s is None:
            self._label_since_s = now_s

        label_since_s = (
            now_s if self._label_since_s is None else self._label_since_s
        )
        label_held_for_s = max(0.0, now_s - label_since_s)
        pose_trigger = None
        if (
            label is not CoarsePoseLabel.UNKNOWN
            and not self._pose_emitted
            and label_held_for_s >= self.config.pose_hold_seconds
        ):
            pose_trigger = label
            self._pose_emitted = True

        movement = self._movement(frame)
        if movement is None or movement > self.config.movement_threshold:
            self._stationary_since_s = now_s
            self._support_emitted = False
        elif self._stationary_since_s is None:
            self._stationary_since_s = now_s
        stationary_since_s = (
            now_s
            if self._stationary_since_s is None
            else self._stationary_since_s
        )
        stationary_for_s = max(0.0, now_s - stationary_since_s)
        support_trigger = False
        if (
            not self._support_emitted
            and stationary_for_s >= self.config.stationary_hold_seconds
        ):
            support_trigger = True
            self._support_emitted = True

        return CoarsePoseObservation(
            label=label,
            label_held_for_s=label_held_for_s,
            stationary_for_s=stationary_for_s,
            pose_trigger=pose_trigger,
            support_trigger=support_trigger,
            raised_hand=self._raised_hand(frame),
            framing_complete=self._framing_complete(frame),
            observed_at_s=now_s,
        )

    def lost(self, now_s: float) -> CoarsePoseObservation:
        if (
            self._last_seen_s is not None
            and now_s - self._last_seen_s <= self.config.target_lost_seconds
        ):
            return CoarsePoseObservation(
                self._label,
                max(
                    0.0,
                    now_s
                    - (now_s if self._label_since_s is None else self._label_since_s),
                ),
                max(
                    0.0,
                    now_s
                    - (
                        now_s
                        if self._stationary_since_s is None
                        else self._stationary_since_s
                    ),
                ),
                None,
                False,
                None,
                False,
                now_s,
            )
        self.reset()
        return CoarsePoseObservation(
            CoarsePoseLabel.UNKNOWN, 0.0, 0.0, None, False, None, False, now_s
        )

    def reset(self) -> None:
        self._label = CoarsePoseLabel.UNKNOWN
        self._label_since_s = None
        self._pose_emitted = False
        self._last_positive_pose_s = None
        self._stationary_since_s = None
        self._support_emitted = False
        self._previous_points = {}
        self._last_seen_s = None

    def resume_after_robot_motion(self) -> None:
        """Restart stillness timing without rearming the current pose episode."""
        self._stationary_since_s = None
        self._support_emitted = False
        self._previous_points = {}

    def _visible(self, frame: CoarsePoseFrame, index: CocoKeypoint) -> bool:
        return (
            frame.keypoints[index].confidence
            >= self.config.minimum_keypoint_confidence
        )

    def _best_side(
        self, frame: CoarsePoseFrame
    ) -> tuple[int, int, int, int, int, int]:
        sides = (
            (
                CocoKeypoint.LEFT_SHOULDER,
                CocoKeypoint.LEFT_ELBOW,
                CocoKeypoint.LEFT_WRIST,
                CocoKeypoint.LEFT_HIP,
                CocoKeypoint.LEFT_KNEE,
                CocoKeypoint.LEFT_ANKLE,
            ),
            (
                CocoKeypoint.RIGHT_SHOULDER,
                CocoKeypoint.RIGHT_ELBOW,
                CocoKeypoint.RIGHT_WRIST,
                CocoKeypoint.RIGHT_HIP,
                CocoKeypoint.RIGHT_KNEE,
                CocoKeypoint.RIGHT_ANKLE,
            ),
        )
        return max(
            sides,
            key=lambda side: sum(frame.keypoints[index].confidence for index in side),
        )

    def _classify(self, frame: CoarsePoseFrame) -> CoarsePoseLabel:
        shoulder_i, elbow_i, wrist_i, hip_i, knee_i, ankle_i = self._best_side(
            frame
        )
        required = (shoulder_i, hip_i)
        if not all(self._visible(frame, index) for index in required):
            return CoarsePoseLabel.UNKNOWN

        shoulder = frame.keypoints[shoulder_i]
        hip = frame.keypoints[hip_i]
        width = frame.bbox_width
        height = frame.bbox_height

        if self._visible(frame, ankle_i):
            ankle = frame.keypoints[ankle_i]
            hip_is_apex = (
                hip.y < shoulder.y - 0.07 * height
                and hip.y < ankle.y - 0.10 * height
                and abs(hip.x - shoulder.x) > 0.10 * width
                and abs(ankle.x - hip.x) > 0.10 * width
            )
            if hip_is_apex:
                if self._visible(frame, wrist_i):
                    wrist = frame.keypoints[wrist_i]
                    if abs(wrist.y - ankle.y) > 0.40 * height:
                        return CoarsePoseLabel.UNKNOWN
                return CoarsePoseLabel.DOWNWARD_DOG

        visible_leg_points = [
            index
            for index in (knee_i, ankle_i)
            if self._visible(frame, index)
        ]
        if not visible_leg_points:
            torso_x = abs(hip.x - shoulder.x)
            torso_y = abs(hip.y - shoulder.y)
            arm_support = False
            for arm_i in (wrist_i, elbow_i):
                if self._visible(frame, arm_i):
                    arm_support = (
                        frame.keypoints[arm_i].y
                        >= shoulder.y + 0.08 * height
                    )
                    break
            if (
                arm_support
                and torso_x >= 0.18 * width
                and torso_y <= 0.32 * height
                and torso_x >= 1.25 * torso_y
            ):
                return CoarsePoseLabel.PUSH_UP
            return CoarsePoseLabel.UNKNOWN
        leg_i = max(
            visible_leg_points,
            key=lambda index: frame.keypoints[index].confidence,
        )
        leg = frame.keypoints[leg_i]

        horizontal_span = abs(leg.x - shoulder.x)
        vertical_spread = max(shoulder.y, hip.y, leg.y) - min(
            shoulder.y, hip.y, leg.y
        )
        torso_span = abs(hip.x - shoulder.x)
        if (
            horizontal_span >= 0.25 * width
            and torso_span >= 0.10 * width
            and vertical_spread <= 0.42 * height
            and horizontal_span >= 1.25 * vertical_spread
        ):
            return CoarsePoseLabel.PUSH_UP
        return CoarsePoseLabel.UNKNOWN

    def _movement(self, frame: CoarsePoseFrame) -> float | None:
        current: dict[int, tuple[float, float]] = {}
        for index in self._MOTION_POINTS:
            if self._visible(frame, index):
                point = frame.keypoints[index]
                current[int(index)] = (
                    point.x / frame.image_width_px,
                    point.y / frame.image_height_px,
                )
        shared = current.keys() & self._previous_points.keys()
        movement = None
        if len(shared) >= 4:
            squared = [
                (current[index][0] - self._previous_points[index][0]) ** 2
                + (current[index][1] - self._previous_points[index][1]) ** 2
                for index in shared
            ]
            movement = math.sqrt(sum(squared) / len(squared))
        self._previous_points = current
        return movement

    def _raised_hand(self, frame: CoarsePoseFrame) -> RaisedHandSide | None:
        candidates: list[tuple[float, RaisedHandSide]] = []
        for shoulder_i, wrist_i, side in (
            (
                CocoKeypoint.LEFT_SHOULDER,
                CocoKeypoint.LEFT_WRIST,
                RaisedHandSide.LEFT,
            ),
            (
                CocoKeypoint.RIGHT_SHOULDER,
                CocoKeypoint.RIGHT_WRIST,
                RaisedHandSide.RIGHT,
            ),
        ):
            if not (
                self._visible(frame, shoulder_i) and self._visible(frame, wrist_i)
            ):
                continue
            shoulder = frame.keypoints[shoulder_i]
            wrist = frame.keypoints[wrist_i]
            lift = shoulder.y - wrist.y
            if lift >= 0.08 * frame.bbox_height:
                candidates.append((lift, side))
        return max(candidates, default=(0.0, None), key=lambda item: item[0])[1]

    def _framing_complete(self, frame: CoarsePoseFrame) -> bool:
        margin_x = frame.image_width_px * 0.015
        margin_y = frame.image_height_px * 0.015
        return (
            frame.bbox_min_x > margin_x
            and frame.bbox_max_x < frame.image_width_px - margin_x
            and frame.bbox_min_y > margin_y
            and frame.bbox_max_y < frame.image_height_px - margin_y
        )
