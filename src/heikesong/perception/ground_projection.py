"""Project a detected rectangular mat from image pixels into a world frame."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np


class MatProjectionError(ValueError):
    pass


@dataclass(frozen=True)
class CameraIntrinsics:
    fx: float
    fy: float
    cx: float
    cy: float

    def matrix(self) -> np.ndarray:
        return np.asarray(
            [[self.fx, 0.0, self.cx], [0.0, self.fy, self.cy], [0.0, 0.0, 1.0]],
            dtype=np.float64,
        )


@dataclass(frozen=True)
class MatGroundProjection:
    boundary_world: tuple[tuple[float, float, float], ...]
    center_world: tuple[float, float, float]
    normal_world: tuple[float, float, float]
    reprojection_rms_px: float
    gravity_alignment: float
    camera_distance_m: float
    first_edge_m: float
    second_edge_m: float


@dataclass(frozen=True)
class StableBoundaryCluster:
    averaged_boundary: np.ndarray
    maximum_deviation: float
    inlier_count: int


def select_stable_boundary_cluster(
    boundaries: list[np.ndarray],
    *,
    required_inliers: int = 10,
    maximum_deviation: float = 0.15,
) -> StableBoundaryCluster | None:
    """Select stable polygon inliers without letting one first-frame outlier reset all."""

    if required_inliers <= 0 or maximum_deviation <= 0.0:
        raise ValueError("stable cluster limits must be positive")
    if len(boundaries) < required_inliers:
        return None
    reference = np.asarray(boundaries[0], dtype=np.float64)
    aligned = [_align_polygon(reference, np.asarray(item, dtype=np.float64)) for item in boundaries]
    median = np.median(np.stack(aligned), axis=0)
    deviations = [
        float(np.max(np.linalg.norm(item[:, :2] - median[:, :2], axis=1)))
        for item in aligned
    ]
    inliers = [item for item, deviation in zip(aligned, deviations) if deviation <= maximum_deviation]
    if len(inliers) < required_inliers:
        return None
    selected = inliers[-required_inliers:]
    averaged = np.mean(np.stack(selected), axis=0)
    selected_maximum = max(
        float(np.max(np.linalg.norm(item[:, :2] - median[:, :2], axis=1)))
        for item in selected
    )
    return StableBoundaryCluster(
        averaged_boundary=averaged,
        maximum_deviation=selected_maximum,
        inlier_count=len(inliers),
    )


def project_mat_boundary_to_world(
    boundary_px: np.ndarray,
    intrinsics: CameraIntrinsics,
    rotation_world_from_camera: np.ndarray,
    translation_world_from_camera: np.ndarray,
    *,
    long_edge_m: float = 1.8,
    short_edge_m: float = 0.8,
    min_gravity_alignment: float = 0.85,
    max_reprojection_rms_px: float = 3.0,
) -> MatGroundProjection:
    """Solve planar pose and transform the physical mat rectangle into world."""

    image_points = np.asarray(boundary_px, dtype=np.float64).reshape(-1, 2)
    if image_points.shape != (4, 2):
        raise MatProjectionError("exactly four image boundary points are required")
    rotation_wc = np.asarray(rotation_world_from_camera, dtype=np.float64)
    translation_wc = np.asarray(translation_world_from_camera, dtype=np.float64).reshape(3)
    if rotation_wc.shape != (3, 3):
        raise MatProjectionError("rotation_world_from_camera must be 3x3")

    candidates: list[tuple[float, MatGroundProjection]] = []
    for first_edge, second_edge in (
        (long_edge_m, short_edge_m),
        (short_edge_m, long_edge_m),
    ):
        object_points = _rectangle_points(first_edge, second_edge)
        solved = cv2.solvePnPGeneric(
            object_points,
            image_points,
            intrinsics.matrix(),
            None,
            flags=cv2.SOLVEPNP_IPPE,
        )
        if not solved[0]:
            continue
        for rvec, tvec in zip(solved[1], solved[2]):
            rotation_camera_from_mat, _ = cv2.Rodrigues(rvec)
            translation_camera_from_mat = np.asarray(tvec, dtype=np.float64).reshape(3)
            corners_camera = (
                rotation_camera_from_mat @ object_points.T
            ).T + translation_camera_from_mat
            if np.any(corners_camera[:, 2] <= 0.0):
                continue

            projected, _ = cv2.projectPoints(
                object_points,
                rvec,
                tvec,
                intrinsics.matrix(),
                None,
            )
            errors = projected.reshape(-1, 2) - image_points
            reprojection_rms = float(np.sqrt(np.mean(np.sum(errors * errors, axis=1))))
            normal_world = rotation_wc @ rotation_camera_from_mat[:, 2]
            gravity_alignment = float(abs(normal_world[2]) / np.linalg.norm(normal_world))
            camera_distance = float(np.linalg.norm(translation_camera_from_mat))

            corners_world = (
                rotation_wc @ corners_camera.T
            ).T + translation_wc
            center_world = rotation_wc @ translation_camera_from_mat + translation_wc
            projection = MatGroundProjection(
                boundary_world=tuple(tuple(float(v) for v in row) for row in corners_world),
                center_world=tuple(float(v) for v in center_world),
                normal_world=tuple(float(v) for v in normal_world),
                reprojection_rms_px=reprojection_rms,
                gravity_alignment=gravity_alignment,
                camera_distance_m=camera_distance,
                first_edge_m=first_edge,
                second_edge_m=second_edge,
            )
            score = reprojection_rms + 25.0 * (1.0 - gravity_alignment)
            candidates.append((score, projection))

    if not candidates:
        raise MatProjectionError("no positive-depth planar pose solution")
    _, best = min(candidates, key=lambda item: item[0])
    if best.gravity_alignment < min_gravity_alignment:
        raise MatProjectionError(
            f"mat plane is not horizontal enough: {best.gravity_alignment:.3f}"
        )
    if best.reprojection_rms_px > max_reprojection_rms_px:
        raise MatProjectionError(
            f"reprojection error too high: {best.reprojection_rms_px:.3f}px"
        )
    return best


def quaternion_xyzw_to_matrix(quaternion: tuple[float, float, float, float]) -> np.ndarray:
    x, y, z, w = quaternion
    norm = x * x + y * y + z * z + w * w
    if norm <= 0.0:
        raise MatProjectionError("zero-length quaternion")
    scale = 2.0 / norm
    xx, yy, zz = x * x * scale, y * y * scale, z * z * scale
    xy, xz, yz = x * y * scale, x * z * scale, y * z * scale
    wx, wy, wz = w * x * scale, w * y * scale, w * z * scale
    return np.asarray(
        [
            [1.0 - yy - zz, xy - wz, xz + wy],
            [xy + wz, 1.0 - xx - zz, yz - wx],
            [xz - wy, yz + wx, 1.0 - xx - yy],
        ],
        dtype=np.float64,
    )


def _rectangle_points(first_edge_m: float, second_edge_m: float) -> np.ndarray:
    half_first = first_edge_m / 2.0
    half_second = second_edge_m / 2.0
    return np.asarray(
        [
            [-half_first, -half_second, 0.0],
            [half_first, -half_second, 0.0],
            [half_first, half_second, 0.0],
            [-half_first, half_second, 0.0],
        ],
        dtype=np.float64,
    )


def _align_polygon(reference: np.ndarray, candidate: np.ndarray) -> np.ndarray:
    variants = []
    for reversed_candidate in (candidate, candidate[::-1]):
        variants.extend(np.roll(reversed_candidate, shift, axis=0) for shift in range(4))
    return min(
        variants,
        key=lambda variant: float(np.sum((variant[:, :2] - reference[:, :2]) ** 2)),
    )
