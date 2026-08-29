#!/usr/bin/env python3
"""Remove the two late high phases from the vendor push-up trajectory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-npz", required=True, type=Path)
    parser.add_argument("--source-head", required=True, type=Path)
    parser.add_argument("--source-dag", required=True, type=Path)
    parser.add_argument("--output-npz", required=True, type=Path)
    parser.add_argument("--output-head", required=True, type=Path)
    parser.add_argument("--output-dag", required=True, type=Path)
    parser.add_argument("--remove-start", type=int, default=178)
    parser.add_argument("--remove-end", type=int, default=274)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with np.load(args.source_npz, allow_pickle=True) as source:
        frame_count = int(source["qpos"].shape[0])
        if not 0 < args.remove_start < args.remove_end < frame_count:
            raise ValueError("invalid frame removal interval")

        left = args.remove_start - 1
        right = args.remove_end
        position_gap = float(
            np.max(np.abs(source["qpos"][left] - source["qpos"][right]))
        )
        velocity_gap = float(
            np.max(np.abs(source["qvel"][left] - source["qvel"][right]))
        )
        if position_gap > 0.05 or velocity_gap > 0.15:
            raise ValueError(
                "unsafe trajectory seam: "
                f"position_gap={position_gap:.6f}, velocity_gap={velocity_gap:.6f}"
            )

        output: dict[str, np.ndarray] = {}
        for name in source.files:
            value = source[name]
            if name == "split_points":
                output[name] = np.asarray(
                    [0, frame_count - (args.remove_end - args.remove_start)],
                    dtype=value.dtype,
                )
            elif value.ndim > 0 and value.shape[0] == frame_count:
                output[name] = np.concatenate(
                    (value[: args.remove_start], value[args.remove_end :]), axis=0
                )
            else:
                output[name] = value

    args.output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez(args.output_npz, **output)

    head_rows = args.source_head.read_text(encoding="utf-8").splitlines()
    if not head_rows:
        raise ValueError("head trajectory is empty")
    head_start = round(args.remove_start / frame_count * len(head_rows))
    head_end = round(args.remove_end / frame_count * len(head_rows))
    shortened_head = head_rows[:head_start] + head_rows[head_end:]
    args.output_head.write_text("\n".join(shortened_head) + "\n", encoding="utf-8")

    dag = json.loads(args.source_dag.read_text(encoding="utf-8"))
    dag["task_id"] = "heikesong_pushup_without_late_highs"
    for node in dag["dag"]["nodes"]:
        if node["id"] == "Action_BODY":
            node["args"]["action_path"] = str(args.output_npz)
        elif node["id"] == "Action_HEAD":
            node["args"]["action_path"] = str(args.output_head)
    args.output_dag.write_text(
        json.dumps(dag, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "source_frames": frame_count,
                "output_frames": int(output["qpos"].shape[0]),
                "removed": [args.remove_start, args.remove_end],
                "head_removed": [head_start, head_end],
                "position_gap": position_gap,
                "velocity_gap": velocity_gap,
            },
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
