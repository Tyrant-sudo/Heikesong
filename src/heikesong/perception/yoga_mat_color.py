"""Conservative fixed-color yoga-mat detection for an undistorted BGR frame."""

from __future__ import annotations

from dataclasses import dataclass
import time

import cv2
import numpy as np

from heikesong.core.models import MatObservation, Point2D


@dataclass(frozen=True)
class ColorMatConfig:
    """Thresholds calibrated for the current flesh-pink/purple yoga mat."""

    lab_lower: tuple[int, int, int] = (130, 131, 125)
    lab_upper: tuple[int, int, int] = (180, 140, 134)
    ground_top_fraction: float = 0.58
    min_area_fraction: float = 0.0045
    min_solidity: float = 0.84
    min_width_px_at_480: int = 12
    min_height_px_at_270: int = 10
    side_margin_fraction: float = 0.012
    bottom_margin_fraction: float = 0.025


@dataclass(frozen=True)
class ColorMatAnalysis:
    observation: MatObservation
    mask: np.ndarray
    candidate_count: int
    rejection_counts: dict[str, int]


class ColorYogaMatDetector:
    """Detect a complete mat polygon and reject clipped or occluded candidates."""

    def __init__(self, config: ColorMatConfig | None = None) -> None:
        self.config = config or ColorMatConfig()

    def detect(self, frame: object) -> MatObservation:
        return self.analyze(frame).observation

    def analyze(
        self,
        frame: object,
        *,
        observed_at_s: float | None = None,
    ) -> ColorMatAnalysis:
        image = self._validate_frame(frame)
        height, width = image.shape[:2]
        mask = self._build_mask(image)
        contours, _ = cv2.findContours(
            mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        min_area = self.config.min_area_fraction * width * height
        x_margin = max(3, round(width * self.config.side_margin_fraction))
        bottom_margin = max(5, round(height * self.config.bottom_margin_fraction))
        min_width = max(6, round(self.config.min_width_px_at_480 * width / 480))
        min_height = max(5, round(self.config.min_height_px_at_270 * height / 270))
        rejection_counts: dict[str, int] = {}
        accepted: list[tuple[float, np.ndarray, float]] = []

        def reject(reason: str) -> None:
            rejection_counts[reason] = rejection_counts.get(reason, 0) + 1

        for contour in contours:
            area = float(cv2.contourArea(contour))
            if area < min_area:
                reject("area")
                continue

            x, y, box_width, box_height = cv2.boundingRect(contour)
            if box_width < min_width or box_height < min_height:
                reject("dimensions")
                continue
            if (
                x <= x_margin
                or x + box_width >= width - x_margin
                or y + box_height >= height - bottom_margin
            ):
                reject("clipped")
                continue

            hull = cv2.convexHull(contour)
            hull_area = float(cv2.contourArea(hull))
            solidity = area / hull_area if hull_area > 0 else 0.0
            if solidity < self.config.min_solidity:
                reject("incomplete")
                continue

            polygon = _quadrilateral_from_hull(hull)
            if polygon is None:
                reject("geometry")
                continue

            area_score = min(1.0, area / (min_area * 3.0))
            confidence = min(0.99, 0.65 * solidity + 0.35 * area_score)
            accepted.append((confidence, polygon, area))

        timestamp = time.time() if observed_at_s is None else observed_at_s
        if not accepted:
            observation = MatObservation(
                detected=False,
                confidence=0.0,
                center=None,
                boundary=(),
                observed_at_s=timestamp,
            )
        else:
            confidence, polygon, _ = max(accepted, key=lambda item: (item[0], item[2]))
            ordered = _order_clockwise(polygon.reshape(4, 2).astype(float))
            center_xy = ordered.mean(axis=0)
            observation = MatObservation(
                detected=True,
                confidence=confidence,
                center=Point2D(float(center_xy[0]), float(center_xy[1])),
                boundary=tuple(Point2D(float(x), float(y)) for x, y in ordered),
                observed_at_s=timestamp,
            )

        return ColorMatAnalysis(
            observation=observation,
            mask=mask,
            candidate_count=len(contours),
            rejection_counts=rejection_counts,
        )

    def _build_mask(self, image: np.ndarray) -> np.ndarray:
        lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
        mask = cv2.inRange(
            lab,
            np.asarray(self.config.lab_lower, dtype=np.uint8),
            np.asarray(self.config.lab_upper, dtype=np.uint8),
        )
        ground_top = round(image.shape[0] * self.config.ground_top_fraction)
        mask[:ground_top, :] = 0
        mask = cv2.morphologyEx(
            mask, cv2.MORPH_OPEN, np.ones((3, 3), dtype=np.uint8)
        )
        return cv2.morphologyEx(
            mask, cv2.MORPH_CLOSE, np.ones((7, 7), dtype=np.uint8)
        )

    @staticmethod
    def _validate_frame(frame: object) -> np.ndarray:
        if not isinstance(frame, np.ndarray):
            raise TypeError("frame must be a numpy BGR image")
        if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
            raise ValueError("frame must have shape HxWx3 and dtype uint8")
        return frame


def _quadrilateral_from_hull(hull: np.ndarray) -> np.ndarray | None:
    perimeter = cv2.arcLength(hull, True)
    for epsilon_fraction in np.linspace(0.01, 0.04, 13):
        polygon = cv2.approxPolyDP(hull, float(epsilon_fraction * perimeter), True)
        if len(polygon) == 4 and cv2.isContourConvex(polygon):
            return polygon
    return None


def _order_clockwise(points: np.ndarray) -> np.ndarray:
    center = points.mean(axis=0)
    angles = np.arctan2(points[:, 1] - center[1], points[:, 0] - center[0])
    ordered = points[np.argsort(angles)]
    start = int(np.argmin(ordered.sum(axis=1)))
    return np.roll(ordered, -start, axis=0)
