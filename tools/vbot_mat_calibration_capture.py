#!/usr/bin/env python3
"""Capture undistorted Vbot camera frames for yoga-mat calibration."""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

import rclpy
from camera_msgs.msg import JpegRequest
from camera_msgs.srv import GetJpegImages


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--stop-file", required=True)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--max-frames", type=int, default=1200)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=360)
    parser.add_argument("--quality", type=int, default=90)
    parser.add_argument("--channel", type=int, default=0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    stop_file = Path(args.stop_file)
    manifest_path = output / "manifest.jsonl"

    rclpy.init()
    node = rclpy.create_node("vbot_mat_calibration_capture")
    client = node.create_client(GetJpegImages, "/get_jpeg_images")
    if not client.wait_for_service(timeout_sec=10.0):
        raise SystemExit("camera service unavailable")

    next_capture = time.monotonic()
    with manifest_path.open("a", encoding="utf-8", buffering=1) as manifest:
        for index in range(args.max_frames):
            if stop_file.exists():
                break
            delay = next_capture - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            next_capture += args.interval

            request = GetJpegImages.Request()
            frame_request = JpegRequest()
            frame_request.channel_id = args.channel
            frame_request.width = args.width
            frame_request.height = args.height
            frame_request.quality = args.quality
            frame_request.undistort = True
            request.request.append(frame_request)
            future = client.call_async(request)
            rclpy.spin_until_future_complete(node, future, timeout_sec=5.0)
            if not future.done() or future.exception() is not None:
                continue
            response = future.result()
            if not response.response:
                continue

            frame = response.response[0]
            data = bytes(frame.data)
            captured_at = time.time()
            name = f"frame_{index:06d}_{captured_at:.3f}.jpg"
            path = output / name
            path.write_bytes(data)
            manifest.write(
                json.dumps(
                    {
                        "file": name,
                        "captured_at": captured_at,
                        "status": int(frame.status),
                        "width": int(frame.width),
                        "height": int(frame.height),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "undistort": True,
                    },
                    separators=(",", ":"),
                )
                + "\n"
            )

    node.destroy_node()
    rclpy.shutdown()


if __name__ == "__main__":
    main()
