"""Geometry primitives for a convex navigation keepout zone."""

from __future__ import annotations

from dataclasses import dataclass
import math


Point = tuple[float, float]


@dataclass(frozen=True)
class OccupancyGridData:
    origin_x: float
    origin_y: float
    resolution: float
    width: int
    height: int
    data: tuple[int, ...]


@dataclass(frozen=True)
class KeepoutZone:
    boundary: tuple[Point, ...]

    def __post_init__(self) -> None:
        if len(self.boundary) < 3:
            raise ValueError("keepout boundary requires at least three points")

    def contains(self, point: Point) -> bool:
        return _point_in_polygon(point, self.boundary)

    def segment_allowed(self, start: Point, end: Point) -> bool:
        if self.contains(start) or self.contains(end):
            return False
        edges = zip(self.boundary, self.boundary[1:] + self.boundary[:1])
        return not any(_segments_intersect(start, end, a, b) for a, b in edges)

    def expanded(self, margin_m: float) -> "KeepoutZone":
        if margin_m < 0.0:
            raise ValueError("margin_m must be non-negative")
        if margin_m == 0.0:
            return self
        return KeepoutZone(tuple(_offset_convex_polygon(self.boundary, margin_m)))

    def occupancy_grid(
        self,
        *,
        resolution: float = 0.05,
        outer_margin_m: float = 0.25,
    ) -> OccupancyGridData:
        if resolution <= 0.0:
            raise ValueError("resolution must be positive")
        xs = [point[0] for point in self.boundary]
        ys = [point[1] for point in self.boundary]
        origin_x = math.floor((min(xs) - outer_margin_m) / resolution) * resolution
        origin_y = math.floor((min(ys) - outer_margin_m) / resolution) * resolution
        max_x = max(xs) + outer_margin_m
        max_y = max(ys) + outer_margin_m
        width = max(1, math.ceil((max_x - origin_x) / resolution))
        height = max(1, math.ceil((max_y - origin_y) / resolution))
        values: list[int] = []
        for row in range(height):
            y = origin_y + (row + 0.5) * resolution
            for column in range(width):
                x = origin_x + (column + 0.5) * resolution
                values.append(100 if self.contains((x, y)) else 0)
        return OccupancyGridData(
            origin_x=origin_x,
            origin_y=origin_y,
            resolution=resolution,
            width=width,
            height=height,
            data=tuple(values),
        )


@dataclass(frozen=True)
class Pose2D:
    x: float
    y: float
    yaw: float


@dataclass(frozen=True)
class Motion2D:
    linear_x: float
    linear_y: float
    angular_z: float


@dataclass(frozen=True)
class KeepoutMotionGate:
    zone: KeepoutZone
    prediction_horizon_s: float = 1.0
    integration_step_s: float = 0.1

    def command_allowed(self, pose: Pose2D, motion: Motion2D) -> bool:
        if self.prediction_horizon_s <= 0.0 or self.integration_step_s <= 0.0:
            raise ValueError("prediction horizon and integration step must be positive")
        if self.zone.contains((pose.x, pose.y)):
            return False
        speed = math.hypot(motion.linear_x, motion.linear_y)
        if speed <= 1e-6:
            return True

        steps = max(1, math.ceil(self.prediction_horizon_s / self.integration_step_s))
        dt = self.prediction_horizon_s / steps
        x, y, yaw = pose.x, pose.y, pose.yaw
        for _ in range(steps):
            world_vx = math.cos(yaw) * motion.linear_x - math.sin(yaw) * motion.linear_y
            world_vy = math.sin(yaw) * motion.linear_x + math.cos(yaw) * motion.linear_y
            next_point = (x + world_vx * dt, y + world_vy * dt)
            if not self.zone.segment_allowed((x, y), next_point):
                return False
            x, y = next_point
            yaw += motion.angular_z * dt
        return True


def _signed_area(points: tuple[Point, ...] | list[Point]) -> float:
    return 0.5 * sum(
        x1 * y2 - x2 * y1
        for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1])
    )


def _offset_convex_polygon(points: tuple[Point, ...], margin: float) -> list[Point]:
    ordered = list(points)
    if _signed_area(ordered) < 0.0:
        ordered.reverse()
    shifted_lines: list[tuple[Point, Point]] = []
    for start, end in zip(ordered, ordered[1:] + ordered[:1]):
        dx, dy = end[0] - start[0], end[1] - start[1]
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            raise ValueError("keepout polygon contains a zero-length edge")
        outward = (dy / length, -dx / length)
        shifted_start = (start[0] + margin * outward[0], start[1] + margin * outward[1])
        shifted_lines.append((shifted_start, (dx, dy)))

    result: list[Point] = []
    for index, current in enumerate(shifted_lines):
        previous = shifted_lines[index - 1]
        result.append(_line_intersection(previous, current))
    return result


def _line_intersection(first: tuple[Point, Point], second: tuple[Point, Point]) -> Point:
    point_a, direction_a = first
    point_b, direction_b = second
    denominator = _cross(direction_a, direction_b)
    if abs(denominator) <= 1e-9:
        raise ValueError("keepout polygon has parallel adjacent edges")
    difference = (point_b[0] - point_a[0], point_b[1] - point_a[1])
    distance = _cross(difference, direction_b) / denominator
    return (
        point_a[0] + distance * direction_a[0],
        point_a[1] + distance * direction_a[1],
    )


def _point_in_polygon(point: Point, polygon: tuple[Point, ...]) -> bool:
    x, y = point
    inside = False
    previous = polygon[-1]
    for current in polygon:
        x1, y1 = previous
        x2, y2 = current
        if _point_on_segment(point, previous, current):
            return True
        if (y1 > y) != (y2 > y):
            crossing_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing_x:
                inside = not inside
        previous = current
    return inside


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    orientations = (
        _orientation(a, b, c),
        _orientation(a, b, d),
        _orientation(c, d, a),
        _orientation(c, d, b),
    )
    if orientations[0] != orientations[1] and orientations[2] != orientations[3]:
        return True
    return any(
        orientation == 0 and _point_on_segment(point, start, end)
        for orientation, point, start, end in (
            (orientations[0], c, a, b),
            (orientations[1], d, a, b),
            (orientations[2], a, c, d),
            (orientations[3], b, c, d),
        )
    )


def _orientation(a: Point, b: Point, c: Point) -> int:
    value = _cross((b[0] - a[0], b[1] - a[1]), (c[0] - a[0], c[1] - a[1]))
    if abs(value) <= 1e-9:
        return 0
    return 1 if value > 0.0 else -1


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    if _orientation(start, end, point) != 0:
        return False
    return (
        min(start[0], end[0]) - 1e-9 <= point[0] <= max(start[0], end[0]) + 1e-9
        and min(start[1], end[1]) - 1e-9 <= point[1] <= max(start[1], end[1]) + 1e-9
    )


def _cross(first: Point, second: Point) -> float:
    return first[0] * second[1] - first[1] * second[0]
