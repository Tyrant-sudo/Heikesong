#!/usr/bin/env python3
"""Select the detected person standing on the visible yoga mat without motion."""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np
import rclpy
from camera_msgs.msg import JpegRequest
from camera_msgs.srv import GetJpegImages
from rclpy.node import Node
from vision_msgs.msg import PoseDetection


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.perception.yoga_mat_color import ColorYogaMatDetector  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--seconds", type=float, default=3.0)
    return parser.parse_args()


def _point_near_polygon(point: tuple[float, float], polygon: np.ndarray) -> bool:
    # Seated/cross-legged poses often exclude the legs from the YOLO box. The
    # visible far edge of the mat is therefore allowed a modest image-space gap.
    return cv2.pointPolygonTest(polygon.astype(np.float32), point, True) >= -50.0


class PersonOnMatProbe(Node):
    def __init__(self) -> None:
        super().__init__("heikesong_person_on_mat_probe")
        self.camera = self.create_client(GetJpegImages, "/get_jpeg_images")
        self.groups: dict[tuple[int, int], list[PoseDetection]] = defaultdict(list)
        self.create_subscription(PoseDetection, "/perception/poses", self._on_pose, 20)

    def _on_pose(self, message: PoseDetection) -> None:
        stamp = message.header.stamp
        self.groups[(stamp.sec, stamp.nanosec)].append(message)
        if len(self.groups) > 30:
            for key in sorted(self.groups)[:-20]:
                del self.groups[key]

    def capture(self) -> np.ndarray:
        if not self.camera.wait_for_service(timeout_sec=4.0):
            raise RuntimeError("camera service unavailable")
        request = GetJpegImages.Request()
        frame = JpegRequest()
        frame.channel_id = 0
        frame.width = 640
        frame.height = 360
        frame.quality = 95
        frame.undistort = True
        request.request.append(frame)
        future = self.camera.call_async(request)
        rclpy.spin_until_future_complete(self, future, timeout_sec=5.0)
        if not future.done() or future.exception() is not None:
            raise RuntimeError("camera request failed")
        response = future.result()
        if not response.response:
            raise RuntimeError("camera returned no frame")
        image = cv2.imdecode(
            np.frombuffer(bytes(response.response[0].data), dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        if image is None:
            raise RuntimeError("JPEG decode failed")
        return image


def mat_polygon(image: np.ndarray) -> tuple[np.ndarray, str, float, dict[str, int]]:
    analysis = ColorYogaMatDetector().analyze(image)
    if analysis.observation.detected:
        polygon = np.asarray(
            [[point.x, point.y] for point in analysis.observation.boundary],
            dtype=np.float32,
        )
        return polygon, "complete", float(analysis.observation.confidence), analysis.rejection_counts

    contours, _ = cv2.findContours(
        analysis.mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    contours = [contour for contour in contours if cv2.contourArea(contour) >= image.size * 0.0008]
    if not contours:
        raise RuntimeError(f"mat color region not found: {analysis.rejection_counts}")
    contour = max(contours, key=cv2.contourArea)
    hull = cv2.convexHull(contour).reshape(-1, 2).astype(np.float32)
    if len(hull) < 3:
        raise RuntimeError("partial mat region has invalid geometry")
    perimeter = cv2.arcLength(hull.reshape(-1, 1, 2), True)
    quadrilateral = None
    for fraction in np.linspace(0.01, 0.08, 29):
        candidate = cv2.approxPolyDP(
            hull.reshape(-1, 1, 2), float(perimeter * fraction), True
        ).reshape(-1, 2)
        if len(candidate) == 4 and cv2.isContourConvex(candidate.astype(np.float32)):
            quadrilateral = candidate.astype(np.float32)
            break
    if quadrilateral is None:
        raise RuntimeError("partial mat region cannot be fitted to four corners")
    area_fraction = float(cv2.contourArea(contour) / (image.shape[0] * image.shape[1]))
    return quadrilateral, "partial_color_region", min(0.75, area_fraction * 20.0), analysis.rejection_counts


def evaluate_person(
    message: PoseDetection,
    polygon: np.ndarray,
    image_shape: tuple[int, int],
) -> dict[str, object]:
    x1, y1 = float(message.bbox_min.x), float(message.bbox_min.y)
    x2, y2 = float(message.bbox_max.x), float(message.bbox_max.y)
    bottom = ((x1 + x2) * 0.5, y2)
    points: list[tuple[str, float, float]] = [("bbox_bottom", *bottom)]
    for index, name in ((15, "left_ankle"), (16, "right_ankle")):
        keypoint = message.keypoints[index]
        if float(keypoint.confidence) >= 0.0:
            points.append((name, float(keypoint.x), float(keypoint.y)))
    matches = [name for name, x, y in points if _point_near_polygon((x, y), polygon)]

    height, width = image_shape
    person_mask = np.zeros((height, width), dtype=np.uint8)
    px1, py1 = max(0, round(x1)), max(0, round(y1))
    px2, py2 = min(width - 1, round(x2)), min(height - 1, round(y2))
    if px2 > px1 and py2 > py1:
        person_mask[py1 : py2 + 1, px1 : px2 + 1] = 255
    mat_mask = np.zeros_like(person_mask)
    cv2.fillPoly(mat_mask, [polygon.astype(np.int32)], 255)
    bbox_area = max(1, int(np.count_nonzero(person_mask)))
    overlap = float(np.count_nonzero(cv2.bitwise_and(person_mask, mat_mask)) / bbox_area)
    association = 2.0 * len(matches) + min(2.0, overlap * 5.0)
    return {
        "score": float(message.score),
        "bbox": [x1, y1, x2, y2],
        "center_x": (x1 + x2) * 0.5,
        "mat_points": matches,
        "bbox_mat_overlap": overlap,
        "association_score": association,
    }


def main() -> int:
    args = parse_args()
    rclpy.init()
    node = PersonOnMatProbe()
    try:
        image = node.capture()
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        if not node.groups:
            raise RuntimeError("no pose detections received")
        latest_stamp = max(node.groups)
        detections = [message for message in node.groups[latest_stamp] if message.class_id == 0]
        polygon, mat_mode, mat_confidence, rejections = mat_polygon(image)
        people = [
            evaluate_person(message, polygon, image.shape[:2])
            for message in detections
        ]
        people.sort(key=lambda item: (item["association_score"], item["score"]), reverse=True)
        target = people[0] if people and people[0]["association_score"] >= 2.0 else None

        annotated = image.copy()
        cv2.polylines(annotated, [polygon.astype(np.int32)], True, (255, 0, 255), 3)
        for index, person in enumerate(people):
            x1, y1, x2, y2 = [round(value) for value in person["bbox"]]
            selected = person is target
            color = (0, 220, 0) if selected else (0, 180, 255)
            cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
            cv2.putText(
                annotated,
                f"{'TARGET' if selected else 'person'} assoc={person['association_score']:.1f}",
                (max(0, x1), max(18, y1 - 6)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                color,
                2,
                cv2.LINE_AA,
            )
        image_path = Path(args.image)
        image_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(image_path), annotated):
            raise RuntimeError("failed to write annotated image")
        report = {
            "result": "target_selected" if target else "no_person_on_mat",
            "pose_stamp": list(latest_stamp),
            "mat_mode": mat_mode,
            "mat_confidence": mat_confidence,
            "mat_polygon": polygon.tolist(),
            "mat_rejections": rejections,
            "people": people,
            "target": target,
            "image": str(image_path),
        }
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, separators=(",", ":")))
        return 0 if target else 2
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
