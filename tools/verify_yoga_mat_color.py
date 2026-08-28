#!/usr/bin/env python3
"""Run the conservative color-mat detector and save JSON/overlay evidence."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
import sys

import cv2
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from heikesong.perception.yoga_mat_color import ColorYogaMatDetector  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("images", nargs="+")
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    detector = ColorYogaMatDetector()
    records = []

    for raw_path in args.images:
        path = Path(raw_path)
        encoded = np.fromfile(path, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise SystemExit(f"cannot read image: {path}")
        analysis = detector.analyze(image)
        observation = analysis.observation
        overlay = image.copy()
        if observation.detected:
            points = [
                [round(point.x), round(point.y)] for point in observation.boundary
            ]
            cv2.polylines(
                overlay,
                [np.asarray(points, dtype=np.int32)],
                True,
                (0, 255, 0),
                2,
            )
            label = f"MAT {observation.confidence:.3f}"
            color = (0, 255, 0)
        else:
            points = []
            label = "MAT REJECTED"
            color = (0, 0, 255)
        cv2.putText(overlay, label, (12, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        overlay_path = output / f"{path.stem}_overlay.jpg"
        mask_path = output / f"{path.stem}_mask.png"
        overlay_ok, overlay_data = cv2.imencode(".jpg", overlay)
        mask_ok, mask_data = cv2.imencode(".png", analysis.mask)
        if not overlay_ok or not mask_ok:
            raise SystemExit(f"cannot encode evidence for: {path}")
        overlay_data.tofile(overlay_path)
        mask_data.tofile(mask_path)
        record = {
            "file": str(path),
            "detected": observation.detected,
            "confidence_type": "calibrated_heuristic",
            "confidence": observation.confidence,
            "center_px": asdict(observation.center) if observation.center else None,
            "boundary_px": [asdict(point) for point in observation.boundary],
            "candidate_count": analysis.candidate_count,
            "rejection_counts": analysis.rejection_counts,
            "overlay": str(overlay_path),
            "mask": str(mask_path),
        }
        records.append(record)

    (output / "results.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(records, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
