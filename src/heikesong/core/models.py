"""Implementation-neutral contracts shared by V1 modules."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SessionState(str, Enum):
    IDLE = "idle"
    FINDING_MAT = "finding_mat"
    READY = "ready"
    ORBITING_MAT = "orbiting_mat"
    LOCATING_USER = "locating_user"
    FOLLOWING_USER = "following_user"
    RESPONDING_TO_POSE = "responding_to_pose"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAULT = "fault"


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class MatObservation:
    detected: bool
    confidence: float
    center: Point2D | None
    boundary: tuple[Point2D, ...]
    observed_at_s: float


@dataclass(frozen=True)
class UserObservation:
    detected: bool
    confidence: float
    position: Point2D | None
    direction_deg: float | None
    observed_at_s: float


@dataclass(frozen=True)
class PoseObservation:
    label: str
    confidence: float
    held_for_s: float
    observed_at_s: float


@dataclass(frozen=True)
class DomainEvent:
    name: str
    occurred_at_s: float
    correlation_id: str
    payload: dict[str, Any]
