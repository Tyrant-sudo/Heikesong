"""Plan safe bypass and closed orbit routes around a convex keepout zone."""

from __future__ import annotations

from dataclasses import dataclass
import math

from heikesong.safety.keepout import KeepoutZone, Point


@dataclass(frozen=True)
class CornerBypassPlan:
    waypoints: tuple[Point, Point]
    side: str
    extra_margin_m: float


@dataclass(frozen=True)
class FullOrbitPlan:
    waypoints: tuple[Point, ...]
    side: str
    extra_margin_m: float


def point_to_polygon_distance(point: Point, boundary: tuple[Point, ...]) -> float:
    return min(
        _point_to_segment_distance(point, start, end)
        for start, end in zip(boundary, boundary[1:] + boundary[:1])
    )


def polyline_minimum_clearance(
    points: tuple[Point, ...],
    boundary: tuple[Point, ...],
    *,
    samples_per_segment: int = 100,
) -> float:
    minimum = math.inf
    for start, end in zip(points, points[1:]):
        for index in range(samples_per_segment + 1):
            fraction = index / samples_per_segment
            point = (
                start[0] + fraction * (end[0] - start[0]),
                start[1] + fraction * (end[1] - start[1]),
            )
            minimum = min(minimum, point_to_polygon_distance(point, boundary))
    return minimum


def plan_corner_bypass(
    zone: KeepoutZone,
    start: Point,
    yaw: float,
    *,
    side: str = "right",
    extra_margin_m: float = 0.20,
    distance_along_side_m: float = 0.65,
    waypoint_offset_m: float = 0.08,
) -> CornerBypassPlan:
    if side not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")
    if zone.contains(start):
        raise ValueError("route starts inside the keepout zone")

    route_zone = zone.expanded(extra_margin_m)
    boundary = route_zone.boundary
    nearest_edge = min(
        range(len(boundary)),
        key=lambda index: _point_to_segment_distance(
            start, boundary[index], boundary[(index + 1) % len(boundary)]
        ),
    )
    first_index = nearest_edge
    second_index = (nearest_edge + 1) % len(boundary)
    right = (math.sin(yaw), -math.cos(yaw))
    lateral = right if side == "right" else (-right[0], -right[1])

    def lateral_score(index: int) -> float:
        point = boundary[index]
        return (point[0] - start[0]) * lateral[0] + (point[1] - start[1]) * lateral[1]

    corner_index = max((first_index, second_index), key=lateral_score)
    other_front_index = second_index if corner_index == first_index else first_index
    neighbor_indices = (
        (corner_index - 1) % len(boundary),
        (corner_index + 1) % len(boundary),
    )
    side_index = next(index for index in neighbor_indices if index != other_front_index)
    corner = boundary[corner_index]
    side_end = boundary[side_index]
    side_length = math.dist(corner, side_end)
    if side_length <= distance_along_side_m:
        raise ValueError("keepout side is too short for the requested bypass")

    centroid = (
        sum(point[0] for point in boundary) / len(boundary),
        sum(point[1] for point in boundary) / len(boundary),
    )

    def offset_outward(point: Point) -> Point:
        direction = (point[0] - centroid[0], point[1] - centroid[1])
        length = math.hypot(*direction)
        return (
            point[0] + waypoint_offset_m * direction[0] / length,
            point[1] + waypoint_offset_m * direction[1] / length,
        )

    fraction = distance_along_side_m / side_length
    along_side = (
        corner[0] + fraction * (side_end[0] - corner[0]),
        corner[1] + fraction * (side_end[1] - corner[1]),
    )
    waypoints = (offset_outward(corner), offset_outward(along_side))
    polyline = (start,) + waypoints
    if any(not zone.segment_allowed(a, b) for a, b in zip(polyline, polyline[1:])):
        raise ValueError("planned bypass intersects the keepout zone")
    return CornerBypassPlan(waypoints, side, extra_margin_m)


def plan_full_orbit(
    zone: KeepoutZone,
    start: Point,
    yaw: float,
    *,
    side: str = "right",
    extra_margin_m: float = 0.20,
) -> FullOrbitPlan:
    """Approach the nearest orbit edge, traverse one loop, and return to entry."""

    if side not in {"left", "right"}:
        raise ValueError("side must be 'left' or 'right'")
    if zone.contains(start):
        raise ValueError("route starts inside the keepout zone")

    boundary = zone.expanded(extra_margin_m).boundary
    edge_candidates = []
    for index, (edge_start, edge_end) in enumerate(
        zip(boundary, boundary[1:] + boundary[:1])
    ):
        entry = _closest_point_on_segment(start, edge_start, edge_end)
        edge_candidates.append((math.dist(start, entry), index, entry))
    _, edge_index, entry = min(edge_candidates)
    if not zone.segment_allowed(start, entry):
        raise ValueError("approach to orbit entry intersects the keepout zone")

    first_index = edge_index
    second_index = (edge_index + 1) % len(boundary)
    right = (math.sin(yaw), -math.cos(yaw))
    lateral = right if side == "right" else (-right[0], -right[1])

    def score(index: int) -> float:
        point = boundary[index]
        return (point[0] - entry[0]) * lateral[0] + (point[1] - entry[1]) * lateral[1]

    chosen_index = max((first_index, second_index), key=score)
    step = 1 if chosen_index == second_index else -1
    ordered_indices = tuple(
        (chosen_index + step * offset) % len(boundary)
        for offset in range(len(boundary))
    )
    waypoints = (entry,) + tuple(boundary[index] for index in ordered_indices) + (entry,)
    polyline = (start,) + waypoints
    if any(not zone.segment_allowed(a, b) for a, b in zip(polyline, polyline[1:])):
        raise ValueError("planned orbit intersects the keepout zone")
    return FullOrbitPlan(waypoints, side, extra_margin_m)


def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    return math.dist(point, _closest_point_on_segment(point, start, end))


def _closest_point_on_segment(point: Point, start: Point, end: Point) -> Point:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-12:
        return start
    fraction = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared
    fraction = max(0.0, min(1.0, fraction))
    return (start[0] + fraction * dx, start[1] + fraction * dy)
